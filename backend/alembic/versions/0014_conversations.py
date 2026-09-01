"""Add tenant-safe Conversations, immutable Versions, and provenance.

Revision ID: 0014_conversations
Revises: 0013_require_evidence_state
Create Date: 2026-09-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_conversations"
down_revision = "0013_require_evidence_state"
branch_labels = None
depends_on = None

_IMMUTABLE_TABLES = (
    "conversations",
    "conversation_versions",
    "conversation_version_observations",
)


def _create_immutability_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION suppress_conversation_record_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% records are immutable', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in _IMMUTABLE_TABLES:
        for action in ("update", "delete"):
            op.execute(
                f"CREATE TRIGGER suppress_{table}_{action} "
                f"BEFORE {action.upper()} ON {table} FOR EACH ROW "
                "EXECUTE FUNCTION suppress_conversation_record_mutation()"
            )
        op.execute(
            f"CREATE TRIGGER suppress_{table}_truncate "
            f"BEFORE TRUNCATE ON {table} FOR EACH STATEMENT "
            "EXECUTE FUNCTION suppress_conversation_record_mutation()"
        )


def _drop_immutability_guards() -> None:
    for table in reversed(_IMMUTABLE_TABLES):
        for action in ("update", "delete", "truncate"):
            op.execute(f"DROP TRIGGER IF EXISTS suppress_{table}_{action} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS suppress_conversation_record_mutation()")


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("source_platform", sa.String(length=32), nullable=False),
        sa.Column("canonical_external_discussion_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_conversations_workspace_id_workspaces"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_conversations_workspace_id_id"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "source_platform",
            "canonical_external_discussion_id",
            name="uq_conversations_workspace_source_external_id",
        ),
        sa.CheckConstraint(
            "source_platform = lower(source_platform) AND length(source_platform) > 0",
            name=op.f("ck_conversations_source_platform_canonical"),
        ),
        sa.CheckConstraint(
            "length(canonical_external_discussion_id) > 0",
            name=op.f("ck_conversations_external_discussion_id_nonempty"),
        ),
    )
    op.create_index(
        "ix_conversations_workspace_created_at",
        "conversations",
        ["workspace_id", "created_at"],
    )

    op.create_table(
        "conversation_versions",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("normalizer_version", sa.String(length=100), nullable=False),
        sa.Column("normalized_sha256", sa.String(length=64), nullable=False),
        sa.Column("normalized_content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "normalized_content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("source_tree_exhausted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_versions")),
        sa.UniqueConstraint(
            "workspace_id", "id", name="uq_conversation_versions_workspace_id_id"
        ),
        sa.UniqueConstraint(
            "conversation_id",
            "normalizer_version",
            "normalized_content_sha256",
            name="uq_conversation_versions_identity",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_conversation_versions_workspace_conversation",
        ),
        sa.CheckConstraint(
            "length(normalizer_version) > 0",
            name=op.f("ck_conversation_versions_normalizer_version_nonempty"),
        ),
        sa.CheckConstraint(
            "normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_conversation_versions_normalized_sha256_format"),
        ),
        sa.CheckConstraint(
            "normalized_content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_conversation_versions_normalized_content_sha256_format"),
        ),
    )
    op.create_index(
        "ix_conversation_versions_conversation_created_at",
        "conversation_versions",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "conversation_version_observations",
        sa.Column(
            "id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_version_id", sa.Uuid(), nullable=False),
        sa.Column("retrieval_observation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_conversation_version_observations")
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_conversation_version_observations_workspace_id_id",
        ),
        sa.UniqueConstraint(
            "conversation_version_id",
            "retrieval_observation_id",
            name="uq_conversation_version_observations_provenance",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "conversation_version_id"],
            ["conversation_versions.workspace_id", "conversation_versions.id"],
            name="fk_conversation_version_observations_workspace_version",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "retrieval_observation_id"],
            ["retrieval_observations.workspace_id", "retrieval_observations.id"],
            name="fk_conversation_version_observations_workspace_observation",
        ),
    )
    op.create_index(
        "ix_conversation_version_observations_observation",
        "conversation_version_observations",
        ["retrieval_observation_id"],
    )
    _create_immutability_guards()


def downgrade() -> None:
    bind = op.get_bind()
    counts = {
        table: int(bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in _IMMUTABLE_TABLES
    }
    if any(counts.values()):
        retained = ", ".join(
            f"{table}={count}" for table, count in counts.items() if count
        )
        raise RuntimeError(
            "refusing to downgrade 0014_conversations: immutable Conversation "
            f"history would be lost ({retained})"
        )
    _drop_immutability_guards()
    op.drop_index(
        "ix_conversation_version_observations_observation",
        table_name="conversation_version_observations",
    )
    op.drop_table("conversation_version_observations")
    op.drop_index(
        "ix_conversation_versions_conversation_created_at",
        table_name="conversation_versions",
    )
    op.drop_table("conversation_versions")
    op.drop_index("ix_conversations_workspace_created_at", table_name="conversations")
    op.drop_table("conversations")
