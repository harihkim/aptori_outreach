"""Discovery domain slice: runs and immutable retrieval observations.

Retrieval observations are append-only evidence (INV-012): BEFORE UPDATE OR
DELETE triggers reject any mutation at the SQL level, so the audit trail
cannot be rewritten even by privileged database clients.

Revision ID: 0006_discovery_runs
Revises: 0005_stable_page_order
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_discovery_runs"
down_revision = "0005_stable_page_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("campaign_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="queued", nullable=False
        ),
        sa.Column(
            "method_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovery_runs")),
        sa.UniqueConstraint(
            "creation_order", name=op.f("uq_discovery_runs_creation_order")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_discovery_runs_workspace_id_workspaces"),
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name=op.f("fk_discovery_runs_campaign_id_campaigns"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'partial', 'failed', "
            "'cancelled')",
            name=op.f("ck_discovery_runs_status_values"),
        ),
    )
    op.create_index(
        "ix_discovery_runs_campaign_creation_order",
        "discovery_runs",
        ["campaign_id", "creation_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_discovery_runs_workspace_id"),
        "discovery_runs",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "retrieval_observations",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("discovery_run_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("query_id", sa.String(length=200), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(length=32), nullable=False),
        sa.Column("provider_variant", sa.String(length=200), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("observation_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_class", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("external_source_id", sa.Text(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("normalized_sha256", sa.String(length=64), nullable=True),
        sa.Column("normalized_content_sha256", sa.String(length=64), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("runtime", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("network", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw_artifact", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("evidence_directory", sa.Text(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_observations")),
        sa.UniqueConstraint(
            "creation_order", name=op.f("uq_retrieval_observations_creation_order")
        ),
        sa.UniqueConstraint(
            "discovery_run_id",
            "query_id",
            name="uq_retrieval_observations_run_query",
        ),
        sa.ForeignKeyConstraint(
            ["discovery_run_id"],
            ["discovery_runs.id"],
            name=op.f("fk_retrieval_observations_discovery_run_id_discovery_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_retrieval_observations_workspace_id_workspaces"),
        ),
        sa.CheckConstraint(
            "capability IN ('discovery', 'thread_fetch')",
            name=op.f("ck_retrieval_observations_capability_values"),
        ),
        sa.CheckConstraint(
            "status IN ('success', 'no_results', 'incomplete', 'blocked', "
            "'rate_limited', 'auth_required', 'forbidden', "
            "'upstream_unavailable', 'parse_failed', 'transport_failed', "
            "'runtime_verification_failed', 'failed')",
            name=op.f("ck_retrieval_observations_status_values"),
        ),
    )
    op.create_index(
        "ix_retrieval_observations_run_creation_order",
        "retrieval_observations",
        ["discovery_run_id", "creation_order"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION suppress_retrieval_observation_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'retrieval_observations are immutable (INV-012)';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppress_retrieval_observation_update
        BEFORE UPDATE ON retrieval_observations
        FOR EACH ROW EXECUTE FUNCTION suppress_retrieval_observation_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppress_retrieval_observation_delete
        BEFORE DELETE ON retrieval_observations
        FOR EACH ROW EXECUTE FUNCTION suppress_retrieval_observation_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_retrieval_observation_update "
        "ON retrieval_observations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_retrieval_observation_delete "
        "ON retrieval_observations"
    )
    op.execute("DROP FUNCTION IF EXISTS suppress_retrieval_observation_mutation()")
    op.drop_index(
        "ix_retrieval_observations_run_creation_order",
        table_name="retrieval_observations",
    )
    op.drop_table("retrieval_observations")
    op.drop_index(
        "ix_discovery_runs_campaign_creation_order", table_name="discovery_runs"
    )
    op.drop_index(op.f("ix_discovery_runs_workspace_id"), table_name="discovery_runs")
    op.drop_table("discovery_runs")
