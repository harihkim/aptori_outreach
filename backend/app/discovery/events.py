"""Correlated discovery progress events and their worker-safe event bus.

Progress events are ephemeral operational notifications. PostgreSQL remains
the source of truth for runs and observations; Redis pub/sub only wakes live
clients after the corresponding database transaction has committed. Keeping
the event bus behind this small port makes the worker and SSE boundary
testable without Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from fastapi.sse import ServerSentEvent
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import get_settings

logger = logging.getLogger(__name__)

ProgressEventType = Literal[
    "discovery.started",
    "discovery.candidate_found",
    "retrieval.observed",
    "discovery.completed",
    "conversation.normalized",
    "analysis.completed",
    "draft.version_created",
    "approval.created",
    "approval.revoked",
    "approval.expired",
    "approval.consumed",
    "media.started",
    "media.completed",
    "browser.started",
    "browser.ready_for_human",
    "job.failed",
]

# The first four are the live discovery vertical slice. The remaining event
# families are reserved in the same wire catalog so later producers can be
# added without changing the SSE envelope or frontend subscription boundary.
EVENT_TYPES: tuple[ProgressEventType, ...] = (
    "discovery.started",
    "discovery.candidate_found",
    "retrieval.observed",
    "discovery.completed",
    "conversation.normalized",
    "analysis.completed",
    "draft.version_created",
    "approval.created",
    "approval.revoked",
    "approval.expired",
    "approval.consumed",
    "media.started",
    "media.completed",
    "browser.started",
    "browser.ready_for_human",
    "job.failed",
)

EVENT_CHANNEL_PREFIX = "aptori:progress:v1:discovery-run"
HEARTBEAT_SECONDS = 15.0


class ProgressEvent(BaseModel):
    """One public SSE envelope with identity and correlation metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: ProgressEventType
    run_id: uuid.UUID
    workspace_id: uuid.UUID
    correlation_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        run_id: uuid.UUID,
        workspace_id: uuid.UUID,
        correlation_id: str,
        payload: dict[str, Any] | None = None,
    ) -> ProgressEvent:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown progress event type: {event_type!r}")
        return cls(
            id=uuid.uuid4().hex,
            type=event_type,
            run_id=run_id,
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            occurred_at=datetime.now(UTC),
            payload=payload or {},
        )

    def as_sse(self) -> ServerSentEvent:
        """Render the envelope using standard SSE event and id fields."""
        return ServerSentEvent(
            data=self.model_dump(mode="json"),
            event=self.type,
            id=self.id,
        )


class EventBus(Protocol):
    """Async publish/subscribe seam shared by workers and the HTTP stream."""

    async def publish(self, event: ProgressEvent) -> None:
        """Publish one event after its domain transaction has committed."""

    def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[ProgressEvent | None]:
        """Yield events for a run; ``None`` is a keepalive tick."""


def event_channel(run_id: uuid.UUID) -> str:
    """Return a run-scoped channel; a client can never subscribe globally."""
    return f"{EVENT_CHANNEL_PREFIX}:{run_id}"


class InMemoryEventBus:
    """Small event bus for deterministic tests and local development."""

    def __init__(self, *, heartbeat_seconds: float = HEARTBEAT_SECONDS) -> None:
        self.heartbeat_seconds = heartbeat_seconds
        self._subscribers: dict[uuid.UUID, set[asyncio.Queue[ProgressEvent]]] = {}

    async def publish(self, event: ProgressEvent) -> None:
        for subscriber in tuple(self._subscribers.get(event.run_id, ())):
            subscriber.put_nowait(event)

    async def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[ProgressEvent | None]:
        subscriber: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subscribers.setdefault(run_id, set()).add(subscriber)
        try:
            while True:
                try:
                    yield await asyncio.wait_for(
                        subscriber.get(), timeout=self.heartbeat_seconds
                    )
                except TimeoutError:
                    yield None
        finally:
            subscribers = self._subscribers.get(run_id)
            if subscribers is not None:
                subscribers.discard(subscriber)
                if not subscribers:
                    self._subscribers.pop(run_id, None)


class RedisEventBus:
    """Redis pub/sub adapter used by separate FastAPI and arq processes."""

    def __init__(
        self,
        redis_url: str,
        *,
        heartbeat_seconds: float = HEARTBEAT_SECONDS,
    ) -> None:
        self.redis_url = redis_url
        self.heartbeat_seconds = heartbeat_seconds

    async def publish(self, event: ProgressEvent) -> None:
        from redis.asyncio import from_url

        client = from_url(self.redis_url, decode_responses=True)
        try:
            await client.publish(event_channel(event.run_id), event.model_dump_json())
        finally:
            await client.aclose()

    async def subscribe(self, run_id: uuid.UUID) -> AsyncIterator[ProgressEvent | None]:
        from redis.asyncio import from_url

        client = from_url(self.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        channel = event_channel(run_id)
        try:
            await pubsub.subscribe(channel)
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=self.heartbeat_seconds,
                )
                if message is None:
                    yield None
                    continue
                raw_data = message.get("data")
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode("utf-8", errors="replace")
                if not isinstance(raw_data, str):
                    continue
                try:
                    yield ProgressEvent.model_validate(json.loads(raw_data))
                except (TypeError, ValueError, ValidationError) as error:
                    # A malformed message must not terminate every viewer of
                    # this run; the durable database state remains authoritative.
                    logger.warning(
                        "discarding malformed discovery progress event (%s)",
                        type(error).__name__,
                    )
        finally:
            try:
                await pubsub.unsubscribe(channel)
            finally:
                await pubsub.aclose()
                await client.aclose()


DEFAULT_EVENT_BUS: EventBus | None = None


def get_event_bus() -> EventBus:
    """Lazily select Redis so importing the application never opens a socket."""
    global DEFAULT_EVENT_BUS
    if DEFAULT_EVENT_BUS is None:
        DEFAULT_EVENT_BUS = RedisEventBus(get_settings().redis_url)
    return DEFAULT_EVENT_BUS


async def publish_progress_event(event: ProgressEvent) -> None:
    """Publish best-effort operational progress without failing domain work."""
    try:
        await get_event_bus().publish(event)
    except Exception:  # noqa: BLE001 - progress must not roll back evidence
        logger.warning(
            "discovery progress event unavailable (%s, run %s)",
            event.type,
            event.run_id,
            exc_info=True,
        )
