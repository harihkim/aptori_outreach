"""Observation hardening: status vocabulary, TRUNCATE guard, sanctioned purge.

Extends the retrieval_observations status CHECK with 'evidence_unreadable',
rejects TRUNCATE at the SQL level, and provides exactly one sanctioned escape
hatch (aptori_force_drop_observations) that empties the table while restoring
every guard trigger afterwards.

Revision ID: 0007_observation_hardening
Revises: 0006_discovery_runs
Create Date: 2026-08-24
"""

from alembic import op

revision = "0007_observation_hardening"
down_revision = "0006_discovery_runs"
branch_labels = None
depends_on = None

# The original 0006 vocabulary, restored verbatim on downgrade.
_STATUS_WITHOUT_EVIDENCE_UNREADABLE = (
    "status IN ('success', 'no_results', 'incomplete', 'blocked', "
    "'rate_limited', 'auth_required', 'forbidden', "
    "'upstream_unavailable', 'parse_failed', 'transport_failed', "
    "'runtime_verification_failed', 'failed')"
)
_STATUS_WITH_EVIDENCE_UNREADABLE = (
    "status IN ('success', 'no_results', 'incomplete', 'blocked', "
    "'rate_limited', 'auth_required', 'forbidden', "
    "'upstream_unavailable', 'parse_failed', 'transport_failed', "
    "'runtime_verification_failed', 'failed', 'evidence_unreadable')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        _STATUS_WITH_EVIDENCE_UNREADABLE,
    )
    op.execute(
        """
        CREATE TRIGGER suppress_retrieval_observation_truncate
        BEFORE TRUNCATE ON retrieval_observations
        FOR EACH STATEMENT EXECUTE FUNCTION
            suppress_retrieval_observation_mutation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION aptori_force_drop_observations() RETURNS void AS $$
        BEGIN
            -- Single sanctioned escape hatch for ops/tests: leaves the table
            -- EMPTY with every guard trigger re-enabled.
            ALTER TABLE retrieval_observations DISABLE TRIGGER USER;
            TRUNCATE TABLE retrieval_observations;
            ALTER TABLE retrieval_observations ENABLE TRIGGER USER;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS aptori_force_drop_observations()")
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_retrieval_observation_truncate "
        "ON retrieval_observations"
    )
    op.drop_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_retrieval_observations_status_values",
        "retrieval_observations",
        _STATUS_WITHOUT_EVIDENCE_UNREADABLE,
    )
