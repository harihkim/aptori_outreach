"""Add missing workspace index on retrieval_observations.

The ORM declares workspace_id index=True on RetrievalObservation, but
migration 0006 only created ix_retrieval_observations_run_creation_order.
This migration adds the missing ix_retrieval_observations_workspace_id
so workspace-scoped observation queries do not seq-scan.

Revision ID: 0010_add_missing_observation_workspace_index
Revises: 0009_failure_class_vocabulary
Create Date: 2026-08-26
"""

from alembic import op

revision = "0010_add_missing_observation_workspace_index"
down_revision = "0009_failure_class_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_retrieval_observations_workspace_id"),
        "retrieval_observations",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_retrieval_observations_workspace_id"),
        table_name="retrieval_observations",
    )
