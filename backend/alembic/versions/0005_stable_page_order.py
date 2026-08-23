"""Add monotonic ordering for Campaign and audit pagination.

Revision ID: 0005_stable_page_order
Revises: 0004_reconcile_idempotency
Create Date: 2026-08-23
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_stable_page_order"
down_revision = "0004_reconcile_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "creation_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_campaigns_creation_order"), "campaigns", ["creation_order"]
    )
    op.create_index(
        "ix_campaigns_workspace_creation_order",
        "campaigns",
        ["workspace_id", "creation_order"],
        unique=False,
    )

    op.add_column(
        "audit_events",
        sa.Column(
            "event_order",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        op.f("uq_audit_events_event_order"), "audit_events", ["event_order"]
    )
    op.drop_index("ix_audit_events_target", table_name="audit_events")
    op.create_index(
        "ix_audit_events_target_order",
        "audit_events",
        ["target_type", "target_id", "event_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_target_order", table_name="audit_events")
    op.create_index(
        "ix_audit_events_target",
        "audit_events",
        ["target_type", "target_id"],
        unique=False,
    )
    op.drop_constraint(
        op.f("uq_audit_events_event_order"), "audit_events", type_="unique"
    )
    op.drop_column("audit_events", "event_order")

    op.drop_index("ix_campaigns_workspace_creation_order", table_name="campaigns")
    op.drop_constraint(
        op.f("uq_campaigns_creation_order"), "campaigns", type_="unique"
    )
    op.drop_column("campaigns", "creation_order")
