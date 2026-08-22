import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.idempotency.models import IdempotencyEvent


@dataclass(frozen=True)
class Replay:
    status_code: int
    body: dict[str, Any]


class KeyConflictError(ValueError):
    """The key was reused for a different request."""


def execute(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    key: str,
    method: str,
    path: str,
    payload: dict[str, Any],
    operation: Callable[[], Replay],
) -> Replay:
    """Execute and record one keyed write in a single transaction.

    The operation returns either a success or a deterministic domain error;
    both are committed with the key so every retry preserves the first result.
    Unexpected exceptions roll the whole transaction back, allowing a clean
    retry with the same key.
    """
    request_fingerprint = _fingerprint(method, path, payload)
    replay = _claim(
        session,
        workspace_id=workspace_id,
        key=key,
        request_fingerprint=request_fingerprint,
    )
    if replay is not None:
        return replay

    try:
        result = operation()
        _attach(
            session,
            workspace_id=workspace_id,
            key=key,
            status_code=result.status_code,
            body=result.body,
        )
        session.commit()
    except BaseException:
        session.rollback()
        raise
    return result


def _claim(
    session: Session, *, workspace_id: uuid.UUID, key: str, request_fingerprint: str
) -> Replay | None:
    """Claim the key inside the transaction, or return the committed replay.

    The INSERT is flushed (not committed), so a concurrent duplicate with the
    same key blocks on the unique index until this transaction commits - then
    rolls back and re-reads the committed row. Returns None when the caller
    freshly owns the key and must execute the write in this transaction;
    everything (claim, domain mutation, recorded response) commits or aborts
    together, so a crash never leaves a stuck or half-applied key.
    """
    existing = _find(session, workspace_id, key)
    if existing is not None:
        _assert_same_request(existing, request_fingerprint)
        return _replay(existing)

    session.add(
        IdempotencyEvent(
            key=key,
            workspace_id=workspace_id,
            request_fingerprint=request_fingerprint,
        )
    )
    try:
        session.flush()
    except IntegrityError:
        # A concurrent transaction claimed the same key and committed first.
        session.rollback()
        existing = _find(session, workspace_id, key)
        if existing is None:
            raise
        _assert_same_request(existing, request_fingerprint)
        return _replay(existing)
    return None


def _attach(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    key: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """Record the response on the pending claim row, in the same transaction."""
    existing = _find(session, workspace_id, key)
    if existing is None:
        raise KeyError(f"idempotency key {key!r} was not claimed")
    existing.status_code = status_code
    existing.response_body = body


def _find(
    session: Session, workspace_id: uuid.UUID, key: str
) -> IdempotencyEvent | None:
    return session.scalar(
        select(IdempotencyEvent).where(
            IdempotencyEvent.workspace_id == workspace_id,
            IdempotencyEvent.key == key,
        )
    )


def _assert_same_request(event: IdempotencyEvent, request_fingerprint: str) -> None:
    if event.request_fingerprint != request_fingerprint:
        raise KeyConflictError(str(event.id))


def _replay(event: IdempotencyEvent) -> Replay:
    if event.status_code is None or event.response_body is None:
        # Migration 0004 converts legacy pending rows to a stable recovery
        # result. This fallback keeps pre-migration databases honest too.
        return Replay(
            status_code=409,
            body={
                "detail": {
                    "code": "idempotency_key_reconciliation_required",
                    "message": (
                        "This key predates atomic idempotency and requires "
                        "operator reconciliation before it can be retried."
                    ),
                }
            },
        )
    return Replay(status_code=event.status_code, body=event.response_body)


def _fingerprint(method: str, path: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{method} {path} {canonical}".encode()).hexdigest()
