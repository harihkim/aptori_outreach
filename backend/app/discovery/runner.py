"""Worker-side execution of one discovery query against one retrieval CLI.

The runner is the domain seam between the arq queue and the immutable
observation store. One invocation is split into three phases so a crash can
never leave a database transaction open across a subprocess spawn:

1. CLAIM — one short transaction row-locks the run, refuses missing/terminal
   rows, moves queued->running with its audit event, replays-guards the
   observation pair, and commits.
2. SPAWN — the retrieval CLI runs with NO open transaction or connection.
   Query inputs are staged in the Python-owned scratch root and CLI output is
   written to a separate expendable staging root; classification happens here
   too: every outcome becomes an attempt outcome, never an exception.
3. SETTLE — one final transaction re-locks the run, authoritatively
   replay-guards the insert, rolls the run up counting only planned queries,
   and transitions it to a terminal status exactly once.

Spawn configuration comes exclusively from settings: there is deliberately
no override channel on this function, so a queue caller can never substitute
binaries or paths.
"""

import json
import mimetypes
import re
import shutil
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditing.service import record_audit
from app.config import get_settings
from app.db import DatabaseSessionManager
from app.discovery import cli, queue
from app.discovery import events as progress_events
from app.discovery.events import ProgressEvent
from app.discovery.models import (
    FAILURE_CLASSES,
    RUN_COST_STATUSES,
    RUN_COST_UNPRICED,
    DiscoveryRun,
    RetrievalObservation,
)
from app.discovery.observations import (
    OBSERVATION_SCHEMA_VERSION,
    ObservationDocument,
    UnknownObservationSchemaVersion,
    UnknownObservationStatus,
    parse_observation,
    redact_sensitive_text,
)
from app.discovery.service import QUERY_ID_PATTERN
from app.evidence.models import EvidenceBundle
from app.evidence.store import (
    ArtifactInput,
    ArtifactValidationError,
    EvidenceStore,
    EvidenceStoreError,
    EvidenceStoreLimits,
    FinalizedBundle,
    LocalEvidenceStore,
)

# Ruling sets for the run roll-up. Succeeded means nothing was lost;
# usable includes incomplete because partial evidence still has value.
SUCCEEDED_STATUSES = frozenset({"success", "no_results"})
USABLE_STATUSES = frozenset({"success", "no_results", "incomplete"})

# Run statuses no worker may ever leave once reached. Redeliveries and late
# arrivals observe them through 'already_done' instead of mutating history.
TERMINAL_RUN_STATUSES = frozenset({"succeeded", "partial", "failed", "cancelled"})

# Stderr fingerprints emitted by the retrieval CLI's runtime gate.
RUNTIME_VERIFICATION_MARKERS = ("verifyRuntime", "Node version", "Obscura version")

# The only capability this runner may record discovery evidence for.
EXPECTED_CAPABILITY = "discovery"

# Run-metrics shape consumed by the API and the frontend run screen. Pinned
# by test_discovery_contract and test_worker_runner so key drift anywhere in
# the stack fails deterministically; the frontend aligns to THIS shape.
RUN_METRICS_KEYS = frozenset(
    {"counts", "total_elapsed_ms", "cost_usd", "cost_status", "usage"}
)
RUN_USAGE_KEYS = frozenset({"request_count", "bytes_transferred"})


@dataclass(frozen=True)
class _AttemptConfig:
    """Spawn parameters resolved once per attempt from settings alone."""

    node_bin: str
    cli_path: str
    config_path: str
    staging_root: Path
    evidence_store: EvidenceStore
    input_root: Path
    timeout_seconds: float


@dataclass(frozen=True)
class _Claim:
    """Plan snapshot taken under the claim lock, reused outside the tx."""

    run_id: uuid.UUID
    workspace_id: uuid.UUID
    planned_ids: tuple[str, ...]
    entry: dict[str, Any]
    started: bool


@dataclass(frozen=True)
class _Settlement:
    """Committed result of one attempt, including what progress to publish."""

    status: str
    recorded: bool
    completed: bool
    observation: RetrievalObservation | None = None
    metrics: dict[str, object] | None = None


@dataclass(frozen=True)
class _AttemptOutcome:
    """Classified end state of one attempt; never raised, always persisted."""

    evidence_directory: str
    doc: ObservationDocument | None = None
    bundle: FinalizedBundle | None = None
    raw_artifact: dict[str, object] | None = None
    failure_class: str | None = None
    failure_reason: str | None = None


def _resolve_config() -> _AttemptConfig:
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
    return _AttemptConfig(
        node_bin=settings.retrieval_node_bin,
        cli_path=str(settings.retrieval_cli_path),
        config_path=str(settings.discovery_provider_config_path),
        staging_root=Path(settings.retrieval_staging_root),
        evidence_store=LocalEvidenceStore(
            Path(settings.retrieval_evidence_root), limits
        ),
        input_root=Path(settings.retrieval_input_scratch_root),
        timeout_seconds=float(settings.retrieval_attempt_timeout_seconds),
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_iso(value: str | None) -> datetime | None:
    """Strict ISO-8601 parsing: timezone-naive timestamps are rejected.

    A naive datetime would land in the database session's time zone and
    silently corrupt evidence ordering, so it parses to nothing instead.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _plan_queries(method_plan: dict[str, object]) -> list[dict[str, Any]]:
    raw = method_plan.get("queries")
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def _new_observation(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    *,
    schema_version: int,
    provider_variant: str,
    config_sha256: str,
    observation_id: str,
    status: str,
    evidence_state: str,
    capability: str = EXPECTED_CAPABILITY,
    evidence_bundle_id: uuid.UUID | None = None,
    evidence_directory: str | None = None,
    failure_class: str | None = None,
    failure_reason: str | None = None,
    source_url: str | None = None,
    final_url: str | None = None,
    external_source_id: str | None = None,
    candidate_count: int = 0,
    candidates: list[dict[str, Any]] | None = None,
    normalized_sha256: str | None = None,
    normalized_content_sha256: str | None = None,
    elapsed_ms: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    runtime: dict[str, Any] | None = None,
    network: dict[str, Any] | None = None,
    raw_artifact: dict[str, Any] | None = None,
) -> RetrievalObservation:
    """Single construction site for append-only observation rows."""
    return RetrievalObservation(
        discovery_run_id=run.id,
        workspace_id=run.workspace_id,
        query_id=query_id,
        schema_version=schema_version,
        capability=capability,
        provider_variant=provider_variant,
        config_sha256=config_sha256,
        observation_id=observation_id,
        status=status,
        failure_class=failure_class,
        failure_reason=(
            redact_sensitive_text(failure_reason) if failure_reason else None
        ),
        source_url=source_url,
        final_url=final_url,
        external_source_id=external_source_id,
        candidate_count=candidate_count,
        candidates=candidates or [],
        normalized_sha256=normalized_sha256,
        normalized_content_sha256=normalized_content_sha256,
        elapsed_ms=elapsed_ms,
        started_at=started_at,
        completed_at=completed_at,
        runtime=runtime,
        network=network,
        raw_artifact=raw_artifact,
        evidence_state=evidence_state,
        evidence_bundle_id=evidence_bundle_id,
        evidence_directory=evidence_directory,
        correlation_id=correlation_id,
    )


def _document_observation(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    doc: ObservationDocument,
    bundle: FinalizedBundle,
    raw_artifact: dict[str, object],
) -> RetrievalObservation:
    """Map a validated observation document onto an append-only row."""
    return _new_observation(
        run,
        query_id,
        correlation_id,
        schema_version=doc.schema_version,
        provider_variant=doc.provider_variant,
        config_sha256=doc.config_sha256,
        observation_id=doc.observation_id,
        status=doc.status,
        evidence_state="bundle",
        evidence_bundle_id=bundle.id,
        failure_reason=doc.failure_reason,
        source_url=doc.source_url,
        final_url=doc.final_url,
        candidate_count=doc.candidate_count or 0,
        candidates=doc.candidates or [],
        normalized_sha256=doc.normalized_sha256,
        elapsed_ms=doc.elapsed_ms,
        started_at=_parse_iso(doc.started_at),
        completed_at=_parse_iso(doc.completed_at),
        runtime=doc.runtime,
        network=doc.network,
        raw_artifact=raw_artifact,
    )


def _failed_document_observation(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    doc: ObservationDocument,
    *,
    failure_class: str,
    failure_reason: str,
) -> RetrievalObservation:
    """Retain safe provider context while recording no trustworthy evidence."""
    return _new_observation(
        run,
        query_id,
        correlation_id,
        schema_version=doc.schema_version,
        provider_variant=doc.provider_variant,
        config_sha256=doc.config_sha256,
        observation_id=doc.observation_id,
        status="failed",
        evidence_state="none",
        failure_class=failure_class,
        failure_reason=failure_reason,
        source_url=doc.source_url,
        final_url=doc.final_url,
        elapsed_ms=doc.elapsed_ms,
        started_at=_parse_iso(doc.started_at),
        completed_at=_parse_iso(doc.completed_at),
        runtime=doc.runtime,
        network=doc.network,
    )


def _unclassified_observation(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    output_root: Path,
    *,
    failure_class: str,
    failure_reason: str,
) -> RetrievalObservation:
    """Build the terminal row used when no native document can be trusted."""
    plan = run.method_plan
    return _new_observation(
        run,
        query_id,
        correlation_id,
        schema_version=OBSERVATION_SCHEMA_VERSION,
        provider_variant=str(plan.get("provider_variant") or "unknown"),
        config_sha256=str(plan.get("config_sha256") or "0" * 64),
        observation_id=f"{run.id}:{query_id}:unclassified",
        status="failed",
        evidence_state="none",
        failure_class=failure_class,
        failure_reason=failure_reason,
    )


def _outcome_to_row(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    output_root: Path,
    outcome: _AttemptOutcome,
) -> RetrievalObservation:
    # Vocabulary audit: a classifier can never smuggle an out-of-taxonomy
    # failure class past this point (parity-checked down to the wire schema).
    if (
        outcome.failure_class is not None
        and outcome.failure_class not in FAILURE_CLASSES
    ):
        raise ValueError(
            f"classifier produced out-of-vocabulary failure_class "
            f"{outcome.failure_class!r}"
        )
    if outcome.doc is not None and outcome.bundle is not None:
        if outcome.raw_artifact is None:
            raise ValueError("bundled outcome is missing raw artifact metadata")
        return _document_observation(
            run,
            query_id,
            correlation_id,
            outcome.doc,
            outcome.bundle,
            outcome.raw_artifact,
        )
    if outcome.doc is not None and outcome.failure_class is not None:
        return _failed_document_observation(
            run,
            query_id,
            correlation_id,
            outcome.doc,
            failure_class=outcome.failure_class,
            failure_reason=outcome.failure_reason or "raw evidence is unavailable",
        )
    return _unclassified_observation(
        run,
        query_id,
        correlation_id,
        output_root,
        failure_class=outcome.failure_class or "transport_error",
        failure_reason=outcome.failure_reason or "unclassified retrieval failure",
    )


def _classify_result(
    result: cli.CliResult,
    output_root: Path,
    timeout_seconds: float,
    *,
    expected_capability: str = EXPECTED_CAPABILITY,
) -> _AttemptOutcome:
    """Turn a finished CLI attempt into a persisted outcome; raises nothing."""
    if result.timed_out:
        # The adapter already attempted deterministic disk recovery before
        # reporting a timeout; reaching here means nothing valid was written.
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="transport_timeout",
            failure_reason=(
                f"retrieval attempt exceeded {timeout_seconds:g}s and was killed "
                "without recoverable disk evidence"
            ),
        )

    if result.evidence_source == "disk_unreadable":
        # The authoritative disk document exists but cannot be read; stdout
        # projections must never stand in for it.
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="evidence_unreadable",
            failure_reason=(
                "observation.json could not be read from the evidence "
                f"directory (stderr tail: {result.stderr_tail!r})"
            ),
        )

    if result.evidence_source == "no_evidence_pointer":
        # Stdout carried no evidenceDirectory, so there is nothing on disk
        # to trust either; classify explicitly instead of guessing.
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="evidence_unlocated",
            failure_reason=(
                "stdout projection carried no evidenceDirectory pointer; "
                "disk is the only authoritative observation source"
            ),
        )

    if result.observation_doc is not None:
        raw_doc = result.observation_doc
        try:
            doc = parse_observation(raw_doc)
        except UnknownObservationSchemaVersion as error:
            return _AttemptOutcome(
                evidence_directory=str(output_root),
                failure_class="unknown_observation_schema",
                failure_reason=str(error),
            )
        except UnknownObservationStatus as error:
            return _AttemptOutcome(
                evidence_directory=str(output_root),
                failure_class="unknown_observation_status",
                failure_reason=str(error),
            )
        except ValidationError as error:
            return _AttemptOutcome(
                evidence_directory=str(output_root),
                failure_class="contract_violation",
                failure_reason=(
                    f"observation document violates the wire contract: {error}"
                ),
            )
        if doc.capability != expected_capability:
            return _AttemptOutcome(
                evidence_directory=doc.evidence_directory,
                failure_class="contract_violation",
                failure_reason=(
                    f"observation capability {doc.capability!r} is not "
                    f"{expected_capability!r}"
                ),
            )
        return _AttemptOutcome(evidence_directory=doc.evidence_directory, doc=doc)

    if result.evidence_source == "none" and result.exit_code == 0:
        # Exit 0 with neither a readable disk document nor even a locatable
        # stdout pointer is an honesty gap, not a transport failure.
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="evidence_unlocated",
            failure_reason=(
                "retrieval CLI exited 0 without an observation.json on disk "
                "and without a parsable evidenceDirectory pointer in stdout"
            ),
        )

    if result.exit_code == 1:
        if any(marker in result.stderr_tail for marker in RUNTIME_VERIFICATION_MARKERS):
            failure_class = "runtime_verification_failed"
        else:
            failure_class = "wrapper_error"
    else:
        failure_class = "transport_error"
    return _AttemptOutcome(
        evidence_directory=str(output_root),
        failure_class=failure_class,
        failure_reason=(
            f"retrieval CLI exited {result.exit_code} without an observation "
            f"(stderr tail: {result.stderr_tail[-500:]!r})"
        ),
    )


def _raw_artifact_input(
    doc: ObservationDocument,
    staging_root: Path,
    output_root: Path,
    query_id: str,
) -> ArtifactInput:
    """Validate the provider-declared raw file without trusting its metadata."""
    raw = doc.raw_artifact
    if not isinstance(raw, dict):
        raise ArtifactValidationError("observation has no declared raw artifact")
    path_value = raw.get("path")
    filename = raw.get("filename")
    declared_bytes = raw.get("bytes")
    declared_digest = raw.get("sha256")
    if not isinstance(path_value, str) or not path_value:
        raise ArtifactValidationError("raw artifact path is missing")
    if not isinstance(filename, str) or not filename:
        raise ArtifactValidationError("raw artifact filename is missing")
    if not isinstance(declared_bytes, int) or isinstance(declared_bytes, bool):
        raise ArtifactValidationError("raw artifact bytes is invalid")
    if declared_bytes < 0:
        raise ArtifactValidationError("raw artifact bytes is negative")
    if (
        not isinstance(declared_digest, str)
        or len(declared_digest) != 64
        or any(character not in "0123456789abcdef" for character in declared_digest)
    ):
        raise ArtifactValidationError("raw artifact sha256 is invalid")
    if "\x00" in path_value or "\x00" in filename:
        raise ArtifactValidationError("raw artifact contains NUL")

    # Node emits absolute paths. Requiring one here avoids interpreting a
    # provider-controlled relative path against a changing process cwd.
    declared_path = Path(path_value)
    if not declared_path.is_absolute() or Path(filename).name != filename:
        raise ArtifactValidationError("raw artifact path or filename is invalid")
    try:
        staging_resolved = staging_root.resolve(strict=True)
        output_resolved = output_root.resolve(strict=True)
        attempt_resolved = Path(doc.evidence_directory).resolve(strict=True)
        attempt_resolved.relative_to(staging_resolved)
        # The evidence pointer must identify this invocation's run output,
        # not another run or a sibling query attempt below the global staging
        # root. Node's attempt layout is <safe-query>_<attempt-id>; the test
        # adapter uses attempt-<query>.
        attempt_resolved.relative_to(output_resolved)
        safe_query = (
            re.sub(r"[^a-zA-Z0-9_-]+", "-", query_id).strip("-")[:80] or "attempt"
        )
        if attempt_resolved == output_resolved or not (
            attempt_resolved.name.startswith(f"{safe_query}_")
            or attempt_resolved.name == f"attempt-{query_id}"
        ):
            raise ArtifactValidationError("evidence directory is not an attempt")
        source_stat = declared_path.lstat()
        if source_stat.st_mode & 0o170000 != 0o100000:
            raise ArtifactValidationError("raw artifact is not a regular file")
        source_resolved = declared_path.resolve(strict=True)
        source_resolved.relative_to(attempt_resolved)
    except (OSError, ValueError) as error:
        raise ArtifactValidationError(
            "raw artifact is outside the declared staging attempt"
        ) from error

    media_type = mimetypes.guess_type(filename, strict=False)[0]
    return ArtifactInput(
        name=filename,
        role="raw",
        media_type=media_type or "application/octet-stream",
        path=declared_path,
    )


def _raw_artifact_metadata(bundle: FinalizedBundle) -> dict[str, object]:
    """Return only canonical, path-free metadata produced by EvidenceStore."""
    artifacts = bundle.artifact_manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise EvidenceStoreError("discovery bundle must contain one raw artifact")
    descriptor = artifacts[0]
    if not isinstance(descriptor, dict):
        raise EvidenceStoreError("discovery bundle descriptor is invalid")
    return dict(descriptor)


def _evidence_failure_reason(error: BaseException) -> str:
    """Render storage failures without copying provider-controlled paths."""
    error_code = type(error).__name__
    return f"raw evidence could not be finalized ({error_code})"


def _cleanup_staging_attempt(
    staging_root: Path, output_root: Path, query_id: str
) -> None:
    """Remove only this query's attempt, without following links or crossing roots."""
    try:
        root = staging_root.resolve(strict=True)
        output = output_root.resolve(strict=True)
        output.relative_to(root)
    except (OSError, ValueError):
        return
    safe_query = re.sub(r"[^a-zA-Z0-9_-]+", "-", query_id).strip("-")[:80] or "attempt"
    prefixes = (f"{safe_query}_", f"attempt-{query_id}")
    try:
        candidates = [
            path
            for path in output.rglob("*")
            if path.is_dir() and path.name.startswith(prefixes)
        ]
    except OSError:
        return

    def path_depth(path: Path) -> int:
        return len(path.parts)

    for candidate in sorted(candidates, key=path_depth, reverse=True):
        try:
            candidate.resolve(strict=True).relative_to(root)
            if candidate.is_symlink():
                candidate.unlink()
            else:
                shutil.rmtree(candidate)
        except (OSError, ValueError):
            continue
    # Prune empty run/capability parents, stopping at the configured root.
    current = output
    while current != root:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _network_request_count(row: RetrievalObservation) -> int | None:
    """Measured request counter retained by the CLI's network metadata."""
    network = row.network
    if not isinstance(network, dict):
        return None
    value = network.get("requests")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _roll_up_run(
    session: Session,
    run: DiscoveryRun,
    planned_ids: tuple[str, ...],
    correlation_id: str,
) -> bool:
    """Recount observations under lock and close the run when complete.

    Only observations whose query_id appears in method_plan['queries'] count
    toward completion, and an already-terminal run is never transitioned
    again. Currency-cost state is always explicit: the backend does not
    price retrieval, so cost_status stays 'unpriced' with cost_usd null;
    measured usage sums cover only dimensions the tooling actually measured
    and stay null otherwise — never zero.
    """
    rows = list(
        session.scalars(
            select(RetrievalObservation)
            .where(
                RetrievalObservation.workspace_id == run.workspace_id,
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id.in_(planned_ids),
            )
            .with_for_update()
        )
    )
    if len(rows) < len(planned_ids):
        return False
    if run.status in TERMINAL_RUN_STATUSES:
        return False

    previous_status = run.status
    statuses = [row.status for row in rows]
    if all(status in SUCCEEDED_STATUSES for status in statuses):
        final_status = "succeeded"
    elif not any(status in USABLE_STATUSES for status in statuses):
        final_status = "failed"
    else:
        final_status = "partial"

    measured_requests = [
        count
        for count in (_network_request_count(row) for row in rows)
        if count is not None
    ]
    if RUN_COST_UNPRICED not in RUN_COST_STATUSES:
        raise ValueError(
            f"RUN_COST_UNPRICED {RUN_COST_UNPRICED!r} not in RUN_COST_STATUSES"
        )

    run.completed_at = _now()
    run.status = final_status
    metrics: dict[str, object] = {
        "counts": dict(sorted(Counter(statuses).items())),
        "total_elapsed_ms": sum(row.elapsed_ms or 0 for row in rows),
        "cost_usd": None,
        "cost_status": RUN_COST_UNPRICED,
        "usage": {
            "request_count": sum(measured_requests) if measured_requests else None,
            "bytes_transferred": None,
        },
    }
    run.metrics = metrics
    record_audit(
        session,
        actor="worker",
        action="discovery_run.completed",
        target_type="discovery_run",
        target_id=run.id,
        workspace_id=run.workspace_id,
        before={"status": previous_status},
        after={"status": final_status},
        correlation_id=correlation_id,
    )
    return True


def _claim_run(
    manager: DatabaseSessionManager,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    correlation_id: str,
    query_id: str,
) -> tuple[str, _Claim | None]:
    """Phase 1: short claim transaction. Returns a marker plus plan snapshot.

    Markers other than 'claimed' mean nothing may be spawned: 'run_missing',
    'already_done' (terminal), a run status when this exact observation was
    already recorded (replay), or a run status after recording an entry-time
    contract violation (hostile kwargs are evidence, never spawns).
    """
    with manager.session_factory() as session, session.begin():
        run = session.execute(
            select(DiscoveryRun)
            .where(
                DiscoveryRun.workspace_id == workspace_id,
                DiscoveryRun.id == run_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            return "run_missing", None
        if run.status in TERMINAL_RUN_STATUSES:
            return "already_done", None

        # Idempotent lifecycle transition: only the first invocation moves
        # the run out of queued and writes the start audit event.
        started = False
        if run.status == "queued":
            run.status = "running"
            run.started_at = _now()
            started = True
            record_audit(
                session,
                actor="worker",
                action="discovery_run.started",
                target_type="discovery_run",
                target_id=run.id,
                workspace_id=run.workspace_id,
                before={"status": "queued"},
                after={"status": "running"},
                correlation_id=correlation_id,
            )

        # Replay guard ahead of the spawn: a redelivered job whose
        # observation already exists must not rerun the attempt.
        already_recorded = session.execute(
            select(RetrievalObservation.id).where(
                RetrievalObservation.workspace_id == workspace_id,
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id == query_id,
            )
        ).scalar_one_or_none()
        if already_recorded is not None:
            return run.status, None

        planned_queries = _plan_queries(run.method_plan)
        planned_ids = tuple(str(q.get("id")) for q in planned_queries)
        entry = next((q for q in planned_queries if str(q.get("id")) == query_id), None)

        # Entry-time refusals: untrusted kwargs become contract_violation
        # evidence inside the claim transaction; no subprocess ever runs and
        # no hostile string reaches the filesystem.
        # Guard over-length ids before DB insert (String(200) / String(128)
        # columns) so hostile kwargs never crash the violation-row INSERT.
        violation_reason: str | None = None
        if len(query_id) > 200 or len(correlation_id) > 128:
            violation_reason = (
                f"query id or correlation id exceeds column bounds "
                f"(query_id len {len(query_id)}, correlation_id len {len(correlation_id)})"
            )
        elif QUERY_ID_PATTERN.fullmatch(query_id) is None:
            violation_reason = (
                f"query id {query_id!r} does not match ^[A-Za-z0-9_-]{{1,64}}$"
            )
        elif entry is None:
            violation_reason = (
                f"query {query_id!r} is not present in the run's method plan"
            )

        if violation_reason is not None:
            output_root = get_settings().retrieval_staging_root / str(run_id)
            session.add(
                _unclassified_observation(
                    run,
                    query_id,
                    correlation_id,
                    output_root,
                    failure_class="contract_violation",
                    failure_reason=violation_reason,
                )
            )
            session.flush()
            _roll_up_run(session, run, planned_ids, correlation_id)
            return run.status, None

        # The refusal chain above records a violation whenever the id is
        # absent from the plan, so a claimed invocation always carries one.
        if entry is None:
            raise ValueError("invariant violation: claimed entry is None")
        return "claimed", _Claim(
            run_id=run_id,
            workspace_id=run.workspace_id,
            planned_ids=planned_ids,
            entry=entry,
            started=started,
        )


async def _spawn_attempt(
    query_id: str, claim: _Claim, config: _AttemptConfig
) -> _AttemptOutcome:
    """Phase 2: spawn the CLI — no DB tx is open, kwargs are already vetted.

    The query input document is staged in the Python-owned scratch root; CLI
    output is written to a separate expendable staging root and only read back.
    """
    input_dir = config.input_root / str(claim.run_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"input-{query_id}.json"
    input_path.write_text(json.dumps({"queries": [claim.entry]}))

    # The CLI owns this tree only for the duration of one attempt. It never
    # writes directly into the durable EvidenceStore root.
    config.staging_root.mkdir(parents=True, exist_ok=True)
    output_root = config.staging_root / str(claim.run_id)
    try:
        result = await cli.run_retrieval_cli(
            "discover",
            node_bin=config.node_bin,
            cli_path=config.cli_path,
            config_path=config.config_path,
            input_path=str(input_path),
            query_id=query_id,
            output_root=str(output_root),
            timeout_seconds=config.timeout_seconds,
        )
        outcome = _classify_result(result, output_root, config.timeout_seconds)
        if outcome.doc is not None:
            try:
                artifact = _raw_artifact_input(
                    outcome.doc, config.staging_root, output_root, query_id
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
        _cleanup_staging_attempt(config.staging_root, output_root, query_id)


def _ensure_bundle_row(session: Session, bundle: FinalizedBundle) -> uuid.UUID:
    """Reuse an orphaned bundle or insert its immutable manifest once."""
    existing = session.scalar(
        select(EvidenceBundle).where(
            EvidenceBundle.workspace_id == bundle.workspace_id,
            EvidenceBundle.bundle_sha256 == bundle.bundle_sha256,
        )
    )
    if existing is not None:
        if (
            existing.id != bundle.id
            or existing.storage_key != bundle.storage_key
            or existing.manifest_version != bundle.manifest_version
            or existing.artifact_manifest != bundle.artifact_manifest
        ):
            raise EvidenceStoreError("database bundle identity conflicts with store")
        return existing.id

    row = EvidenceBundle(
        id=bundle.id,
        workspace_id=bundle.workspace_id,
        manifest_version=bundle.manifest_version,
        bundle_sha256=bundle.bundle_sha256,
        storage_key=bundle.storage_key,
        artifact_manifest=bundle.artifact_manifest,
    )
    try:
        # A concurrent attempt may publish the same content-addressed bundle
        # between the lookup and INSERT. Isolate the conflict so the outer
        # observation transaction remains usable and can reuse that row.
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError as error:
        existing = session.scalar(
            select(EvidenceBundle).where(
                EvidenceBundle.workspace_id == bundle.workspace_id,
                EvidenceBundle.bundle_sha256 == bundle.bundle_sha256,
            )
        )
        if existing is None:
            raise
        if (
            existing.id != bundle.id
            or existing.storage_key != bundle.storage_key
            or existing.manifest_version != bundle.manifest_version
            or existing.artifact_manifest != bundle.artifact_manifest
        ):
            raise EvidenceStoreError(
                "database bundle identity conflicts with store"
            ) from error
        return existing.id
    return row.id


def _settle_run(
    manager: DatabaseSessionManager,
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    query_id: str,
    correlation_id: str,
    outcome: _AttemptOutcome,
    planned_ids: tuple[str, ...],
) -> _Settlement:
    """Phase 3: single final transaction inserts and closes the run."""
    with manager.session_factory() as session, session.begin():
        run = session.execute(
            select(DiscoveryRun)
            .where(
                DiscoveryRun.workspace_id == workspace_id,
                DiscoveryRun.id == run_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            return _Settlement(status="run_missing", recorded=False, completed=False)

        # Terminal runs must not be mutated — late arrivals observe
        # already_done instead of appending evidence that diverges from
        # frozen metrics. See runner invariant at top of module.
        if run.status in TERMINAL_RUN_STATUSES:
            return _Settlement(status="already_done", recorded=False, completed=False)

        # Authoritative replay guard: skip the insert entirely when another
        # invocation already recorded this pair.
        already_recorded = session.execute(
            select(RetrievalObservation.id).where(
                RetrievalObservation.workspace_id == workspace_id,
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id == query_id,
            )
        ).scalar_one_or_none()
        if already_recorded is not None:
            return _Settlement(status=run.status, recorded=False, completed=False)

        if outcome.bundle is not None:
            _ensure_bundle_row(session, outcome.bundle)
        observation = _outcome_to_row(
            run, query_id, correlation_id, Path(outcome.evidence_directory), outcome
        )
        session.add(observation)
        session.flush()
        completed = _roll_up_run(session, run, planned_ids, correlation_id)
        return _Settlement(
            status=run.status,
            recorded=True,
            completed=completed,
            observation=observation,
            metrics=run.metrics,
        )


async def _publish_progress(
    *,
    event_type: str,
    run_id: uuid.UUID,
    workspace_id: uuid.UUID,
    correlation_id: str,
    payload: dict[str, Any],
) -> None:
    """Publish one already-committed progress notification."""
    await progress_events.publish_progress_event(
        ProgressEvent.create(
            event_type=event_type,
            run_id=run_id,
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    )


async def _publish_attempt_progress(
    claim: _Claim,
    correlation_id: str,
    settlement: _Settlement,
) -> None:
    """Publish observation/candidate/completion events in wire order."""
    observation = settlement.observation
    if observation is None:
        return

    candidates = [
        candidate for candidate in observation.candidates if isinstance(candidate, dict)
    ]
    try:
        await queue.enqueue_thread_fetch_candidates(
            claim.workspace_id,
            claim.run_id,
            correlation_id,
            candidates,
        )
    except queue.ThreadFetchQueueError as error:
        await _publish_progress(
            event_type="job.failed",
            run_id=claim.run_id,
            workspace_id=claim.workspace_id,
            correlation_id=correlation_id,
            payload={
                "job": "thread_fetch_enqueue",
                "failed_count": len(error.failed_external_ids),
            },
        )

    for candidate in candidates:
        await _publish_progress(
            event_type="discovery.candidate_found",
            run_id=claim.run_id,
            workspace_id=claim.workspace_id,
            correlation_id=correlation_id,
            payload={
                "query_id": observation.query_id,
                "observation_id": observation.observation_id,
                "candidate": candidate,
            },
        )

    await _publish_progress(
        event_type="retrieval.observed",
        run_id=claim.run_id,
        workspace_id=claim.workspace_id,
        correlation_id=correlation_id,
        payload={
            "query_id": observation.query_id,
            "observation_id": observation.observation_id,
            "status": observation.status,
            "candidate_count": observation.candidate_count,
            "failure_class": observation.failure_class,
            "elapsed_ms": observation.elapsed_ms,
        },
    )

    if settlement.completed:
        await _publish_progress(
            event_type="discovery.completed",
            run_id=claim.run_id,
            workspace_id=claim.workspace_id,
            correlation_id=correlation_id,
            payload={
                "status": settlement.status,
                "metrics": settlement.metrics,
            },
        )


async def run_discovery_query(
    ctx: object,
    *,
    workspace_id: str,
    run_id: str,
    correlation_id: str,
    query_id: str,
) -> str:
    """Execute one query of one discovery run; returns the run's status.

    There is intentionally no override channel: spawn binaries, paths, and
    timeouts come from settings alone, so what the worker runs is exactly
    what the deployment configured.
    """
    del ctx  # arq passes its worker context; the runner does not need it.
    settings = get_settings()
    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        workspace_uuid = uuid.UUID(workspace_id)
        run_uuid = uuid.UUID(run_id)
        marker, claim = _claim_run(
            manager, workspace_uuid, run_uuid, correlation_id, query_id
        )
        if marker != "claimed" or claim is None:
            return marker

        if claim.started:
            await _publish_progress(
                event_type="discovery.started",
                run_id=claim.run_id,
                workspace_id=claim.workspace_id,
                correlation_id=correlation_id,
                payload={
                    "status": "running",
                    "planned_query_count": len(claim.planned_ids),
                },
            )

        outcome = await _spawn_attempt(query_id, claim, _resolve_config())

        settlement = _settle_run(
            manager,
            workspace_uuid,
            run_uuid,
            query_id,
            correlation_id,
            outcome,
            claim.planned_ids,
        )
        if settlement.recorded:
            await _publish_attempt_progress(claim, correlation_id, settlement)
        return settlement.status
    finally:
        manager.dispose()
