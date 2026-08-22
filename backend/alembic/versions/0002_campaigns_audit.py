"""Campaign domain slice: workspaces, campaigns, audit events.

Seeds the fixed default workspace every Campaign must reference.

Revision ID: 0002_campaigns_audit
Revises: 0001_baseline
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_campaigns_audit"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("name", name=op.f("uq_workspaces_name")),
    )
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("product_context", sa.Text(), nullable=True),
        sa.Column("icp", sa.Text(), nullable=True),
        sa.Column(
            "keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "subreddits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "competitors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "approved_claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "prohibited_claims",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("promotion_posture", sa.String(length=32), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="draft", nullable=False
        ),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campaigns")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_campaigns_workspace_id_workspaces"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'archived')",
            name=op.f("ck_campaigns_status_values"),
        ),
        sa.CheckConstraint(
            "promotion_posture IN ('expertise_first', 'balanced', 'high_intent_only')",
            name=op.f("ck_campaigns_posture_values"),
        ),
    )
    op.create_index(
        op.f("ix_campaigns_workspace_id"), "campaigns", ["workspace_id"], unique=False
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(
        "ix_audit_events_target",
        "audit_events",
        ["target_type", "target_id"],
        unique=False,
    )
    op.execute(
        f"INSERT INTO workspaces (id, name) VALUES ('{DEFAULT_WORKSPACE_ID}', 'aptori')"
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_campaigns_workspace_id"), table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_table("workspaces")
