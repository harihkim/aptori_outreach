"""Add immutable Model Runs and Analyses plus Campaign-scoped Opportunities.

Revision ID: 0015_analysis_opportunities
Revises: 0014_conversations
Create Date: 2026-09-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_analysis_opportunities"
down_revision = "0014_conversations"
branch_labels = None
depends_on = None

# Model Runs and Analyses are evidence; Opportunities carry a lifecycle.
_IMMUTABLE_TABLES = ("model_runs", "analyses")

_MODEL_TIERS = ("ordinary", "strong")
_MODEL_RUN_STATUSES = ("succeeded", "failed")
_MODEL_RUN_FAILURE_CLASSES = (
    "model_unconfigured",
    "model_requests_blocked",
    "model_request_failed",
    "output_invalid",
    "usage_limit_exceeded",
    "domain_validation_failed",
)
_RECOMMENDED_ACTIONS = (
    "ignore",
    "monitor",
    "reply_helpfully",
    "reply_with_product",
    "content_opportunity",
)
_OPPORTUNITY_STATUSES = ("open", "saved", "dismissed", "acted_on")
_FACTORS = (
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


def _uuid_pk() -> sa.Column[object]:
    return sa.Column(
        "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _create_immutability_guards() -> None:
    # The trigger function from 0014 is generic over TG_TABLE_NAME; reuse it.
    for table in _IMMUTABLE_TABLES:
        for action in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER suppress_{table}_{action} "
                f"BEFORE {action.upper()} ON {table} FOR EACH ROW "
                "EXECUTE FUNCTION suppress_conversation_record_mutation()"
            )
        op.execute(
            f"CREATE TRIGGER suppress_{table}_truncate "
            f"BEFORE TRUNCATE ON {table} FOR EACH STATEMENT "
            "EXECUTE FUNCTION suppress_conversation_record_mutation()"
        )


def _drop_immutability_guards() -> None:
    for table in reversed(_IMMUTABLE_TABLES):
        for action in ("update", "delete", "truncate"):
            op.execute(f"DROP TRIGGER IF EXISTS suppress_{table}_{action} ON {table}")


def upgrade() -> None:
    op.create_table(
        "model_runs",
        _uuid_pk(),
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("task_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("eval_suite_id", sa.String(length=100), nullable=False),
        sa.Column("model_tier", sa.String(length=16), nullable=False),
        sa.Column("served_tier", sa.String(length=16), nullable=False),
        sa.Column("requested_model", sa.String(length=200), nullable=True),
        sa.Column("actual_model", sa.String(length=200), nullable=True),
        sa.Column("endpoint_label", sa.String(length=200), nullable=True),
        sa.Column(
            "model_settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("output_retry_count", sa.Integer(), nullable=False),
        sa.Column("cost_status", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("failure_class", sa.String(length=48), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("run_reference", sa.String(length=128), nullable=True),
        sa.Column("retention_policy", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_runs")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_model_runs_workspace_id_workspaces"),
        ),
        sa.UniqueConstraint("creation_order", name="uq_model_runs_creation_order"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_model_runs_workspace_id_id"),
        sa.CheckConstraint(
            _in_values("model_tier", _MODEL_TIERS), name=op.f("ck_model_runs_tier_values")
        ),
        sa.CheckConstraint(
            _in_values("status", _MODEL_RUN_STATUSES),
            name=op.f("ck_model_runs_status_values"),
        ),
        sa.CheckConstraint(
            "failure_class IS NULL OR "
            + _in_values("failure_class", _MODEL_RUN_FAILURE_CLASSES),
            name=op.f("ck_model_runs_failure_class_values"),
        ),
        sa.CheckConstraint(
            "(status = 'succeeded') = (failure_class IS NULL)",
            name=op.f("ck_model_runs_failure_class_matches_status"),
        ),
        sa.CheckConstraint(
            "input_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_model_runs_input_sha256_format"),
        ),
        sa.CheckConstraint(
            "output_sha256 IS NULL OR output_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_model_runs_output_sha256_format"),
        ),
    )
    op.create_index(
        "ix_model_runs_workspace_creation_order",
        "model_runs",
        ["workspace_id", "creation_order"],
    )

    op.create_table(
        "analyses",
        _uuid_pk(),
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_version_id", sa.Uuid(), nullable=False),
        sa.Column("model_run_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_identity", sa.String(length=200), nullable=False),
        *(sa.Column(name, sa.Float(), nullable=False) for name in _FACTORS),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("persona", sa.String(length=200), nullable=True),
        sa.Column("recommended_action", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_analyses_workspace_id_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_analyses_workspace_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_analyses_workspace_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_version_id"],
            ["conversation_versions.workspace_id", "conversation_versions.id"],
            name="fk_analyses_workspace_conversation_version",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "model_run_id"],
            ["model_runs.workspace_id", "model_runs.id"],
            name="fk_analyses_workspace_model_run",
        ),
        sa.UniqueConstraint("creation_order", name="uq_analyses_creation_order"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_analyses_workspace_id_id"),
        sa.UniqueConstraint(
            "campaign_id",
            "conversation_version_id",
            "analysis_identity",
            name="uq_analyses_idempotency",
        ),
        sa.CheckConstraint(
            _in_values("recommended_action", _RECOMMENDED_ACTIONS),
            name=op.f("ck_analyses_recommended_action_values"),
        ),
        *(
            sa.CheckConstraint(
                f"{name} >= 0 AND {name} <= 1",
                name=op.f(f"ck_analyses_{name}_unit_interval"),
            )
            for name in _FACTORS
        ),
    )
    op.create_index(
        "ix_analyses_workspace_creation_order",
        "analyses",
        ["workspace_id", "creation_order"],
    )
    op.create_index("ix_analyses_conversation", "analyses", ["conversation_id"])

    op.create_table(
        "opportunities",
        _uuid_pk(),
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column(
            "score_components",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("formula_version", sa.String(length=16), nullable=False),
        sa.Column("post_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="open", nullable=False
        ),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.String(length=200), nullable=True),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opportunities")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_opportunities_workspace_id_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "campaign_id"],
            ["campaigns.workspace_id", "campaigns.id"],
            name="fk_opportunities_workspace_campaign",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_opportunities_workspace_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "analysis_id"],
            ["analyses.workspace_id", "analyses.id"],
            name="fk_opportunities_workspace_analysis",
        ),
        sa.UniqueConstraint(
            "creation_order", name="uq_opportunities_creation_order"
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_opportunities_workspace_id_id"
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "conversation_id",
            name="uq_opportunities_campaign_conversation",
        ),
        sa.CheckConstraint(
            _in_values("status", _OPPORTUNITY_STATUSES),
            name=op.f("ck_opportunities_status_values"),
        ),
        sa.CheckConstraint(
            "opportunity_score >= 0 AND opportunity_score <= 1",
            name=op.f("ck_opportunities_opportunity_score_unit_interval"),
        ),
    )
    op.create_index(
        "ix_opportunities_campaign_score",
        "opportunities",
        ["campaign_id", "opportunity_score", "creation_order"],
    )
    op.create_index(
        "ix_opportunities_workspace_score",
        "opportunities",
        ["workspace_id", "opportunity_score", "creation_order"],
    )
    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    counts = {
        table: int(bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in _IMMUTABLE_TABLES
    }
    if any(counts.values()):
        retained = ", ".join(
            f"{table}={count}" for table, count in counts.items() if count
        )
        raise RuntimeError(
            "refusing to downgrade 0015_analysis_opportunities: immutable "
            f"analysis evidence would be lost ({retained})"
        )
    _drop_immutability_guards()
    op.drop_index("ix_opportunities_workspace_score", table_name="opportunities")
    op.drop_index("ix_opportunities_campaign_score", table_name="opportunities")
    op.drop_table("opportunities")
    op.drop_index("ix_analyses_conversation", table_name="analyses")
    op.drop_index("ix_analyses_workspace_creation_order", table_name="analyses")
    op.drop_table("analyses")
    op.drop_index("ix_model_runs_workspace_creation_order", table_name="model_runs")
    op.drop_table("model_runs")
