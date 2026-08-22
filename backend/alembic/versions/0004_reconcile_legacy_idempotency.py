"""Make legacy pending idempotency rows explicitly replayable.

Revision ID: 0004_reconcile_idempotency
Revises: 0003_idempotency_events
Create Date: 2026-08-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_reconcile_idempotency"
down_revision = "0003_idempotency_events"
branch_labels = None
depends_on = None

_RECONCILIATION_CODE = "idempotency_key_reconciliation_required"
_RECONCILIATION_MESSAGE = (
    "This key predates atomic idempotency and requires operator reconciliation "
    "before it can be retried."
)


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE idempotency_events
            SET status_code = 409,
                response_body = jsonb_build_object(
                    'detail', jsonb_build_object(
                        'code', :code,
                        'message', :message
                    )
                )
            WHERE status_code IS NULL OR response_body IS NULL
            """
        ).bindparams(code=_RECONCILIATION_CODE, message=_RECONCILIATION_MESSAGE)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE idempotency_events
            SET status_code = NULL,
                response_body = NULL
            WHERE response_body -> 'detail' ->> 'code' = :code
            """
        ).bindparams(code=_RECONCILIATION_CODE)
    )
