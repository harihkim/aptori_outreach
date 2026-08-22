import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base


class IdempotencyEvent(Base):
    """One row per (workspace, key): the claim, then the recorded response.

    status_code is null while the key is claimed but its request has not
    finished; a crash leaves the key claimed, which deliberately prevents a
    retry from executing the write twice.
    """

    __tablename__ = "idempotency_events"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_idempotency_events_workspace_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(200))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
