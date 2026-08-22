import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

# Wire values for the Campaign lifecycle and promotion posture. The database
# enforces the same sets via CHECK constraints; the API layer validates first.
CAMPAIGN_STATUSES = ("draft", "active", "paused", "archived")
CAMPAIGN_POSTURES = ("expertise_first", "balanced", "high_intent_only")


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name="status_values",
        ),
        CheckConstraint(
            "promotion_posture IN ('expertise_first', 'balanced', 'high_intent_only')",
            name="posture_values",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    product_context: Mapped[str | None] = mapped_column(Text)
    icp: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    subreddits: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    competitors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    approved_claims: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    prohibited_claims: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    promotion_posture: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
