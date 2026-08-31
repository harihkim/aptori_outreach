"""ORM model for immutable, Workspace-owned Evidence Bundles."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.orm import Base

EVIDENCE_BUNDLE_MANIFEST_VERSION = "evidence-bundle/v1"
EVIDENCE_STATES = ("bundle", "legacy", "none")


class EvidenceBundle(Base):
    """One immutable raw-evidence bundle and its canonical manifest."""

    __tablename__ = "evidence_bundles"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "id", name="uq_evidence_bundles_workspace_id_id"
        ),
        UniqueConstraint(
            "workspace_id",
            "bundle_sha256",
            name="uq_evidence_bundles_workspace_bundle_sha256",
        ),
        UniqueConstraint(
            "workspace_id",
            "storage_key",
            name="uq_evidence_bundles_workspace_storage_key",
        ),
        CheckConstraint(
            f"manifest_version = '{EVIDENCE_BUNDLE_MANIFEST_VERSION}'",
            name="manifest_version_values",
        ),
        Index("ix_evidence_bundles_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False
    )
    manifest_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=EVIDENCE_BUNDLE_MANIFEST_VERSION,
        server_default=EVIDENCE_BUNDLE_MANIFEST_VERSION,
    )
    bundle_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
