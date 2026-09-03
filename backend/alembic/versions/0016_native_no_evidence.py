"""Allow native retrieval failures without retained raw evidence.

Access challenges are deliberately not stored, and provider failures can occur
before a response body exists. Preserve those typed outcomes instead of forcing
them into the backend ``evidence_unreadable`` class.

Revision ID: 0016_native_no_evidence
Revises: 0015_analysis_opportunities
Create Date: 2026-09-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_native_no_evidence"
down_revision = "0015_analysis_opportunities"
branch_labels = None
depends_on = None

_CONSTRAINT = "ck_retrieval_observations_evidence_reference_values"
_OLD_REFERENCE_CHECK = (
    "(evidence_state = 'bundle' AND evidence_bundle_id IS NOT NULL "
    "AND evidence_directory IS NULL) OR "
    "(evidence_state = 'legacy' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NOT NULL) OR "
    "(evidence_state = 'none' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NULL AND status = 'failed' "
    "AND failure_class IS NOT NULL)"
)
_NEW_REFERENCE_CHECK = (
    "(evidence_state = 'bundle' AND evidence_bundle_id IS NOT NULL "
    "AND evidence_directory IS NULL) OR "
    "(evidence_state = 'legacy' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NOT NULL) OR "
    "(evidence_state = 'none' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NULL AND ("
    "(status = 'failed' AND failure_class IS NOT NULL) OR "
    "(failure_class IS NULL AND status IN ("
    "'blocked', 'rate_limited', 'auth_required', 'forbidden', "
    "'upstream_unavailable', 'parse_failed', 'transport_failed', "
    "'runtime_verification_failed', 'failed'))))"
)


def _replace_constraint(definition: str) -> None:
    op.drop_constraint(_CONSTRAINT, "retrieval_observations", type_="check")
    op.create_check_constraint(_CONSTRAINT, "retrieval_observations", definition)


def upgrade() -> None:
    _replace_constraint(_NEW_REFERENCE_CHECK)


def downgrade() -> None:
    native_none_count = int(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM retrieval_observations "
                "WHERE evidence_state = 'none' AND failure_class IS NULL"
            )
        )
        .scalar_one()
    )
    if native_none_count:
        raise RuntimeError(
            "refusing to downgrade 0016_native_no_evidence: would invalidate "
            f"{native_none_count} native observation(s) without raw evidence"
        )
    _replace_constraint(_OLD_REFERENCE_CHECK)
