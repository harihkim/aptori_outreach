import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

# Wire values for the Discovery lifecycle and retrieval evidence. The database
# enforces the same sets via CHECK constraints; the API layer validates first.
DISCOVERY_RUN_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "cancelled")
OBSERVATION_CAPABILITIES = ("discovery", "thread_fetch")
RETRIEVAL_OBSERVATION_STATUSES = (
    "success",
    "no_results",
    "incomplete",
    "blocked",
    "rate_limited",
    "auth_required",
    "forbidden",
    "upstream_unavailable",
    "parse_failed",
    "transport_failed",
    "runtime_verification_failed",
    "failed",
)


def _in_values(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    __table_args__ = (
        CheckConstraint(_in_values("status", DISCOVERY_RUN_STATUSES), name="status_values"),
        Index("ix_discovery_runs_campaign_creation_order", "campaign_id", "creation_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creation_order: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaigns.id"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued"
    )
    method_plan: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128))
    metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RetrievalObservation(Base):
    """Append-only retrieval evidence (INV-012).

    The database rejects UPDATE and DELETE on this table via triggers; rows are
    written once per (run, query) and never revised.
    """

    __tablename__ = "retrieval_observations"
    __table_args__ = (
        UniqueConstraint(
            "discovery_run_id", "query_id", name="uq_retrieval_observations_run_query"
        ),
        CheckConstraint(
            _in_values("capability", OBSERVATION_CAPABILITIES), name="capability_values"
        ),
        CheckConstraint(
            _in_values("status", RETRIEVAL_OBSERVATION_STATUSES), name="status_values"
        ),
        Index(
            "ix_retrieval_observations_run_creation_order",
            "discovery_run_id",
            "creation_order",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creation_order: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True
    )
    discovery_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_runs.id")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), index=True
    )
    query_id: Mapped[str] = mapped_column(String(200))
    schema_version: Mapped[int] = mapped_column(Integer)
    capability: Mapped[str] = mapped_column(String(32))
    provider_variant: Mapped[str] = mapped_column(String(200))
    config_sha256: Mapped[str] = mapped_column(String(64))
    observation_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32))
    failure_class: Mapped[str | None] = mapped_column(String(64))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    final_url: Mapped[str | None] = mapped_column(Text)
    external_source_id: Mapped[str | None] = mapped_column(Text)
    candidate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    candidates: Mapped[list[object]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    normalized_sha256: Mapped[str | None] = mapped_column(String(64))
    normalized_content_sha256: Mapped[str | None] = mapped_column(String(64))
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runtime: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    network: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    raw_artifact: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    evidence_directory: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
