import uuid
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


def claim(
    session: Session, *, workspace_id: uuid.UUID, key: str, request_fingerprint: str
) -> Replay | None:
    """Claim the key inside the caller's transaction, or return the committed replay.

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


def attach(
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
        # Committed rows always carry a response; defensive only.
        raise KeyConflictError(str(event.id))
    return Replay(status_code=event.status_code, body=event.response_body)
