"""Immutable Model Run provenance for every LLM Task attempt."""

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

MODEL_TIERS = ("ordinary", "strong")
MODEL_RUN_STATUSES = ("succeeded", "failed")
# Why a run produced no authoritative output. Each class names who owns the
# fix: configuration, the deployment's test guard, the endpoint, the model's
# output, the run limits, or the domain validators.
MODEL_RUN_FAILURE_CLASSES = (
    "model_unconfigured",
    "model_requests_blocked",
    "model_request_failed",
    "output_invalid",
    "usage_limit_exceeded",
    "domain_validation_failed",
)
# Prompts and completions are never stored; only their digests are. This is
# the one retention policy the prototype implements.
RETENTION_HASHES_ONLY = "hashes_only"
COST_UNPRICED = "unpriced"


def _in_values(column: str, values: tuple[str, ...]) -> str:
    listed = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({listed})"


class ModelRun(Base):
    """One LLM Task attempt: versions, routing, usage, and outcome.

    Rows are written once, after the attempt settles, and never revised.
    """

    __tablename__ = "model_runs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_model_runs_workspace_id_id"),
        CheckConstraint(_in_values("model_tier", MODEL_TIERS), name="tier_values"),
        CheckConstraint(_in_values("status", MODEL_RUN_STATUSES), name="status_values"),
        CheckConstraint(
            "failure_class IS NULL OR "
            + _in_values("failure_class", MODEL_RUN_FAILURE_CLASSES),
            name="failure_class_values",
        ),
        CheckConstraint(
            "(status = 'succeeded') = (failure_class IS NULL)",
            name="failure_class_matches_status",
        ),
        CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="input_sha256_format"),
        CheckConstraint(
            "output_sha256 IS NULL OR output_sha256 ~ '^[0-9a-f]{64}$'",
            name="output_sha256_format",
        ),
        Index(
            "ix_model_runs_workspace_creation_order", "workspace_id", "creation_order"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    creation_order: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(100), nullable=False)
    task_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    eval_suite_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    # The tier the caller asked for may differ from the tier that served it
    # (strong falling back to ordinary is configuration, not code).
    served_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_model: Mapped[str | None] = mapped_column(String(200))
    actual_model: Mapped[str | None] = mapped_column(String(200))
    # Host of the configured endpoint: enough to audit routing, never a
    # provider name baked into code and never a credential.
    endpoint_label: Mapped[str | None] = mapped_column(String(200))
    model_settings: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=COST_UNPRICED
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    failure_class: Mapped[str | None] = mapped_column(String(48))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_reference: Mapped[str | None] = mapped_column(String(128))
    retention_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RETENTION_HASHES_ONLY
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
