import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.auditing.models import AuditEvent


def record_audit(
    session: Session,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: uuid.UUID,
    workspace_id: uuid.UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> None:
    """Append one audit row inside the caller's transaction.

    Never commits: the domain operation that caused the event owns the
    commit, so an audit row can never outlive the change it describes.
    """
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            workspace_id=workspace_id,
            before=before,
            after=after,
            correlation_id=correlation_id,
        )
    )
