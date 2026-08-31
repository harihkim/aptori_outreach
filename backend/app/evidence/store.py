"""Portable, immutable Evidence Bundle storage.

The storage seam deliberately exposes only finalization, artifact opening, and
verification. The adapters own validation, canonicalization, integrity checks,
limits, and atomic publication so callers do not need storage-specific
knowledge.
"""

from __future__ import annotations

import hashlib
import io
import json
import operator
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Sequence
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO, Protocol, cast, runtime_checkable

from app.evidence.models import EVIDENCE_BUNDLE_MANIFEST_VERSION

_CHUNK_SIZE = 1024 * 1024
_DIGEST_LENGTH = hashlib.sha256().digest_size * 2
_DESCRIPTOR_KEYS = frozenset({"name", "role", "sha256", "byte_length", "media_type"})
_BUNDLE_ID_NAMESPACE = uuid.UUID("f5e0ab8c-97e8-4b02-a8f2-c919a2cbbf8d")


class EvidenceStoreError(RuntimeError):
    """Base error for storage and bundle-integrity failures."""


class ArtifactValidationError(ValueError):
    """An input artifact or finalized manifest is invalid."""


class EvidenceLimitExceeded(ArtifactValidationError):
    """A configured bundle safety limit was exceeded."""


class BundleNotFound(LookupError):
    """The requested bundle or artifact is not available."""


class BundleIntegrityError(EvidenceStoreError):
    """A finalized bundle or stored artifact failed integrity checks."""


@dataclass(frozen=True, slots=True)
class EvidenceStoreLimits:
    """Explicit count, artifact, total, and manifest safety limits."""

    max_artifacts: int = 128
    max_artifact_bytes: int = 128 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_manifest_bytes: int = 1024 * 1024
    max_name_bytes: int = 255
    max_role_bytes: int = 128
    max_media_type_bytes: int = 255

    def __post_init__(self) -> None:
        for field_name in (
            "max_artifacts",
            "max_artifact_bytes",
            "max_total_bytes",
            "max_manifest_bytes",
            "max_name_bytes",
            "max_role_bytes",
            "max_media_type_bytes",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ArtifactInput:
    """A caller-owned regular file to include in a bundle."""

    name: str
    role: str
    media_type: str
    path: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """The path-free descriptor retained in a canonical manifest."""

    name: str
    role: str
    sha256: str
    byte_length: int
    media_type: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "role": self.role,
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "media_type": self.media_type,
        }


@dataclass(frozen=True, slots=True)
class FinalizedBundle:
    """Identity and canonical manifest of one immutable Evidence Bundle."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    manifest_version: str
    bundle_sha256: str
    storage_key: str
    artifact_manifest: dict[str, object]


@runtime_checkable
class EvidenceStore(Protocol):
    """The three-operation Evidence Bundle storage interface."""

    def finalize_bundle(
        self, workspace_id: uuid.UUID, artifacts: Sequence[ArtifactInput]
    ) -> FinalizedBundle:
        """Validate, digest, and atomically publish an immutable bundle."""

    def open_artifact(self, bundle: FinalizedBundle, name: str) -> BinaryIO:
        """Open one verified artifact from a finalized bundle."""

    def verify_bundle(self, bundle: FinalizedBundle) -> bool:
        """Return whether the bundle identity, manifest, and content verify."""


def _canonical_manifest(manifest: dict[str, object]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_workspace(workspace_id: uuid.UUID) -> None:
    if not isinstance(workspace_id, uuid.UUID):
        raise ArtifactValidationError("workspace_id must be a UUID")


def _validate_text(value: str, field_name: str, max_bytes: int) -> str:
    if not isinstance(value, str) or not value:
        raise ArtifactValidationError(f"{field_name} must be a non-empty string")
    if "\x00" in value:
        raise ArtifactValidationError(f"{field_name} may not contain NUL")
    if len(value.encode("utf-8")) > max_bytes:
        raise EvidenceLimitExceeded(f"{field_name} exceeds {max_bytes} bytes")
    return value


def _validate_name(name: str, limits: EvidenceStoreLimits) -> str:
    """Accept canonical relative POSIX names, never filesystem paths."""
    _validate_text(name, "artifact name", limits.max_name_bytes)
    if name.startswith(("/", "\\")):
        raise ArtifactValidationError("artifact name must not be absolute")
    posix = PurePosixPath(name)
    windows = PureWindowsPath(name)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ArtifactValidationError("artifact name must not be absolute")
    if "\\" in name:
        raise ArtifactValidationError("artifact name must use '/' separators")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ArtifactValidationError(
            "artifact name may not contain empty, '.', or '..' path segments"
        )
    if "/".join(parts) != name:
        raise ArtifactValidationError("artifact name is not canonical")
    return name


def _validate_inputs(
    artifacts: Sequence[ArtifactInput], limits: EvidenceStoreLimits
) -> tuple[ArtifactInput, ...]:
    inputs: list[ArtifactInput] = []
    names: set[str] = set()
    for artifact in artifacts:
        name = _validate_name(artifact.name, limits)
        _validate_text(artifact.role, "artifact role", limits.max_role_bytes)
        _validate_text(
            artifact.media_type, "artifact media_type", limits.max_media_type_bytes
        )
        if name in names:
            raise ArtifactValidationError("artifact names must be unique")
        names.add(name)
        inputs.append(
            ArtifactInput(name, artifact.role, artifact.media_type, artifact.path)
        )
    if not inputs:
        raise EvidenceLimitExceeded("an Evidence Bundle needs at least one artifact")
    if len(inputs) > limits.max_artifacts:
        raise EvidenceLimitExceeded(
            f"bundle has {len(inputs)} artifacts; limit is {limits.max_artifacts}"
        )
    return tuple(inputs)


def _open_source(path: Path) -> int:
    try:
        source_stat = path.lstat()
    except OSError as error:
        raise ArtifactValidationError(
            f"artifact source is unreadable: {path}"
        ) from error
    if stat.S_ISLNK(source_stat.st_mode):
        raise ArtifactValidationError(f"artifact source may not be a symlink: {path}")
    if not stat.S_ISREG(source_stat.st_mode):
        raise ArtifactValidationError(f"artifact source must be a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return os.open(path, flags)
    except OSError as error:
        raise ArtifactValidationError(
            f"artifact source is unreadable: {path}"
        ) from error


def _file_fingerprint(file_stat: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _check_sizes(
    byte_length: int, total_before: int, limits: EvidenceStoreLimits
) -> None:
    if byte_length > limits.max_artifact_bytes:
        raise EvidenceLimitExceeded(
            f"artifact is {byte_length} bytes; limit is {limits.max_artifact_bytes}"
        )
    if total_before + byte_length > limits.max_total_bytes:
        raise EvidenceLimitExceeded(
            f"bundle exceeds {limits.max_total_bytes} total bytes"
        )


def _read_source(
    artifact: ArtifactInput,
    limits: EvidenceStoreLimits,
    total_before: int,
    destination: Path | None = None,
) -> tuple[ArtifactDescriptor, bytes]:
    """Read one source, optionally copying it to a staged local artifact."""
    source_fd = _open_source(artifact.path)
    target_path = destination
    source: BinaryIO | None = None
    target: BinaryIO | None = None
    chunks: list[bytes] = []
    digest = hashlib.sha256()
    byte_length = 0
    completed = False
    try:
        source = os.fdopen(source_fd, "rb")
        initial = os.fstat(source.fileno())
        _check_sizes(initial.st_size, total_before, limits)
        initial_fingerprint = _file_fingerprint(initial)
        if target_path is not None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_fd = os.open(
                target_path,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            target = os.fdopen(target_fd, "wb")
        while chunk := source.read(_CHUNK_SIZE):
            byte_length += len(chunk)
            _check_sizes(byte_length, total_before, limits)
            digest.update(chunk)
            if target is not None:
                target.write(chunk)
            else:
                chunks.append(chunk)
        if target is not None:
            target.flush()
            os.fsync(target.fileno())
        final = os.fstat(source.fileno())
        if _file_fingerprint(final) != initial_fingerprint:
            raise ArtifactValidationError(
                f"artifact source changed while reading: {artifact.path}"
            )
        try:
            path_after = artifact.path.lstat()
        except OSError as error:
            raise ArtifactValidationError(
                f"artifact source changed while reading: {artifact.path}"
            ) from error
        if _file_fingerprint(path_after) != initial_fingerprint:
            raise ArtifactValidationError(
                f"artifact source changed while reading: {artifact.path}"
            )
        completed = True
    except EvidenceStoreError:
        raise
    except OSError as error:
        raise ArtifactValidationError(
            f"artifact source or destination could not be read/written: {artifact.path}"
        ) from error
    finally:
        if target is not None:
            with suppress(OSError):
                target.close()
        if target_path is not None and not completed:
            with suppress(OSError):
                target_path.unlink()
        if source is not None:
            with suppress(OSError):
                source.close()
    descriptor = ArtifactDescriptor(
        name=artifact.name,
        role=artifact.role,
        sha256=digest.hexdigest(),
        byte_length=byte_length,
        media_type=artifact.media_type,
    )
    return descriptor, b"".join(chunks)


def _manifest_for(
    descriptors: Sequence[ArtifactDescriptor], limits: EvidenceStoreLimits
) -> tuple[dict[str, object], str]:
    manifest: dict[str, object] = {
        "manifest_version": EVIDENCE_BUNDLE_MANIFEST_VERSION,
        "artifacts": [
            descriptor.as_dict()
            for descriptor in sorted(descriptors, key=operator.attrgetter("name"))
        ],
    }
    encoded = _canonical_manifest(manifest)
    if len(encoded) > limits.max_manifest_bytes:
        raise EvidenceLimitExceeded(
            f"canonical manifest is {len(encoded)} bytes; "
            f"limit is {limits.max_manifest_bytes}"
        )
    return manifest, hashlib.sha256(encoded).hexdigest()


def _descriptors_from_manifest(
    manifest: object, limits: EvidenceStoreLimits
) -> tuple[ArtifactDescriptor, ...] | None:
    if not isinstance(manifest, dict) or set(manifest) != {
        "manifest_version",
        "artifacts",
    }:
        return None
    if manifest.get("manifest_version") != EVIDENCE_BUNDLE_MANIFEST_VERSION:
        return None
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        return None
    if len(raw_artifacts) > limits.max_artifacts:
        return None
    descriptors: list[ArtifactDescriptor] = []
    names: set[str] = set()
    total = 0
    for raw in raw_artifacts:
        if not isinstance(raw, dict) or set(raw) != _DESCRIPTOR_KEYS:
            return None
        name = raw.get("name")
        role = raw.get("role")
        digest = raw.get("sha256")
        byte_length = raw.get("byte_length")
        media_type = raw.get("media_type")
        try:
            if not isinstance(name, str):
                return None
            _validate_name(name, limits)
            if not isinstance(role, str):
                return None
            _validate_text(role, "artifact role", limits.max_role_bytes)
            if not isinstance(digest, str) or len(digest) != _DIGEST_LENGTH:
                return None
            if any(character not in "0123456789abcdef" for character in digest):
                return None
            if (
                not isinstance(byte_length, int)
                or isinstance(byte_length, bool)
                or byte_length < 0
            ):
                return None
            _check_sizes(byte_length, total, limits)
            if not isinstance(media_type, str):
                return None
            _validate_text(
                media_type, "artifact media_type", limits.max_media_type_bytes
            )
        except ArtifactValidationError:
            return None
        if name in names:
            return None
        names.add(name)
        total += byte_length
        descriptors.append(
            ArtifactDescriptor(name, role, digest, byte_length, media_type)
        )
    ordered = tuple(sorted(descriptors, key=operator.attrgetter("name")))
    canonical, _digest = _manifest_for(ordered, limits)
    return ordered if canonical == manifest else None


def _bundle_id(workspace_id: uuid.UUID, bundle_sha256: str) -> uuid.UUID:
    return uuid.uuid5(_BUNDLE_ID_NAMESPACE, f"{workspace_id}:{bundle_sha256}")


def _storage_key(workspace_id: uuid.UUID, bundle_sha256: str) -> str:
    return f"workspaces/{workspace_id}/evidence/{bundle_sha256}"


def _make_bundle(
    workspace_id: uuid.UUID, manifest: dict[str, object], bundle_sha256: str
) -> FinalizedBundle:
    return FinalizedBundle(
        id=_bundle_id(workspace_id, bundle_sha256),
        workspace_id=workspace_id,
        manifest_version=EVIDENCE_BUNDLE_MANIFEST_VERSION,
        bundle_sha256=bundle_sha256,
        storage_key=_storage_key(workspace_id, bundle_sha256),
        artifact_manifest=manifest,
    )


def _descriptor_map(
    manifest: dict[str, object], limits: EvidenceStoreLimits
) -> dict[str, ArtifactDescriptor] | None:
    descriptors = _descriptors_from_manifest(manifest, limits)
    return (
        {descriptor.name: descriptor for descriptor in descriptors}
        if descriptors is not None
        else None
    )


def _validate_bundle(bundle: FinalizedBundle, limits: EvidenceStoreLimits) -> None:
    if not isinstance(bundle, FinalizedBundle):
        raise ArtifactValidationError("bundle has an invalid type")
    _validate_workspace(bundle.workspace_id)
    if bundle.manifest_version != EVIDENCE_BUNDLE_MANIFEST_VERSION:
        raise ArtifactValidationError("bundle manifest version is unsupported")
    if (
        not isinstance(bundle.bundle_sha256, str)
        or len(bundle.bundle_sha256) != _DIGEST_LENGTH
        or any(
            character not in "0123456789abcdef" for character in bundle.bundle_sha256
        )
    ):
        raise ArtifactValidationError(
            "bundle_sha256 must be a lowercase SHA-256 digest"
        )
    if bundle.storage_key != _storage_key(bundle.workspace_id, bundle.bundle_sha256):
        raise ArtifactValidationError("bundle storage key is not Workspace-scoped")
    if bundle.id != _bundle_id(bundle.workspace_id, bundle.bundle_sha256):
        raise ArtifactValidationError("bundle id does not match its identity")
    descriptors = _descriptors_from_manifest(bundle.artifact_manifest, limits)
    if descriptors is None:
        raise ArtifactValidationError("bundle manifest is not canonical")
    if bundle.artifact_manifest.get("manifest_version") != bundle.manifest_version:
        raise ArtifactValidationError("bundle manifest version does not match")
    encoded = _canonical_manifest(bundle.artifact_manifest)
    if hashlib.sha256(encoded).hexdigest() != bundle.bundle_sha256:
        raise ArtifactValidationError("bundle manifest digest does not match")


def _verify_bytes(
    bundle: FinalizedBundle,
    contents: dict[str, bytes],
    limits: EvidenceStoreLimits,
) -> bool:
    try:
        _validate_bundle(bundle, limits)
        descriptors = _descriptor_map(bundle.artifact_manifest, limits)
        if descriptors is None or set(contents) != set(descriptors):
            return False
        for name, descriptor in descriptors.items():
            content = contents[name]
            if len(content) != descriptor.byte_length:
                return False
            if hashlib.sha256(content).hexdigest() != descriptor.sha256:
                return False
    except (ArtifactValidationError, TypeError, ValueError, UnicodeError):
        return False
    return True


def _bundle_key(bundle: FinalizedBundle) -> tuple[uuid.UUID, str]:
    return bundle.workspace_id, bundle.bundle_sha256


class InMemoryEvidenceStore:
    """Deterministic adapter for development and contract tests."""

    def __init__(self, limits: EvidenceStoreLimits | None = None) -> None:
        self.limits = limits or EvidenceStoreLimits()
        self._bundles: dict[tuple[uuid.UUID, str], FinalizedBundle] = {}
        self._contents: dict[tuple[uuid.UUID, str], dict[str, bytes]] = {}

    def finalize_bundle(
        self, workspace_id: uuid.UUID, artifacts: Sequence[ArtifactInput]
    ) -> FinalizedBundle:
        _validate_workspace(workspace_id)
        inputs = _validate_inputs(artifacts, self.limits)
        descriptors: list[ArtifactDescriptor] = []
        contents: dict[str, bytes] = {}
        total = 0
        for artifact in inputs:
            descriptor, content = _read_source(artifact, self.limits, total)
            total += descriptor.byte_length
            descriptors.append(descriptor)
            contents[descriptor.name] = content
        manifest, digest = _manifest_for(descriptors, self.limits)
        key = (workspace_id, digest)
        existing = self._bundles.get(key)
        if existing is not None:
            if not self.verify_bundle(existing):
                raise BundleIntegrityError(
                    f"existing bundle {existing.id} failed verification"
                )
            return existing
        bundle = _make_bundle(workspace_id, manifest, digest)
        self._bundles[key] = FinalizedBundle(
            bundle.id,
            bundle.workspace_id,
            bundle.manifest_version,
            bundle.bundle_sha256,
            bundle.storage_key,
            deepcopy(bundle.artifact_manifest),
        )
        self._contents[key] = contents
        return bundle

    def open_artifact(self, bundle: FinalizedBundle, name: str) -> BinaryIO:
        try:
            _validate_bundle(bundle, self.limits)
        except (ArtifactValidationError, TypeError, ValueError) as error:
            raise BundleIntegrityError("bundle identity is invalid") from error
        logical_name = _validate_name(name, self.limits)
        key = _bundle_key(bundle)
        stored = self._bundles.get(key)
        if stored is None or stored != bundle:
            raise BundleNotFound(f"bundle {bundle.id} is not present")
        if not self.verify_bundle(bundle):
            raise BundleIntegrityError(f"bundle {bundle.id} failed verification")
        descriptors = _descriptor_map(bundle.artifact_manifest, self.limits)
        if descriptors is None or logical_name not in descriptors:
            raise BundleNotFound(
                f"artifact {logical_name!r} is not in bundle {bundle.id}"
            )
        return io.BytesIO(self._contents[key][logical_name])

    def verify_bundle(self, bundle: FinalizedBundle) -> bool:
        try:
            key = _bundle_key(bundle)
            stored = self._bundles.get(key)
            contents = self._contents.get(key)
        except (AttributeError, TypeError):
            return False
        if stored is None or contents is None or stored != bundle:
            return False
        return _verify_bytes(bundle, contents, self.limits)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_tree(path: Path) -> None:
    for directory, subdirectories, filenames in os.walk(path, followlinks=False):
        directory_path = Path(directory)
        for child in (*subdirectories, *filenames):
            child_path = directory_path / child
            try:
                child_stat = child_path.lstat()
            except OSError as error:
                raise BundleIntegrityError(
                    "staging tree could not be inspected"
                ) from error
            if stat.S_ISLNK(child_stat.st_mode):
                raise BundleIntegrityError("staging tree contains a symlink")
        _fsync_directory(directory_path)


def _safe_regular_file(path: Path) -> BinaryIO:
    try:
        source_stat = path.lstat()
    except OSError as error:
        raise BundleNotFound(str(path)) from error
    if stat.S_ISLNK(source_stat.st_mode) or not stat.S_ISREG(source_stat.st_mode):
        raise BundleIntegrityError(f"stored artifact is not a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as error:
        raise BundleIntegrityError(f"stored artifact is unreadable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BundleIntegrityError(f"stored artifact is not a regular file: {path}")
        return os.fdopen(fd, "rb")
    except BaseException:
        os.close(fd)
        raise


def _ensure_directory(path: Path) -> None:
    """Create a directory chain without following a symlink component."""
    current = Path(path.anchor) if path.anchor else Path()
    for part in path.parts:
        if current == Path() and part == path.anchor:
            continue
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            current.mkdir()
            mode = current.lstat().st_mode
        except OSError as error:
            raise BundleIntegrityError(
                f"storage directory is inaccessible: {current}"
            ) from error
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise BundleIntegrityError(f"storage path is not a directory: {current}")


class LocalEvidenceStore:
    """Filesystem adapter using Workspace-prefixed content-addressed keys."""

    def __init__(self, root: Path, limits: EvidenceStoreLimits | None = None) -> None:
        root_path = Path(root)
        self.limits = limits or EvidenceStoreLimits()
        root_path.mkdir(parents=True, exist_ok=True)
        if not root_path.is_dir() or root_path.is_symlink():
            raise ValueError(f"EvidenceStore root is not a directory: {root_path}")
        self.root = root_path.resolve()

    def _bundle_path(self, bundle: FinalizedBundle) -> Path:
        try:
            _validate_bundle(bundle, self.limits)
        except (ArtifactValidationError, TypeError, ValueError) as error:
            raise BundleIntegrityError("bundle storage identity is invalid") from error
        candidate = self.root.joinpath(*bundle.storage_key.split("/"))
        try:
            candidate.relative_to(self.root)
        except ValueError as error:
            raise BundleIntegrityError(
                "bundle storage key escapes the store root"
            ) from error
        current = self.root
        for part in candidate.relative_to(self.root).parts:
            current /= part
            try:
                if stat.S_ISLNK(current.lstat().st_mode):
                    raise BundleIntegrityError("bundle storage path contains a symlink")
            except FileNotFoundError:
                break
        return candidate

    def _read_manifest(self, bundle_path: Path) -> dict[str, object]:
        with _safe_regular_file(bundle_path / "manifest.json") as manifest_file:
            encoded = manifest_file.read(self.limits.max_manifest_bytes + 1)
        if len(encoded) > self.limits.max_manifest_bytes:
            raise BundleIntegrityError("stored manifest exceeds configured limit")
        try:
            manifest = json.loads(encoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise BundleIntegrityError("stored manifest is not valid JSON") from error
        if _descriptors_from_manifest(manifest, self.limits) is None:
            raise BundleIntegrityError("stored manifest is not canonical")
        return cast(dict[str, object], manifest)

    def _load_existing(self, bundle: FinalizedBundle) -> FinalizedBundle:
        self._read_manifest(self._bundle_path(bundle))
        if not self.verify_bundle(bundle):
            raise BundleIntegrityError(
                f"existing bundle {bundle.id} failed verification"
            )
        return bundle

    def _stored_contents(
        self, bundle: FinalizedBundle
    ) -> tuple[dict[str, bytes], dict[str, ArtifactDescriptor]] | None:
        try:
            bundle_path = self._bundle_path(bundle)
            entries = list(bundle_path.iterdir())
        except (BundleIntegrityError, OSError):
            return None
        if {entry.name for entry in entries} != {"manifest.json", "artifacts"}:
            return None
        if any(entry.is_symlink() for entry in entries):
            return None
        try:
            manifest = self._read_manifest(bundle_path)
        except (BundleIntegrityError, BundleNotFound):
            return None
        if manifest != bundle.artifact_manifest:
            return None
        descriptors = _descriptor_map(manifest, self.limits)
        artifact_root = bundle_path / "artifacts"
        if (
            descriptors is None
            or not artifact_root.is_dir()
            or artifact_root.is_symlink()
        ):
            return None
        actual_names: set[str] = set()
        try:
            for directory, subdirectories, filenames in os.walk(
                artifact_root, followlinks=False
            ):
                directory_path = Path(directory)
                for child in subdirectories:
                    child_path = directory_path / child
                    child_stat = child_path.lstat()
                    if stat.S_ISLNK(child_stat.st_mode) or not stat.S_ISDIR(
                        child_stat.st_mode
                    ):
                        return None
                for filename in filenames:
                    child_path = directory_path / filename
                    child_stat = child_path.lstat()
                    if stat.S_ISLNK(child_stat.st_mode) or not stat.S_ISREG(
                        child_stat.st_mode
                    ):
                        return None
                    actual_names.add(child_path.relative_to(artifact_root).as_posix())
        except OSError:
            return None
        if actual_names != set(descriptors):
            return None
        contents: dict[str, bytes] = {}
        for name in actual_names:
            try:
                _validate_name(name, self.limits)
                with _safe_regular_file(
                    artifact_root.joinpath(*name.split("/"))
                ) as file:
                    content = file.read(self.limits.max_artifact_bytes + 1)
            except (
                ArtifactValidationError,
                BundleIntegrityError,
                BundleNotFound,
                OSError,
            ):
                return None
            if len(content) > self.limits.max_artifact_bytes:
                return None
            contents[name] = content
        return contents, descriptors

    def finalize_bundle(
        self, workspace_id: uuid.UUID, artifacts: Sequence[ArtifactInput]
    ) -> FinalizedBundle:
        _validate_workspace(workspace_id)
        inputs = _validate_inputs(artifacts, self.limits)
        descriptors: list[ArtifactDescriptor] = []
        total = 0
        # The temporary bundle is created beside its final content-addressed
        # directory. Copying from any source filesystem is safe, while
        # publication remains one same-filesystem atomic rename.
        destination_parent = self.root / "workspaces" / str(workspace_id) / "evidence"
        _ensure_directory(destination_parent)
        staging = Path(
            tempfile.mkdtemp(prefix=".evidence-bundle-", dir=destination_parent)
        )
        moved = False
        try:
            artifact_root = staging / "artifacts"
            artifact_root.mkdir()
            for artifact in inputs:
                descriptor, _unused = _read_source(
                    artifact,
                    self.limits,
                    total,
                    artifact_root.joinpath(*artifact.name.split("/")),
                )
                total += descriptor.byte_length
                descriptors.append(descriptor)
            manifest, digest = _manifest_for(descriptors, self.limits)
            manifest_path = staging / "manifest.json"
            manifest_bytes = _canonical_manifest(manifest)
            with manifest_path.open("xb") as manifest_file:
                manifest_file.write(manifest_bytes)
                manifest_file.flush()
                os.fsync(manifest_file.fileno())
            _fsync_tree(staging)
            bundle = _make_bundle(workspace_id, manifest, digest)
            destination = self._bundle_path(bundle)
            if destination.exists() or destination.is_symlink():
                return self._load_existing(bundle)
            try:
                os.rename(staging, destination)
                moved = True
            except FileExistsError:
                return self._load_existing(bundle)
            _fsync_directory(destination.parent)
            return bundle
        finally:
            if not moved and staging.exists():
                shutil.rmtree(staging)

    def open_artifact(self, bundle: FinalizedBundle, name: str) -> BinaryIO:
        try:
            _validate_bundle(bundle, self.limits)
        except (ArtifactValidationError, TypeError, ValueError) as error:
            raise BundleIntegrityError("bundle identity is invalid") from error
        logical_name = _validate_name(name, self.limits)
        if not self.verify_bundle(bundle):
            raise BundleIntegrityError(f"bundle {bundle.id} failed verification")
        descriptors = _descriptor_map(bundle.artifact_manifest, self.limits)
        if descriptors is None or logical_name not in descriptors:
            raise BundleNotFound(
                f"artifact {logical_name!r} is not in bundle {bundle.id}"
            )
        return _safe_regular_file(
            self._bundle_path(bundle) / "artifacts" / Path(*logical_name.split("/"))
        )

    def verify_bundle(self, bundle: FinalizedBundle) -> bool:
        try:
            _validate_bundle(bundle, self.limits)
            stored = self._stored_contents(bundle)
        except (ArtifactValidationError, BundleIntegrityError, TypeError, ValueError):
            return False
        if stored is None:
            return False
        contents, _descriptors = stored
        return _verify_bytes(bundle, contents, self.limits)
