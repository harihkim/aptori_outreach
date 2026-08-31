"""Shared contract tests for the EvidenceStore adapters."""

import os
import stat
import uuid
from pathlib import Path

import pytest

from app.evidence.store import (
    ArtifactInput,
    ArtifactValidationError,
    BundleIntegrityError,
    EvidenceLimitExceeded,
    EvidenceStore,
    EvidenceStoreLimits,
    FinalizedBundle,
    InMemoryEvidenceStore,
    LocalEvidenceStore,
)

WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000042")
OTHER_WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-000000000043")


def _stores(tmp_path: Path) -> list[EvidenceStore]:
    return [
        InMemoryEvidenceStore(),
        LocalEvidenceStore(tmp_path / "local-store"),
    ]


def _artifacts(tmp_path: Path) -> list[ArtifactInput]:
    first = tmp_path / "source-one.json"
    first.write_bytes(b'{"source":"one"}')
    second = tmp_path / "source-two.html"
    second.write_bytes(b"<html>two</html>")
    return [
        ArtifactInput(
            name="raw/one.json",
            role="retrieval-response",
            media_type="application/json",
            path=first,
        ),
        ArtifactInput(
            name="raw/two.html",
            role="page",
            media_type="text/html",
            path=second,
        ),
    ]


def _finalize(store: EvidenceStore, tmp_path: Path) -> FinalizedBundle:
    return store.finalize_bundle(WORKSPACE_ID, _artifacts(tmp_path))


def test_adapters_share_canonical_manifest_and_idempotency(tmp_path: Path) -> None:
    for store in _stores(tmp_path):
        bundle = _finalize(store, tmp_path)
        assert bundle.manifest_version == "evidence-bundle/v1"
        assert bundle.storage_key == (
            f"workspaces/{WORKSPACE_ID}/evidence/{bundle.bundle_sha256}"
        )
        assert bundle.artifact_manifest == {
            "manifest_version": "evidence-bundle/v1",
            "artifacts": [
                {
                    "name": "raw/one.json",
                    "role": "retrieval-response",
                    "sha256": "dedc9de625182c8557dd829c4de7844c72518c21"
                    "e5bd22befacbe90305f7fced",
                    "byte_length": 16,
                    "media_type": "application/json",
                },
                {
                    "name": "raw/two.html",
                    "role": "page",
                    "sha256": "54ce1fcc7cf93fde5190607117dd90d10b1d2fe1"
                    "cab1a2d26f7c23ac0093d836",
                    "byte_length": 16,
                    "media_type": "text/html",
                },
            ],
        }
        # The expected values above should be derived from the bytes, not
        # caller-supplied metadata. Keep the contract assertion explicit.
        assert store.verify_bundle(bundle)
        with store.open_artifact(bundle, "raw/one.json") as artifact:
            assert artifact.read() == b'{"source":"one"}'
        with store.open_artifact(bundle, "raw/two.html") as artifact:
            assert artifact.read() == b"<html>two</html>"

        replay = store.finalize_bundle(WORKSPACE_ID, _artifacts(tmp_path))
        assert replay == bundle
        assert replay.id == bundle.id
        assert replay.bundle_sha256 == bundle.bundle_sha256

        # The public seam intentionally has no destructive operation.
        assert not hasattr(store, "delete_bundle")


def test_same_content_has_same_portable_identity_across_adapters(
    tmp_path: Path,
) -> None:
    memory = InMemoryEvidenceStore()
    local = LocalEvidenceStore(tmp_path / "local-store")
    memory_bundle = _finalize(memory, tmp_path)
    local_bundle = _finalize(local, tmp_path)
    assert local_bundle == memory_bundle
    assert local.verify_bundle(memory_bundle)


def test_workspace_isolation_is_part_of_identity(tmp_path: Path) -> None:
    for store in _stores(tmp_path):
        bundle = _finalize(store, tmp_path)
        other = store.finalize_bundle(OTHER_WORKSPACE_ID, _artifacts(tmp_path))
        assert other.id != bundle.id
        assert other.bundle_sha256 == bundle.bundle_sha256
        assert other.storage_key != bundle.storage_key
        assert store.verify_bundle(bundle)
        assert store.verify_bundle(other)

        forged = FinalizedBundle(
            id=bundle.id,
            workspace_id=OTHER_WORKSPACE_ID,
            manifest_version=bundle.manifest_version,
            bundle_sha256=bundle.bundle_sha256,
            storage_key=bundle.storage_key,
            artifact_manifest=bundle.artifact_manifest,
        )
        assert not store.verify_bundle(forged)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/absolute",
        "\\absolute",
        "../escape",
        "nested/../escape",
        "nested//file",
        "nested/./file",
        "C:/drive-file",
        "C:\\drive-file",
        "nul\x00name",
    ],
)
def test_adapters_reject_unsafe_artifact_names(tmp_path: Path, name: str) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    artifact = ArtifactInput(name, "raw", "application/octet-stream", source)
    for store in _stores(tmp_path):
        with pytest.raises(ArtifactValidationError):
            store.finalize_bundle(WORKSPACE_ID, [artifact])


def test_adapters_reject_duplicates_and_invalid_sources(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"content")
    duplicate = [
        ArtifactInput("same", "raw", "text/plain", source),
        ArtifactInput("same", "raw", "text/plain", source),
    ]
    for store in _stores(tmp_path):
        with pytest.raises(ArtifactValidationError):
            store.finalize_bundle(WORKSPACE_ID, duplicate)

        with pytest.raises(ArtifactValidationError):
            store.finalize_bundle(
                WORKSPACE_ID,
                [ArtifactInput("missing", "raw", "text/plain", tmp_path / "missing")],
            )

        symlink = tmp_path / "symlink"
        try:
            symlink.symlink_to(source)
        except (NotImplementedError, OSError):
            pass
        else:
            with pytest.raises(ArtifactValidationError):
                store.finalize_bundle(
                    WORKSPACE_ID,
                    [ArtifactInput("symlink", "raw", "text/plain", symlink)],
                )


def test_adapters_reject_special_files_when_supported(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo"
    try:
        os.mkfifo(fifo)
    except (AttributeError, NotImplementedError, OSError):
        pytest.skip("the test platform cannot create FIFOs")
    source = ArtifactInput("fifo", "raw", "application/octet-stream", fifo)
    for store in _stores(tmp_path):
        with pytest.raises(ArtifactValidationError):
            store.finalize_bundle(WORKSPACE_ID, [source])
    assert stat.S_ISFIFO(fifo.stat().st_mode)


def test_limits_apply_to_count_bytes_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"0123456789")
    artifact = ArtifactInput("source", "raw", "text/plain", source)
    duplicate_source = tmp_path / "duplicate-source"
    duplicate_source.write_bytes(b"duplicate")
    duplicate_artifact = ArtifactInput(
        "duplicate", "raw", "text/plain", duplicate_source
    )
    for limits, artifacts, expected in (
        (
            EvidenceStoreLimits(max_artifacts=1),
            [artifact, duplicate_artifact],
            EvidenceLimitExceeded,
        ),
        (EvidenceStoreLimits(max_artifact_bytes=5), [artifact], EvidenceLimitExceeded),
        (EvidenceStoreLimits(max_total_bytes=5), [artifact], EvidenceLimitExceeded),
        (EvidenceStoreLimits(max_manifest_bytes=1), [artifact], EvidenceLimitExceeded),
    ):
        for store in (
            InMemoryEvidenceStore(limits),
            LocalEvidenceStore(tmp_path / f"local-{limits.max_manifest_bytes}", limits),
        ):
            with pytest.raises(expected):
                store.finalize_bundle(WORKSPACE_ID, artifacts)


def test_local_adapter_detects_tampered_artifact(tmp_path: Path) -> None:
    store = LocalEvidenceStore(tmp_path / "local-store")
    bundle = _finalize(store, tmp_path)
    artifact_path = (
        store.root
        / "workspaces"
        / str(WORKSPACE_ID)
        / "evidence"
        / bundle.bundle_sha256
        / "artifacts"
        / "raw"
        / "one.json"
    )
    artifact_path.write_bytes(b"tampered")
    assert not store.verify_bundle(bundle)
    with pytest.raises(BundleIntegrityError):
        store.open_artifact(bundle, "raw/one.json")


def test_local_adapter_survives_store_relocation(tmp_path: Path) -> None:
    original_root = tmp_path / "original-store"
    store = LocalEvidenceStore(original_root)
    bundle = _finalize(store, tmp_path)

    relocated_root = tmp_path / "relocated-store"
    original_root.rename(relocated_root)
    relocated = LocalEvidenceStore(relocated_root)

    assert relocated.verify_bundle(bundle)
    with relocated.open_artifact(bundle, "raw/one.json") as artifact:
        assert artifact.read() == b'{"source":"one"}'


def test_local_adapter_rejects_storage_symlink_without_following_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "local-store"
    outside = tmp_path / "outside"
    outside.mkdir()
    store = LocalEvidenceStore(root)
    (root / "workspaces").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BundleIntegrityError):
        _finalize(store, tmp_path)
    assert list(outside.iterdir()) == []


def test_local_adapter_does_not_publish_partial_bundle_on_rename_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "local-store"
    store = LocalEvidenceStore(root)

    def fail_rename(
        _source: str | bytes | os.PathLike[str],
        _destination: str | bytes | os.PathLike[str],
    ) -> None:
        raise OSError("simulated atomic publication failure")

    monkeypatch.setattr(os, "rename", fail_rename)
    with pytest.raises(OSError, match="simulated atomic publication failure"):
        _finalize(store, tmp_path)

    destination_parent = root / "workspaces" / str(WORKSPACE_ID) / "evidence"
    assert list(destination_parent.iterdir()) == []
