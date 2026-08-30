"""Progress-event contract and Workspace-scoped event-bus tests."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.discovery import events as progress_events
from app.discovery.events import (
    EVENT_TYPES,
    InMemoryEventBus,
    ProgressEvent,
    RedisEventBus,
    event_channel,
)

WORKSPACE_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
WORKSPACE_B = uuid.UUID("00000000-0000-0000-0000-000000000002")


def event(
    run_id: uuid.UUID,
    event_type: str,
    payload: dict[str, object],
    *,
    workspace_id: uuid.UUID = WORKSPACE_A,
) -> ProgressEvent:
    return ProgressEvent.create(
        event_type=event_type,
        run_id=run_id,
        workspace_id=workspace_id,
        correlation_id="corr-event-test",
        payload=payload,
    )


def test_progress_event_json_is_a_correlated_sse_envelope() -> None:
    run_id = uuid.uuid4()
    progress = event(run_id, "discovery.candidate_found", {"query_id": "q-a"})

    encoded = json.loads(progress.model_dump_json())

    assert encoded["type"] == "discovery.candidate_found"
    assert encoded["run_id"] == str(run_id)
    assert encoded["workspace_id"] == str(WORKSPACE_A)
    assert encoded["correlation_id"] == "corr-event-test"
    assert encoded["payload"] == {"query_id": "q-a"}


def test_event_type_catalog_includes_the_discovery_vertical_slice() -> None:
    assert EVENT_TYPES[:4] == (
        "discovery.started",
        "discovery.candidate_found",
        "retrieval.observed",
        "discovery.completed",
    )


async def next_event(
    stream: AsyncIterator[ProgressEvent | None],
) -> ProgressEvent | None:
    return await anext(stream)


def test_in_memory_subscriptions_are_scoped_by_workspace_and_run() -> None:
    async def exercise() -> None:
        run_id = uuid.uuid4()
        bus = InMemoryEventBus(heartbeat_seconds=60)
        own_stream = bus.subscribe(WORKSPACE_A, run_id)
        foreign_stream = bus.subscribe(WORKSPACE_B, run_id)
        own_next: asyncio.Task[ProgressEvent | None] = asyncio.create_task(
            next_event(own_stream)
        )
        foreign_next: asyncio.Task[ProgressEvent | None] = asyncio.create_task(
            next_event(foreign_stream)
        )
        await asyncio.sleep(0)

        foreign_event = event(
            run_id,
            "discovery.started",
            {"status": "running"},
            workspace_id=WORKSPACE_B,
        )
        await bus.publish(foreign_event)

        assert await asyncio.wait_for(foreign_next, timeout=1) == foreign_event
        assert not own_next.done()

        own_next.cancel()
        with pytest.raises(asyncio.CancelledError):
            await own_next
        await own_stream.aclose()
        await foreign_stream.aclose()

    asyncio.run(exercise())


class FakePubSub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    async def get_message(
        self, *, ignore_subscribe_messages: bool, timeout: float
    ) -> dict[str, Any] | None:
        del ignore_subscribe_messages, timeout
        return None

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed.append(channel)

    async def aclose(self) -> None:
        self.closed = True


class FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.pubsub_instance = FakePubSub()
        self.closed = False

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def pubsub(self) -> FakePubSub:
        return self.pubsub_instance

    async def aclose(self) -> None:
        self.closed = True


def test_redis_channels_include_workspace_and_filter_subscription_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def exercise() -> None:
        run_id = uuid.uuid4()
        client = FakeRedisClient()

        def fake_from_url(redis_url: str) -> FakeRedisClient:
            del redis_url
            return client

        monkeypatch.setattr(progress_events, "_redis_from_url", fake_from_url)
        bus = RedisEventBus("redis://unused", heartbeat_seconds=60)

        own_event = event(run_id, "discovery.started", {"status": "running"})
        await bus.publish(own_event)
        assert client.published == [
            (event_channel(WORKSPACE_A, run_id), own_event.model_dump_json())
        ]
        assert event_channel(WORKSPACE_A, run_id) != event_channel(WORKSPACE_B, run_id)

        stream = bus.subscribe(WORKSPACE_B, run_id)
        assert await anext(stream) is None
        assert client.pubsub_instance.subscribed == [event_channel(WORKSPACE_B, run_id)]
        await stream.aclose()
        assert client.pubsub_instance.unsubscribed == [
            event_channel(WORKSPACE_B, run_id)
        ]

    asyncio.run(exercise())
