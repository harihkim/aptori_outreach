"""Conversation persistence, replay, provenance, and current-version reads."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.conversations.models import (
    Conversation,
    ConversationVersion,
    ConversationVersionObservation,
)
from app.conversations.normalizer import (
    NORMALIZER_VERSION,
    NormalizationError,
    NormalizedThread,
    normalize_reddit_thread,
)
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.evidence.models import EvidenceBundle
from app.evidence.store import EvidenceStore, FinalizedBundle

_CONVERSATION_NAMESPACE = uuid.UUID("a6364574-5df2-46ae-a1bd-1a135f12b4c5")
_VERSION_NAMESPACE = uuid.UUID("547720a9-8fed-487d-a67e-67460aa444b6")
_PROVENANCE_NAMESPACE = uuid.UUID("bfac70b1-04e0-463f-990c-4befc9f446d1")


@dataclass(frozen=True, slots=True)
class NormalizationRecord:
    conversation: Conversation
    version: ConversationVersion
    provenance: ConversationVersionObservation
    version_created: bool
    provenance_created: bool


@dataclass(frozen=True, slots=True)
class CandidateTransition:
    external_source_id: str
    url: str
    title: str
    rank: int | None
    retrieval_status: str | None
    conversation: Conversation | None
    current_version: ConversationVersion | None


@dataclass(frozen=True, slots=True)
class RunConversationTransitions:
    items: list[CandidateTransition]
    expected_count: int
    fetched_count: int
    normalized_count: int
    processing_complete: bool


def conversation_id_for(
    workspace_id: uuid.UUID, source_platform: str, external_discussion_id: str
) -> uuid.UUID:
    canonical_platform = source_platform.strip().lower()
    if not canonical_platform or not external_discussion_id:
        raise ValueError("Conversation identity components must be non-empty")
    return uuid.uuid5(
        _CONVERSATION_NAMESPACE,
        f"{workspace_id}\0{canonical_platform}\0{external_discussion_id}",
    )


def _version_id_for(
    conversation_id: uuid.UUID, normalizer_version: str, content_sha256: str
) -> uuid.UUID:
    return uuid.uuid5(
        _VERSION_NAMESPACE,
        f"{conversation_id}\0{normalizer_version}\0{content_sha256}",
    )


def _provenance_id_for(version_id: uuid.UUID, observation_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_PROVENANCE_NAMESPACE, f"{version_id}\0{observation_id}")


def _finalized_bundle(row: EvidenceBundle) -> FinalizedBundle:
    return FinalizedBundle(
        id=row.id,
        workspace_id=row.workspace_id,
        manifest_version=row.manifest_version,
        bundle_sha256=row.bundle_sha256,
        storage_key=row.storage_key,
        artifact_manifest=row.artifact_manifest,
    )


def _artifact_name(observation: RetrievalObservation) -> str:
    raw = observation.raw_artifact
    if not isinstance(raw, dict):
        raise NormalizationError("bundle-backed observation has no raw descriptor")
    name = raw.get("name")
    role = raw.get("role")
    if not isinstance(name, str) or not name or role != "raw":
        raise NormalizationError("bundle-backed observation raw descriptor is invalid")
    return name


def _load_normalized(
    store: EvidenceStore,
    observation: RetrievalObservation,
    bundle_row: EvidenceBundle,
    normalizer_version: str,
) -> NormalizedThread:
    bundle = _finalized_bundle(bundle_row)
    if not store.verify_bundle(bundle):
        raise NormalizationError("Evidence Bundle failed verification")
    name = _artifact_name(observation)
    try:
        with store.open_artifact(bundle, name) as artifact:
            payload = json.load(artifact)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NormalizationError("raw evidence is not valid readable JSON") from error
    normalized = normalize_reddit_thread(payload, normalizer_version=normalizer_version)
    if normalized.root_external_source_id != observation.external_source_id:
        raise NormalizationError(
            "raw evidence root identity does not match its Retrieval Observation"
        )
    # These hashes are a non-authoritative subprocess projection. Comparing
    # them after replay detects cross-runtime drift without using them as input.
    if (
        observation.normalized_sha256 is not None
        and observation.normalized_sha256 != normalized.normalized_sha256
    ):
        raise NormalizationError(
            "normalized hash disagrees with frozen fetch projection"
        )
    if (
        observation.normalized_content_sha256 is not None
        and observation.normalized_content_sha256
        != normalized.normalized_content_sha256
    ):
        raise NormalizationError(
            "normalized content hash disagrees with frozen fetch projection"
        )
    return normalized


def _get_or_create_conversation(
    session: Session,
    workspace_id: uuid.UUID,
    source_platform: str,
    external_discussion_id: str,
) -> Conversation:
    conversation_id = conversation_id_for(
        workspace_id, source_platform, external_discussion_id
    )
    existing = session.get(Conversation, conversation_id)
    if existing is not None:
        if (
            existing.workspace_id != workspace_id
            or existing.source_platform != source_platform
            or existing.canonical_external_discussion_id != external_discussion_id
        ):
            raise RuntimeError("deterministic Conversation identity conflict")
        return existing
    row = Conversation(
        id=conversation_id,
        workspace_id=workspace_id,
        source_platform=source_platform,
        canonical_external_discussion_id=external_discussion_id,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.source_platform == source_platform,
                Conversation.canonical_external_discussion_id == external_discussion_id,
            )
        )
        if existing is None or existing.id != conversation_id:
            raise
        return existing
    return row


def _get_or_create_version(
    session: Session,
    conversation: Conversation,
    normalized: NormalizedThread,
) -> tuple[ConversationVersion, bool]:
    version_id = _version_id_for(
        conversation.id,
        normalized.normalizer_version,
        normalized.normalized_content_sha256,
    )
    existing = session.get(ConversationVersion, version_id)
    if existing is not None:
        return existing, False
    row = ConversationVersion(
        id=version_id,
        workspace_id=conversation.workspace_id,
        conversation_id=conversation.id,
        normalizer_version=normalized.normalizer_version,
        normalized_sha256=normalized.normalized_sha256,
        normalized_content_sha256=normalized.normalized_content_sha256,
        normalized_content=cast(dict[str, object], normalized.content),
        source_tree_exhausted=normalized.source_tree_exhausted,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(ConversationVersion).where(
                ConversationVersion.conversation_id == conversation.id,
                ConversationVersion.normalizer_version == normalized.normalizer_version,
                ConversationVersion.normalized_content_sha256
                == normalized.normalized_content_sha256,
            )
        )
        if existing is None or existing.id != version_id:
            raise
        return existing, False
    return row, True


def _get_or_create_provenance(
    session: Session,
    workspace_id: uuid.UUID,
    version_id: uuid.UUID,
    observation_id: uuid.UUID,
) -> tuple[ConversationVersionObservation, bool]:
    provenance_id = _provenance_id_for(version_id, observation_id)
    existing = session.get(ConversationVersionObservation, provenance_id)
    if existing is not None:
        return existing, False
    row = ConversationVersionObservation(
        id=provenance_id,
        workspace_id=workspace_id,
        conversation_version_id=version_id,
        retrieval_observation_id=observation_id,
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(ConversationVersionObservation).where(
                ConversationVersionObservation.conversation_version_id == version_id,
                ConversationVersionObservation.retrieval_observation_id
                == observation_id,
            )
        )
        if existing is None or existing.id != provenance_id:
            raise
        return existing, False
    return row, True


def normalize_observation(
    session: Session,
    store: EvidenceStore,
    workspace_id: uuid.UUID,
    observation_id: uuid.UUID,
    *,
    normalizer_version: str = NORMALIZER_VERSION,
) -> NormalizationRecord:
    """Replay one already-committed bundle observation into canonical state."""
    observation = session.scalar(
        select(RetrievalObservation).where(
            RetrievalObservation.workspace_id == workspace_id,
            RetrievalObservation.id == observation_id,
        )
    )
    if observation is None:
        raise LookupError("Retrieval Observation not found in Workspace")
    if observation.capability != "thread_fetch":
        raise NormalizationError("only thread-fetch observations can be normalized")
    if observation.status not in {"success", "incomplete"}:
        raise NormalizationError("thread-fetch observation has no usable content")
    if observation.evidence_state != "bundle" or observation.evidence_bundle_id is None:
        raise NormalizationError("normalization requires verified bundle evidence")
    if not observation.external_source_id:
        raise NormalizationError("thread-fetch observation has no source identity")
    bundle = session.scalar(
        select(EvidenceBundle).where(
            EvidenceBundle.workspace_id == workspace_id,
            EvidenceBundle.id == observation.evidence_bundle_id,
        )
    )
    if bundle is None:
        raise NormalizationError("Retrieval Observation bundle is missing")

    normalized = _load_normalized(
        store, observation, bundle, normalizer_version=normalizer_version
    )
    expected_status = "success" if normalized.source_tree_exhausted else "incomplete"
    if observation.status != expected_status:
        raise NormalizationError(
            "thread completeness disagrees with source-tree exhaustion"
        )
    conversation = _get_or_create_conversation(
        session, workspace_id, "reddit", observation.external_source_id
    )
    version, version_created = _get_or_create_version(session, conversation, normalized)
    provenance, provenance_created = _get_or_create_provenance(
        session, workspace_id, version.id, observation.id
    )
    return NormalizationRecord(
        conversation=conversation,
        version=version,
        provenance=provenance,
        version_created=version_created,
        provenance_created=provenance_created,
    )


def current_version(
    session: Session, workspace_id: uuid.UUID, conversation_id: uuid.UUID
) -> ConversationVersion | None:
    """Select current content by evidence time and immutable tie-breakers."""
    observed_at = func.coalesce(
        RetrievalObservation.completed_at,
        RetrievalObservation.started_at,
        RetrievalObservation.created_at,
    )
    return session.scalar(
        select(ConversationVersion)
        .join(
            ConversationVersionObservation,
            (ConversationVersionObservation.workspace_id == workspace_id)
            & (
                ConversationVersionObservation.conversation_version_id
                == ConversationVersion.id
            ),
        )
        .join(
            RetrievalObservation,
            (RetrievalObservation.workspace_id == workspace_id)
            & (
                RetrievalObservation.id
                == ConversationVersionObservation.retrieval_observation_id
            ),
        )
        .where(
            ConversationVersion.workspace_id == workspace_id,
            ConversationVersion.conversation_id == conversation_id,
        )
        .order_by(
            observed_at.desc(),
            RetrievalObservation.creation_order.desc(),
            ConversationVersion.normalizer_version.desc(),
            ConversationVersion.id.desc(),
        )
        .limit(1)
    )


def _candidate_fields(
    candidate: dict[str, Any],
) -> tuple[str, str, str, int | None] | None:
    external_id = candidate.get("externalSourceId")
    url = candidate.get("url")
    title = candidate.get("title")
    rank = candidate.get("rank")
    if not isinstance(external_id, str) or not external_id:
        return None
    if not isinstance(url, str) or not url:
        return None
    return (
        external_id,
        url,
        title if isinstance(title, str) else "",
        rank if isinstance(rank, int) and not isinstance(rank, bool) else None,
    )


def list_run_transitions(
    session: Session, workspace_id: uuid.UUID, run_id: uuid.UUID
) -> RunConversationTransitions:
    run = session.scalar(
        select(DiscoveryRun).where(
            DiscoveryRun.workspace_id == workspace_id, DiscoveryRun.id == run_id
        )
    )
    if run is None:
        raise LookupError("Discovery Run not found in Workspace")
    discovery_rows = list(
        session.scalars(
            select(RetrievalObservation)
            .where(
                RetrievalObservation.workspace_id == workspace_id,
                RetrievalObservation.discovery_run_id == run_id,
                RetrievalObservation.capability == "discovery",
            )
            .order_by(RetrievalObservation.creation_order)
        )
    )
    ordered: dict[str, tuple[str, str, int | None]] = {}
    for row in discovery_rows:
        for raw_candidate in row.candidates:
            if not isinstance(raw_candidate, dict):
                continue
            fields = _candidate_fields(raw_candidate)
            if fields is None:
                continue
            external_id, url, title, rank = fields
            ordered.setdefault(external_id, (url, title, rank))

    fetch_rows = {
        row.external_source_id: row
        for row in session.scalars(
            select(RetrievalObservation)
            .where(
                RetrievalObservation.workspace_id == workspace_id,
                RetrievalObservation.discovery_run_id == run_id,
                RetrievalObservation.capability == "thread_fetch",
                RetrievalObservation.external_source_id.is_not(None),
            )
            .order_by(RetrievalObservation.creation_order)
        )
        if row.external_source_id is not None
    }
    items: list[CandidateTransition] = []
    fetched_count = 0
    normalized_count = 0
    for external_id, (url, title, rank) in ordered.items():
        fetch = fetch_rows.get(external_id)
        if fetch is not None:
            fetched_count += 1
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.source_platform == "reddit",
                Conversation.canonical_external_discussion_id == external_id,
            )
        )
        version = (
            current_version(session, workspace_id, conversation.id)
            if conversation is not None
            else None
        )
        if version is not None:
            normalized_count += 1
        items.append(
            CandidateTransition(
                external_source_id=external_id,
                url=url,
                title=title,
                rank=rank,
                retrieval_status=fetch.status if fetch is not None else None,
                conversation=conversation,
                current_version=version,
            )
        )
    expected_count = len(items)
    processing_complete = (
        run.status in {"succeeded", "partial", "failed", "cancelled"}
        and fetched_count == expected_count
    )
    return RunConversationTransitions(
        items=items,
        expected_count=expected_count,
        fetched_count=fetched_count,
        normalized_count=normalized_count,
        processing_complete=processing_complete,
    )
