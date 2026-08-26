"""Worker-side execution of one discovery query against one retrieval CLI.

The runner is the domain seam between the arq queue and the immutable
observation store. One invocation is split into three phases so a crash can
never leave a database transaction open across a subprocess spawn:

1. CLAIM — one short transaction row-locks the run, refuses missing/terminal
   rows, moves queued->running with its audit event, replays-guards the
   observation pair, and commits.
2. SPAWN — the retrieval CLI runs with NO open transaction or connection.
   Query inputs are staged in the Python-owned scratch root (the evidence
   output root belongs to the CLI); classification happens here too: every
   outcome becomes an attempt outcome, never an exception.
3. SETTLE — one final transaction re-locks the run, authoritatively
   replay-guards the insert, rolls the run up counting only planned queries,
   and transitions it to a terminal status exactly once.

Spawn configuration comes exclusively from settings: there is deliberately
no override channel on this function, so a queue caller can never substitute
binaries or paths.
"""

import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditing.service import record_audit
from app.config import get_settings
from app.db import DatabaseSessionManager
from app.discovery import cli
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
    evidence_root: Path
    input_root: Path
    timeout_seconds: float


@dataclass(frozen=True)
class _Claim:
    """Plan snapshot taken under the claim lock, reused outside the tx."""

    run_id: uuid.UUID
    planned_ids: tuple[str, ...]
    entry: dict[str, Any]


@dataclass(frozen=True)
class _AttemptOutcome:
    """Classified end state of one attempt; never raised, always persisted."""

    evidence_directory: str
    doc: ObservationDocument | None = None
    failure_class: str | None = None
    failure_reason: str | None = None


def _resolve_config() -> _AttemptConfig:
    settings = get_settings()
    return _AttemptConfig(
        node_bin=settings.retrieval_node_bin,
        cli_path=str(settings.retrieval_cli_path),
        config_path=str(settings.discovery_provider_config_path),
        evidence_root=Path(settings.retrieval_evidence_root),
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
    evidence_directory: str,
    failure_class: str | None = None,
    failure_reason: str | None = None,
    source_url: str | None = None,
    final_url: str | None = None,
    candidate_count: int = 0,
    candidates: list[dict[str, Any]] | None = None,
    normalized_sha256: str | None = None,
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
        capability=EXPECTED_CAPABILITY,
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
        external_source_id=None,
        candidate_count=candidate_count,
        candidates=candidates or [],
        normalized_sha256=normalized_sha256,
        normalized_content_sha256=None,
        elapsed_ms=elapsed_ms,
        started_at=started_at,
        completed_at=completed_at,
        runtime=runtime,
        network=network,
        raw_artifact=raw_artifact,
        evidence_directory=evidence_directory,
        correlation_id=correlation_id,
    )


def _document_observation(
    run: DiscoveryRun, query_id: str, correlation_id: str, doc: ObservationDocument
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
        evidence_directory=doc.evidence_directory,
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
        raw_artifact=doc.raw_artifact,
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
        evidence_directory=str(output_root),
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
    if outcome.failure_class is not None and outcome.failure_class not in FAILURE_CLASSES:
        raise ValueError(
            f"classifier produced out-of-vocabulary failure_class "
            f"{outcome.failure_class!r}"
        )
    if outcome.doc is not None:
        return _document_observation(run, query_id, correlation_id, outcome.doc)
    return _unclassified_observation(
        run,
        query_id,
        correlation_id,
        Path(outcome.evidence_directory) if outcome.evidence_directory else output_root,
        failure_class=outcome.failure_class or "transport_error",
        failure_reason=outcome.failure_reason or "unclassified retrieval failure",
    )


def _classify_result(
    result: cli.CliResult, output_root: Path, timeout_seconds: float
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
        if doc.capability != EXPECTED_CAPABILITY:
            return _AttemptOutcome(
                evidence_directory=doc.evidence_directory,
                failure_class="contract_violation",
                failure_reason=(
                    f"observation capability {doc.capability!r} is not "
                    f"{EXPECTED_CAPABILITY!r}"
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
    session: Session, run: DiscoveryRun, planned_ids: tuple[str, ...], correlation_id: str
) -> None:
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
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id.in_(planned_ids),
            )
            .with_for_update()
        )
    )
    if len(rows) < len(planned_ids):
        return
    if run.status in TERMINAL_RUN_STATUSES:
        return

    previous_status = run.status
    statuses = [row.status for row in rows]
    if all(status in SUCCEEDED_STATUSES for status in statuses):
        final_status = "succeeded"
    elif not any(status in USABLE_STATUSES for status in statuses):
        final_status = "failed"
    else:
        final_status = "partial"

    measured_requests = [
        count for count in (_network_request_count(row) for row in rows) if count is not None
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
        before={"status": previous_status},
        after={"status": final_status},
        correlation_id=correlation_id,
    )


def _claim_run(
    manager: DatabaseSessionManager,
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
            select(DiscoveryRun).where(DiscoveryRun.id == run_id).with_for_update()
        ).scalar_one_or_none()
        if run is None:
            return "run_missing", None
        if run.status in TERMINAL_RUN_STATUSES:
            return "already_done", None

        # Idempotent lifecycle transition: only the first invocation moves
        # the run out of queued and writes the start audit event.
        if run.status == "queued":
            run.status = "running"
            run.started_at = _now()
            record_audit(
                session,
                actor="worker",
                action="discovery_run.started",
                target_type="discovery_run",
                target_id=run.id,
                before={"status": "queued"},
                after={"status": "running"},
                correlation_id=correlation_id,
            )

        # Replay guard ahead of the spawn: a redelivered job whose
        # observation already exists must not rerun the attempt.
        already_recorded = session.execute(
            select(RetrievalObservation.id).where(
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id == query_id,
            )
        ).scalar_one_or_none()
        if already_recorded is not None:
            return run.status, None

        planned_queries = _plan_queries(run.method_plan)
        planned_ids = tuple(str(q.get("id")) for q in planned_queries)
        entry = next(
            (q for q in planned_queries if str(q.get("id")) == query_id), None
        )

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
            output_root = get_settings().retrieval_evidence_root / str(run_id)
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
        return "claimed", _Claim(run_id=run_id, planned_ids=planned_ids, entry=entry)


async def _spawn_attempt(query_id: str, claim: _Claim, config: _AttemptConfig) -> _AttemptOutcome:
    """Phase 2: spawn the CLI — no DB tx is open, kwargs are already vetted.

    The query input document is staged in the Python-owned scratch root; the
    evidence output root is owned by the CLI and only ever read back.
    """
    input_dir = config.input_root / str(claim.run_id)
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"input-{query_id}.json"
    input_path.write_text(json.dumps({"queries": [claim.entry]}))

    output_root = config.evidence_root / str(claim.run_id)
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
    return _classify_result(result, output_root, config.timeout_seconds)


def _settle_run(
    manager: DatabaseSessionManager,
    run_id: uuid.UUID,
    query_id: str,
    correlation_id: str,
    outcome: _AttemptOutcome,
    planned_ids: tuple[str, ...],
) -> str:
    """Phase 3: single final transaction inserts and closes the run."""
    with manager.session_factory() as session, session.begin():
        run = session.execute(
            select(DiscoveryRun).where(DiscoveryRun.id == run_id).with_for_update()
        ).scalar_one_or_none()
        if run is None:
            return "run_missing"

        # Terminal runs must not be mutated — late arrivals observe
        # already_done instead of appending evidence that diverges from
        # frozen metrics. See runner invariant at top of module.
        if run.status in TERMINAL_RUN_STATUSES:
            return "already_done"

        # Authoritative replay guard: skip the insert entirely when another
        # invocation already recorded this pair.
        already_recorded = session.execute(
            select(RetrievalObservation.id).where(
                RetrievalObservation.discovery_run_id == run.id,
                RetrievalObservation.query_id == query_id,
            )
        ).scalar_one_or_none()
        if already_recorded is not None:
            return run.status

        session.add(
            _outcome_to_row(
                run, query_id, correlation_id, Path(outcome.evidence_directory), outcome
            )
        )
        session.flush()
        _roll_up_run(session, run, planned_ids, correlation_id)
        return run.status


async def run_discovery_query(
    ctx: object,
    *,
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
        marker, claim = _claim_run(manager, uuid.UUID(run_id), correlation_id, query_id)
        if marker != "claimed" or claim is None:
            return marker

        outcome = await _spawn_attempt(query_id, claim, _resolve_config())

        return _settle_run(
            manager,
            uuid.UUID(run_id),
            query_id,
            correlation_id,
            outcome,
            claim.planned_ids,
        )
    finally:
        manager.dispose()
