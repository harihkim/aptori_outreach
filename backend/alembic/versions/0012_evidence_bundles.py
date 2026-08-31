"""Add immutable Evidence Bundles and an additive observation reference.

Evidence Bundle rows are durable, Workspace-owned manifests for raw retrieval
artifacts. Existing retrieval observations keep their exact legacy directory
references; the new evidence_state column defaults them to ``legacy`` without
rewriting the append-only payloads.

Revision ID: 0012_evidence_bundles
Revises: 0011_workspace_ownership
Create Date: 2026-08-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_evidence_bundles"
down_revision = "0011_workspace_ownership"
branch_labels = None
depends_on = None

_MANIFEST_VERSION = "evidence-bundle/v1"
_EVIDENCE_STATE_CHECK = "evidence_state IN ('bundle', 'legacy', 'none')"
_EVIDENCE_REFERENCE_CHECK = (
    "(evidence_state = 'bundle' AND evidence_bundle_id IS NOT NULL "
    "AND evidence_directory IS NULL) OR "
    "(evidence_state = 'legacy' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NOT NULL) OR "
    "(evidence_state = 'none' AND evidence_bundle_id IS NULL "
    "AND evidence_directory IS NULL AND status = 'failed' "
    "AND failure_class IS NOT NULL)"
)


def _create_bundle_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION suppress_evidence_bundle_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'evidence_bundles are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppress_evidence_bundle_update
        BEFORE UPDATE ON evidence_bundles
        FOR EACH ROW EXECUTE FUNCTION suppress_evidence_bundle_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppress_evidence_bundle_delete
        BEFORE DELETE ON evidence_bundles
        FOR EACH ROW EXECUTE FUNCTION suppress_evidence_bundle_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER suppress_evidence_bundle_truncate
        BEFORE TRUNCATE ON evidence_bundles
        FOR EACH STATEMENT EXECUTE FUNCTION suppress_evidence_bundle_mutation();
        """
    )


def _drop_bundle_guards() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_evidence_bundle_update ON evidence_bundles"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_evidence_bundle_delete ON evidence_bundles"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS suppress_evidence_bundle_truncate ON evidence_bundles"
    )
    op.execute("DROP FUNCTION IF EXISTS suppress_evidence_bundle_mutation()")


def upgrade() -> None:
    op.create_table(
        "evidence_bundles",
        sa.Column(
            "id",
            sa.Uuid(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "manifest_version",
            sa.String(length=32),
            server_default=_MANIFEST_VERSION,
            nullable=False,
        ),
        sa.Column("bundle_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column(
            "artifact_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_bundles")),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_evidence_bundles_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "bundle_sha256",
            name="uq_evidence_bundles_workspace_bundle_sha256",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "storage_key",
            name="uq_evidence_bundles_workspace_storage_key",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_evidence_bundles_workspace_id_workspaces"),
        ),
        sa.CheckConstraint(
            f"manifest_version = '{_MANIFEST_VERSION}'",
            name=op.f("ck_evidence_bundles_manifest_version_values"),
        ),
    )
    op.create_index(
        op.f("ix_evidence_bundles_workspace_id"),
        "evidence_bundles",
        ["workspace_id"],
        unique=False,
    )
    _create_bundle_guards()

    # Adding a constant DEFAULT is PostgreSQL's metadata-only backfill for
    # existing rows. It does not UPDATE the immutable observation table or
    # invoke its append-only trigger.
    op.add_column(
        "retrieval_observations",
        sa.Column(
            "evidence_state",
            sa.String(length=16),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.add_column(
        "retrieval_observations",
        sa.Column("evidence_bundle_id", sa.Uuid(), nullable=True),
    )
    op.alter_column(
        "retrieval_observations",
        "evidence_directory",
        existing_type=sa.Text(),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_retrieval_observations_workspace_evidence_bundle",
        "retrieval_observations",
        "evidence_bundles",
        ["workspace_id", "evidence_bundle_id"],
        ["workspace_id", "id"],
    )
    op.create_check_constraint(
        "ck_retrieval_observations_evidence_state_values",
        "retrieval_observations",
        _EVIDENCE_STATE_CHECK,
    )
    op.create_check_constraint(
        "ck_retrieval_observations_evidence_reference_values",
        "retrieval_observations",
        _EVIDENCE_REFERENCE_CHECK,
    )


def downgrade() -> None:
    bind = op.get_bind()
    bundle_count = int(
        bind.execute(sa.text("SELECT count(*) FROM evidence_bundles")).scalar_one()
    )
    nonlegacy_count = int(
        bind.execute(
            sa.text(
                "SELECT count(*) FROM retrieval_observations "
                "WHERE evidence_state IS DISTINCT FROM 'legacy'"
            )
        ).scalar_one()
    )
    if bundle_count or nonlegacy_count:
        details: list[str] = []
        if bundle_count:
            details.append(f"{bundle_count} Evidence Bundle(s)")
        if nonlegacy_count:
            details.append(f"{nonlegacy_count} non-legacy RetrievalObservation(s)")
        raise RuntimeError(
            "refusing to downgrade 0012_evidence_bundles: would lose "
            + " and ".join(details)
            + ". Preserve or remove these records explicitly before downgrading."
        )

    op.drop_constraint(
        "ck_retrieval_observations_evidence_reference_values",
        "retrieval_observations",
        type_="check",
    )
    op.drop_constraint(
        "ck_retrieval_observations_evidence_state_values",
        "retrieval_observations",
        type_="check",
    )
    op.drop_constraint(
        "fk_retrieval_observations_workspace_evidence_bundle",
        "retrieval_observations",
        type_="foreignkey",
    )
    op.alter_column(
        "retrieval_observations",
        "evidence_directory",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_column("retrieval_observations", "evidence_bundle_id")
    op.drop_column("retrieval_observations", "evidence_state")

    _drop_bundle_guards()
    op.drop_index(
        op.f("ix_evidence_bundles_workspace_id"),
        table_name="evidence_bundles",
    )
    op.drop_table("evidence_bundles")
