"""Immutable Analyses: typed factors bound to one Conversation Version."""

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
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

RECOMMENDED_ACTIONS = (
    "ignore",
    "monitor",
    "reply_helpfully",
    "reply_with_product",
    "content_opportunity",
)
FACTOR_COLUMNS = (
    "relevance",
    "pain_intensity",
    "buying_intent",
    "replyability",
    "product_fit",
    "promotion_fit",
    "confidence",
)


def _in_values(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


def _unit_interval(column: str) -> CheckConstraint:
    return CheckConstraint(
        f"{column} >= 0 AND {column} <= 1", name=f"{column}_unit_interval"
    )


class Analysis(Base):
    """One validated `analyze_conversation` result; never revised.

    ``analysis_identity`` freezes the task, prompt, and schema versions that
    produced the row, so replaying the job under the same versions finds it
    instead of asking the model again.
    """

    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_analyses_workspace_id_id"),
        UniqueConstraint(
            "campaign_id",
            "conversation_version_id",
            "analysis_identity",
            name="uq_analyses_idempotency",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_analyses_workspace_campaign",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_analyses_workspace_conversation",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_version_id"],
            ["conversation_versions.workspace_id", "conversation_versions.id"],
            name="fk_analyses_workspace_conversation_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "model_run_id"],
            ["model_runs.workspace_id", "model_runs.id"],
            name="fk_analyses_workspace_model_run",
        ),
        CheckConstraint(
            _in_values("recommended_action", RECOMMENDED_ACTIONS),
            name="recommended_action_values",
        ),
        *(_unit_interval(column) for column in FACTOR_COLUMNS),
        Index("ix_analyses_workspace_creation_order", "workspace_id", "creation_order"),
        Index("ix_analyses_conversation", "conversation_id"),
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
    conversation_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    model_run_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    analysis_identity: Mapped[str] = mapped_column(String(200), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)
    pain_intensity: Mapped[float] = mapped_column(Float, nullable=False)
    buying_intent: Mapped[float] = mapped_column(Float, nullable=False)
    replyability: Mapped[float] = mapped_column(Float, nullable=False)
    product_fit: Mapped[float] = mapped_column(Float, nullable=False)
    promotion_fit: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    persona: Mapped[str | None] = mapped_column(String(200))
    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def factors(self) -> dict[str, float]:
        return {name: float(getattr(self, name)) for name in FACTOR_COLUMNS}
