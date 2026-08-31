"""Require callers to choose the observation evidence state.

Revision ID: 0013_require_evidence_state
Revises: 0012_evidence_bundles
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_require_evidence_state"
down_revision = "0012_evidence_bundles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "retrieval_observations",
        "evidence_state",
        server_default=None,
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "retrieval_observations",
        "evidence_state",
        server_default="legacy",
        existing_type=sa.String(length=16),
        existing_nullable=False,
    )
