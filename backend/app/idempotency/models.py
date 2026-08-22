import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base


class IdempotencyEvent(Base):
    """One row per (workspace, key): the request fingerprint and its response.

    Rows become visible only when the whole keyed write committed (claim,
    domain mutation, recorded response in one transaction), so every
    committed row carries a replayable response and a crash leaves no row.
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
