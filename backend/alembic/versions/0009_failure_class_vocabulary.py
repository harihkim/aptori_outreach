"""Failure-class vocabulary for retrieval observations.

failure_class is the backend-classified taxonomy persisted under
status='failed'; native document statuses keep it NULL. This migration adds a
nullable CHECK pinning non-NULL values to the canonical nine, mirroring
models.FAILURE_CLASSES, the wire-schema Literal, and the contract JSON
'failureClasses' key (parity-tested).

Revision ID: 0009_failure_class_vocabulary
Revises: 0008_observation_vocabulary
Create Date: 2026-08-24
"""

from alembic import op

revision = "0009_failure_class_vocabulary"
down_revision = "0008_observation_vocabulary"
branch_labels = None
depends_on = None

# NULL allowed (native statuses); otherwise exactly models.FAILURE_CLASSES.
_FAILURE_CLASS_CHECK = (
    "failure_class IS NULL OR failure_class IN ("
    "'transport_error', 'transport_timeout', 'evidence_unreadable', "
    "'evidence_unlocated', 'unknown_observation_schema', "
    "'unknown_observation_status', 'contract_violation', "
    "'runtime_verification_failed', 'wrapper_error')"
)


def upgrade() -> None:
    op.create_check_constraint(
        "ck_retrieval_observations_failure_class_values",
        "retrieval_observations",
        _FAILURE_CLASS_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_retrieval_observations_failure_class_values",
        "retrieval_observations",
        type_="check",
    )
