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


class KeyInProgressError(ValueError):
    """The key is claimed by a request that has not finished."""


def claim(
    session: Session, *, workspace_id: uuid.UUID, key: str, request_fingerprint: str
) -> Replay | None:
    """Claim the key for this request, or return the recorded replay.

    Returns None when the caller freshly owns the key and must execute the
    write. The claim commits immediately so a concurrent duplicate cannot
    also execute.
    """
    existing = _find(session, workspace_id, key)
    if existing is not None:
        _assert_same_request(existing, request_fingerprint)
        return _replay_or_in_progress(existing)

    session.add(
        IdempotencyEvent(
            key=key,
            workspace_id=workspace_id,
            request_fingerprint=request_fingerprint,
        )
    )
    try:
        session.commit()
    except IntegrityError:
        # A concurrent request claimed the same key first.
        session.rollback()
        existing = _find(session, workspace_id, key)
        if existing is None:
            raise
        _assert_same_request(existing, request_fingerprint)
        return _replay_or_in_progress(existing)
    return None


def record(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    key: str,
    status_code: int,
    body: dict[str, Any],
) -> None:
    """Attach the response to the claimed key so replays return it."""
    existing = _find(session, workspace_id, key)
    if existing is None:
        raise KeyError(f"idempotency key {key!r} was not claimed")
    existing.status_code = status_code
    existing.response_body = body
    session.commit()


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


def _replay_or_in_progress(event: IdempotencyEvent) -> Replay | None:
    if event.status_code is None:
        raise KeyInProgressError(str(event.id))
    if event.response_body is None:
        raise KeyInProgressError(str(event.id))
    return Replay(status_code=event.status_code, body=event.response_body)
