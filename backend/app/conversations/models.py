"""Workspace-owned Conversation identity, Versions, and evidence provenance."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.discovery.models import RetrievalObservation  # noqa: F401
from app.orm import Base


class Conversation(Base):
    """Stable identity of one source discussion inside one Workspace."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_conversations_workspace_id_id"),
        UniqueConstraint(
            "workspace_id",
            "source_platform",
            "canonical_external_discussion_id",
            name="uq_conversations_workspace_source_external_id",
        ),
        CheckConstraint(
            "source_platform = lower(source_platform) AND length(source_platform) > 0",
            name="source_platform_canonical",
        ),
        CheckConstraint(
            "length(canonical_external_discussion_id) > 0",
            name="external_discussion_id_nonempty",
        ),
        Index("ix_conversations_workspace_created_at", "workspace_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    source_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_external_discussion_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConversationVersion(Base):
    """Immutable normalized content produced by one named normalizer."""

    __tablename__ = "conversation_versions"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_conversation_versions_workspace_id_id",
        ),
        UniqueConstraint(
            "conversation_id",
            "normalizer_version",
            "normalized_content_sha256",
            name="uq_conversation_versions_identity",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_id"],
            ["conversations.workspace_id", "conversations.id"],
            name="fk_conversation_versions_workspace_conversation",
        ),
        CheckConstraint(
            "length(normalizer_version) > 0",
            name="normalizer_version_nonempty",
        ),
        CheckConstraint(
            "normalized_sha256 ~ '^[0-9a-f]{64}$'",
            name="normalized_sha256_format",
        ),
        CheckConstraint(
            "normalized_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="normalized_content_sha256_format",
        ),
        Index(
            "ix_conversation_versions_conversation_created_at",
            "conversation_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    source_tree_exhausted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ConversationVersionObservation(Base):
    """Immutable provenance edge from a Version to retained raw evidence."""

    __tablename__ = "conversation_version_observations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "id",
            name="uq_conversation_version_observations_workspace_id_id",
        ),
        UniqueConstraint(
            "conversation_version_id",
            "retrieval_observation_id",
            name="uq_conversation_version_observations_provenance",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "conversation_version_id"],
            ["conversation_versions.workspace_id", "conversation_versions.id"],
            name="fk_conversation_version_observations_workspace_version",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "retrieval_observation_id"],
            ["retrieval_observations.workspace_id", "retrieval_observations.id"],
            name="fk_conversation_version_observations_workspace_observation",
        ),
        Index(
            "ix_conversation_version_observations_observation",
            "retrieval_observation_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    conversation_version_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    retrieval_observation_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
