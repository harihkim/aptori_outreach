"""Idempotent writes: one row per (workspace, idempotency key).

Revision ID: 0003_idempotency_events
Revises: 0002_campaigns_audit
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_idempotency_events"
down_revision = "0002_campaigns_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_events")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_idempotency_events_workspace_id_workspaces"),
        ),
        sa.UniqueConstraint("workspace_id", "key", name="uq_idempotency_events_workspace_key"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_events")
