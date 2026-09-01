"""Fetch one Candidate, commit raw evidence, then normalize by bundle replay."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.conversations import service
from app.conversations.identity import thread_fetch_query_id
from app.conversations.normalizer import NormalizationError
from app.db import DatabaseSessionManager
from app.discovery import cli, queue
from app.discovery import events as progress_events
from app.discovery.events import ProgressEvent
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.discovery.runner import (
    _AttemptOutcome,
    _classify_result,
    _cleanup_staging_attempt,
    _ensure_bundle_row,
    _evidence_failure_reason,
    _new_observation,
    _parse_iso,
    _raw_artifact_input,
    _raw_artifact_metadata,
)
from app.evidence.store import (
    ArtifactValidationError,
    EvidenceStore,
    EvidenceStoreError,
    EvidenceStoreLimits,
    LocalEvidenceStore,
)


@dataclass(frozen=True, slots=True)
class _ThreadConfig:
    node_bin: str
    cli_path: str
    config_path: str
    staging_root: Path
    input_root: Path
    evidence_store: EvidenceStore
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class _ThreadClaim:
    workspace_id: uuid.UUID
    run_id: uuid.UUID
    correlation_id: str
    query_id: str
    external_source_id: str
    url: str


def _resolve_config() -> _ThreadConfig:
    settings = get_settings()
    limits = EvidenceStoreLimits(
        max_artifacts=settings.evidence_store_max_artifacts,
        max_artifact_bytes=settings.evidence_store_max_artifact_bytes,
        max_total_bytes=settings.evidence_store_max_total_bytes,
        max_manifest_bytes=settings.evidence_store_max_manifest_bytes,
        max_name_bytes=settings.evidence_store_max_name_bytes,
        max_role_bytes=settings.evidence_store_max_role_bytes,
        max_media_type_bytes=settings.evidence_store_max_media_type_bytes,
    )
    return _ThreadConfig(
        node_bin=settings.retrieval_node_bin,
        cli_path=str(settings.retrieval_cli_path),
        config_path=str(settings.thread_provider_config_path),
        staging_root=Path(settings.retrieval_staging_root),
        input_root=Path(settings.retrieval_input_scratch_root),
        evidence_store=LocalEvidenceStore(
            Path(settings.retrieval_evidence_root), limits
        ),
        timeout_seconds=float(settings.retrieval_attempt_timeout_seconds),
    )


def _candidate_in_run(
    rows: list[RetrievalObservation], external_source_id: str, url: str
) -> bool:
    for row in rows:
        for candidate in row.candidates:
            if not isinstance(candidate, dict):
                continue
            if (
                candidate.get("externalSourceId") == external_source_id
                and candidate.get("url") == url
            ):
                return True
    return False


def _claim(
    manager: DatabaseSessionManager,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    correlation_id: str,
    external_source_id: str,
    url: str,
) -> tuple[str, _ThreadClaim | RetrievalObservation | None]:
    query_id = thread_fetch_query_id(external_source_id)
    with manager.session_factory() as session, session.begin():
        run = session.scalar(
            select(DiscoveryRun).where(
                DiscoveryRun.workspace_id == workspace_id,
                DiscoveryRun.id == run_id,
            )
        )
        if run is None:
            return "run_missing", None
        existing = session.scalar(
            select(RetrievalObservation).where(
                RetrievalObservation.workspace_id == workspace_id,
                RetrievalObservation.discovery_run_id == run_id,
                RetrievalObservation.query_id == query_id,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return "recorded", existing
        discovery_rows = list(
            session.scalars(
                select(RetrievalObservation).where(
                    RetrievalObservation.workspace_id == workspace_id,
                    RetrievalObservation.discovery_run_id == run_id,
                    RetrievalObservation.capability == "discovery",
                )
            )
        )
        violation: str | None = None
        if correlation_id != run.correlation_id:
            violation = "thread-fetch correlation does not match its Discovery Run"
        elif len(correlation_id) > 128 or len(external_source_id) > 512:
            violation = "thread-fetch identity exceeds persisted contract bounds"
        elif not _candidate_in_run(discovery_rows, external_source_id, url):
            violation = "thread-fetch input is not a durable Candidate of this run"
        if violation is not None:
            row = _new_observation(
                run,
                query_id,
                run.correlation_id,
                schema_version=1,
                provider_variant="unknown-thread-fetch",
                config_sha256="0" * 64,
                observation_id=f"{run.id}:{query_id}:refused",
                status="failed",
                evidence_state="none",
                capability="thread_fetch",
                external_source_id=external_source_id[:512] or None,
                source_url=url[:2048] or None,
                failure_class="contract_violation",
                failure_reason=violation,
            )
            session.add(row)
            session.flush()
            session.expunge(row)
            return "contract_violation", row
        return "claimed", _ThreadClaim(
            workspace_id=workspace_id,
            run_id=run_id,
            correlation_id=run.correlation_id,
            query_id=query_id,
            external_source_id=external_source_id,
            url=url,
        )


async def _spawn(claim: _ThreadClaim, config: _ThreadConfig) -> _AttemptOutcome:
    input_dir = config.input_root / str(claim.run_id) / "threads"
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"input-{claim.query_id}.json"
    input_path.write_text(
        json.dumps({"threads": [{"id": claim.query_id, "url": claim.url}]})
    )
    config.staging_root.mkdir(parents=True, exist_ok=True)
    output_root = config.staging_root / str(claim.run_id) / "thread-fetch"
    try:
        result = await cli.run_retrieval_cli(
            "fetch-thread",
            node_bin=config.node_bin,
            cli_path=config.cli_path,
            config_path=config.config_path,
            input_path=input_path,
            query_id=claim.query_id,
            output_root=output_root,
            timeout_seconds=config.timeout_seconds,
        )
        outcome = _classify_result(
            result,
            output_root,
            config.timeout_seconds,
            expected_capability="thread_fetch",
        )
        if outcome.doc is not None:
            try:
                artifact = _raw_artifact_input(
                    outcome.doc,
                    config.staging_root,
                    output_root,
                    claim.query_id,
                )
                bundle = config.evidence_store.finalize_bundle(
                    claim.workspace_id, [artifact]
                )
                if not config.evidence_store.verify_bundle(bundle):
                    raise EvidenceStoreError(
                        "finalized raw evidence failed verification"
                    )
                outcome = _AttemptOutcome(
                    evidence_directory=outcome.evidence_directory,
                    doc=outcome.doc,
                    bundle=bundle,
                    raw_artifact=_raw_artifact_metadata(bundle),
                )
            except (
                ArtifactValidationError,
                EvidenceStoreError,
                OSError,
                ValueError,
            ) as error:
                outcome = _AttemptOutcome(
                    evidence_directory=outcome.evidence_directory,
                    doc=outcome.doc,
                    failure_class="evidence_unreadable",
                    failure_reason=_evidence_failure_reason(error),
                )
        return outcome
    finally:
        _cleanup_staging_attempt(config.staging_root, output_root, claim.query_id)


def _row_from_outcome(
    run: DiscoveryRun, claim: _ThreadClaim, outcome: _AttemptOutcome
) -> RetrievalObservation:
    doc = outcome.doc
    if doc is not None and outcome.bundle is not None:
        if outcome.raw_artifact is None:
            raise ValueError("bundled thread outcome has no raw descriptor")
        return _new_observation(
            run,
            claim.query_id,
            claim.correlation_id,
            schema_version=doc.schema_version,
            provider_variant=doc.provider_variant,
            config_sha256=doc.config_sha256,
            observation_id=doc.observation_id,
            status=doc.status,
            evidence_state="bundle",
            capability="thread_fetch",
            evidence_bundle_id=outcome.bundle.id,
            failure_reason=doc.failure_reason,
            source_url=doc.source_url,
            final_url=doc.final_url,
            external_source_id=doc.external_source_id,
            normalized_sha256=doc.normalized_sha256,
            normalized_content_sha256=doc.normalized_content_sha256,
            elapsed_ms=doc.elapsed_ms,
            started_at=_parse_iso(doc.started_at),
            completed_at=_parse_iso(doc.completed_at),
            runtime=doc.runtime,
            network=doc.network,
            raw_artifact=outcome.raw_artifact,
        )
    return _new_observation(
        run,
        claim.query_id,
        claim.correlation_id,
        schema_version=doc.schema_version if doc is not None else 1,
        provider_variant=doc.provider_variant
        if doc is not None
        else "unknown-thread-fetch",
        config_sha256=doc.config_sha256 if doc is not None else "0" * 64,
        observation_id=(
            doc.observation_id
            if doc is not None
            else f"{run.id}:{claim.query_id}:unclassified"
        ),
        status="failed",
        evidence_state="none",
        capability="thread_fetch",
        external_source_id=claim.external_source_id,
        source_url=claim.url,
        failure_class=outcome.failure_class or "transport_error",
        failure_reason=outcome.failure_reason or "thread retrieval failed",
        elapsed_ms=doc.elapsed_ms if doc is not None else None,
        started_at=_parse_iso(doc.started_at) if doc is not None else None,
        completed_at=_parse_iso(doc.completed_at) if doc is not None else None,
        runtime=doc.runtime if doc is not None else None,
        network=doc.network if doc is not None else None,
    )


def _settle(
    manager: DatabaseSessionManager,
    claim: _ThreadClaim,
    outcome: _AttemptOutcome,
) -> RetrievalObservation | None:
    with manager.session_factory() as session, session.begin():
        run = session.scalar(
            select(DiscoveryRun).where(
                DiscoveryRun.workspace_id == claim.workspace_id,
                DiscoveryRun.id == claim.run_id,
            )
        )
        if run is None:
            return None
        existing = session.scalar(
            select(RetrievalObservation).where(
                RetrievalObservation.workspace_id == claim.workspace_id,
                RetrievalObservation.discovery_run_id == claim.run_id,
                RetrievalObservation.query_id == claim.query_id,
            )
        )
        if existing is not None:
            session.expunge(existing)
            return existing
        if outcome.bundle is not None:
            _ensure_bundle_row(session, outcome.bundle)
        row = _row_from_outcome(run, claim, outcome)
        session.add(row)
        session.flush()
        session.expunge(row)
        return row


async def _publish(
    claim: _ThreadClaim, event_type: str, payload: dict[str, Any]
) -> None:
    await progress_events.publish_progress_event(
        ProgressEvent.create(
            event_type=event_type,
            run_id=claim.run_id,
            workspace_id=claim.workspace_id,
            correlation_id=claim.correlation_id,
            payload=payload,
        )
    )


def _campaign_id_for_run(
    manager: DatabaseSessionManager, claim: _ThreadClaim
) -> uuid.UUID | None:
    with manager.session_factory() as session:
        return session.scalar(
            select(DiscoveryRun.campaign_id).where(
                DiscoveryRun.workspace_id == claim.workspace_id,
                DiscoveryRun.id == claim.run_id,
            )
        )


async def _enqueue_analysis(
    manager: DatabaseSessionManager,
    claim: _ThreadClaim,
    conversation_id: uuid.UUID,
    version_id: uuid.UUID,
) -> None:
    """Hand the new Version to the analysis worker; refusal is loud, not fatal.

    A refused enqueue leaves the Conversation Version durable and replayable
    (the same job id re-enqueues later); the failure is published so the
    operator sees analysis did not start rather than waiting for a score.
    """
    campaign_id = _campaign_id_for_run(manager, claim)
    if campaign_id is None:
        return
    try:
        await queue.enqueue_conversation_analysis(
            claim.workspace_id,
            campaign_id,
            conversation_id,
            version_id,
            claim.correlation_id,
            discovery_run_id=claim.run_id,
        )
    except queue.AnalysisQueueError as error:
        await _publish(
            claim,
            "job.failed",
            {
                "job": "analysis_enqueue",
                "conversation_id": str(conversation_id),
                "conversation_version_id": str(version_id),
                "error_class": type(error).__name__,
            },
        )


async def _publish_processing_complete_if_ready(
    manager: DatabaseSessionManager, claim: _ThreadClaim
) -> None:
    with manager.session_factory() as session:
        transitions = service.list_run_transitions(
            session, claim.workspace_id, claim.run_id
        )
    if transitions.processing_complete:
        await _publish(
            claim,
            "conversation.processing_completed",
            {
                "expected_count": transitions.expected_count,
                "fetched_count": transitions.fetched_count,
                "normalized_count": transitions.normalized_count,
            },
        )


async def run_thread_fetch(
    ctx: object,
    *,
    workspace_id: str,
    run_id: str,
    correlation_id: str,
    external_source_id: str,
    url: str,
) -> str:
    """Direct arq callable: one Candidate, one CLI fetch, one replay."""
    del ctx
    settings = get_settings()
    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        workspace_uuid = uuid.UUID(workspace_id)
        run_uuid = uuid.UUID(run_id)
        marker, claimed = _claim(
            manager,
            workspace_uuid,
            run_uuid,
            correlation_id,
            external_source_id,
            url,
        )
        if marker == "run_missing" or claimed is None:
            return marker
        observation: RetrievalObservation | None
        if isinstance(claimed, RetrievalObservation):
            observation = claimed
            claim = _ThreadClaim(
                workspace_id=observation.workspace_id,
                run_id=observation.discovery_run_id,
                correlation_id=observation.correlation_id,
                query_id=observation.query_id,
                external_source_id=(
                    observation.external_source_id or external_source_id
                ),
                url=observation.source_url or url,
            )
        else:
            claim = claimed
            outcome = await _spawn(claim, _resolve_config())
            observation = _settle(manager, claim, outcome)
        if observation is None:
            return "run_missing"
        await _publish(
            claim,
            "retrieval.observed",
            {
                "query_id": observation.query_id,
                "observation_id": observation.observation_id,
                "capability": "thread_fetch",
                "external_source_id": observation.external_source_id,
                "status": observation.status,
                "failure_class": observation.failure_class,
            },
        )
        if (
            observation.status in {"success", "incomplete"}
            and observation.evidence_state == "bundle"
        ):
            config = _resolve_config()
            try:
                with manager.session_factory() as session, session.begin():
                    record = service.normalize_observation(
                        session,
                        config.evidence_store,
                        workspace_uuid,
                        observation.id,
                    )
            except (LookupError, NormalizationError, EvidenceStoreError) as error:
                await _publish(
                    claim,
                    "job.failed",
                    {
                        "job": "conversation_normalization",
                        "observation_id": str(observation.id),
                        "error_class": type(error).__name__,
                    },
                )
                await _publish_processing_complete_if_ready(manager, claim)
                return "normalization_failed"
            await _publish(
                claim,
                "conversation.normalized",
                {
                    "external_source_id": claim.external_source_id,
                    "conversation_id": str(record.conversation.id),
                    "conversation_version_id": str(record.version.id),
                    "normalizer_version": record.version.normalizer_version,
                    "normalized_content_sha256": (
                        record.version.normalized_content_sha256
                    ),
                    "source_tree_exhausted": record.version.source_tree_exhausted,
                    "version_created": record.version_created,
                    "provenance_created": record.provenance_created,
                },
            )
            await _enqueue_analysis(
                manager, claim, record.conversation.id, record.version.id
            )
            result = "normalized"
        else:
            result = observation.status
        await _publish_processing_complete_if_ready(manager, claim)
        return result
    finally:
        manager.dispose()
