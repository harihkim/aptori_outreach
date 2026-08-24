"""Observation vocabulary cleanup: dead status removed, purge surface removed.

The 'evidence_unreadable' outcome is a failure_class under status='failed',
never a status; this migration narrows ck_retrieval_observations_status_values
back to the twelve native wire statuses. The SECURITY DEFINER purge helper
aptori_force_drop_observations() is also dropped from production: privileged
cleanup belongs to migrations/owners, not to a callable runtime surface.

Revision ID: 0008_observation_vocabulary
Revises: 0007_observation_hardening
Create Date: 2026-08-24
"""

from alembic import op

revision = "0008_observation_vocabulary"
down_revision = "0007_observation_hardening"
branch_labels = None
depends_on = None

# The twelve native statuses emitted by the frozen Node observation document;
# identical to observations.STATUS_VALUES and models.RETRIEVAL_OBSERVATION_STATUSES.
_NATIVE_STATUS_CHECK = (
    "status IN ('success', 'no_results', 'incomplete', 'blocked', "
    "'rate_limited', 'auth_required', 'forbidden', "
    "'upstream_unavailable', 'parse_failed', 'transport_failed', "
    "'runtime_verification_failed', 'failed')"
)
# The 0007-era vocabulary, restored only on downgrade for chain symmetry.
_LEGACY_STATUS_CHECK = (
    "status IN ('success', 'no_results', 'incomplete', 'blocked', "
    "'rate_limited', 'auth_required', 'forbidden', "
    "'upstream_unavailable', 'parse_failed', 'transport_failed', "
    "'runtime_verification_failed', 'failed', 'evidence_unreadable')"
)


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS aptori_force_drop_observations()")
    op.drop_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        _NATIVE_STATUS_CHECK,
    )


def downgrade() -> None:
    # Chain symmetry only: these legacy surfaces existed at 0007 and come
    # back solely so this revision can be unwound.
    op.drop_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        _LEGACY_STATUS_CHECK,
    )
    op.execute(
        """
        CREATE FUNCTION aptori_force_drop_observations() RETURNS void AS $$
        BEGIN
            -- Legacy 0007 escape hatch, recreated only on downgrade.
            ALTER TABLE retrieval_observations DISABLE TRIGGER USER;
            TRUNCATE TABLE retrieval_observations;
            ALTER TABLE retrieval_observations ENABLE TRIGGER USER;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        """
    )
