"""Opportunity: one Campaign's assessment of one Conversation."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

OPPORTUNITY_STATUSES = ("open", "saved", "dismissed", "acted_on")


def _in_values(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


class Opportunity(Base):
    """Ranked, explainable assessment with a triage lifecycle.

    One row per (Campaign, Conversation). A newer Analysis re-scores the row
    in place; its disposition (saved, dismissed, acted on) is never reset by
    scoring. The aggregate score is always recomputable from the referenced
    Analysis plus the stored components.
    """

    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_opportunities_workspace_id_id"),
        UniqueConstraint(
            "campaign_id",
            "conversation_id",
            name="uq_opportunities_campaign_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_opportunities_workspace_campaign",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_opportunities_workspace_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "analysis_id"],
            ["analyses.workspace_id", "analyses.id"],
            name="fk_opportunities_workspace_analysis",
        ),
        CheckConstraint(
            _in_values("status", OPPORTUNITY_STATUSES), name="status_values"
        ),
        CheckConstraint(
            "opportunity_score >= 0 AND opportunity_score <= 1",
            name="opportunity_score_unit_interval",
        ),
        Index(
            "ix_opportunities_campaign_score",
            "campaign_id",
            "opportunity_score",
            "creation_order",
        ),
        Index(
            "ix_opportunities_workspace_score",
            "workspace_id",
            "opportunity_score",
            "creation_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creation_order: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    opportunity_score: Mapped[float] = mapped_column(Float, nullable=False)
    score_components: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(16), nullable=False)
    post_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default="open"
    )
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissal_reason: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
