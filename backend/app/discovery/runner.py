"""Worker-side execution of one discovery query against one retrieval CLI.

The runner is the domain seam between the arq queue and the immutable
observation store. One invocation is split into three phases so a crash can
never leave a database transaction open across a subprocess spawn:

1. CLAIM — one short transaction row-locks the run, refuses missing/terminal
   rows, moves queued->running with its audit event, replays-guards the
   observation pair, and commits.
2. SPAWN — the retrieval CLI runs with NO open transaction or connection.
   Classification happens here too: every outcome becomes an attempt outcome,
   never an exception.
3. SETTLE — one final transaction re-locks the run, authoritatively
   replay-guards the insert, rolls the run up counting only planned queries,
   and transitions it to a terminal status exactly once.
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
from app.discovery.models import DiscoveryRun, RetrievalObservation
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


@dataclass(frozen=True)
class _AttemptConfig:
    """Resolved spawn parameters; tests inject every value."""

    node_bin: str
    cli_path: str
    config_path: str
    evidence_root: Path
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


def _resolve_config(overrides: dict[str, object] | None) -> _AttemptConfig:
    settings = get_settings()
    given = overrides or {}

    def pick(key: str, fallback: object) -> str:
        value = given.get(key, fallback)
        return str(value)

    return _AttemptConfig(
        node_bin=pick("node_bin", settings.retrieval_node_bin),
        cli_path=pick("cli_path", settings.retrieval_cli_path),
        config_path=pick("provider_config_path", settings.discovery_provider_config_path),
        evidence_root=Path(pick("evidence_root", settings.retrieval_evidence_root)),
        timeout_seconds=float(pick("timeout_seconds", settings.retrieval_attempt_timeout_seconds)),
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


def _document_observation(
    run: DiscoveryRun, query_id: str, correlation_id: str, doc: ObservationDocument
) -> RetrievalObservation:
    """Map a validated observation document onto an append-only row."""
    return RetrievalObservation(
        discovery_run_id=run.id,
        workspace_id=run.workspace_id,
        query_id=query_id,
        schema_version=doc.schema_version,
        capability="discovery",
        provider_variant=doc.provider_variant,
        config_sha256=doc.config_sha256,
        observation_id=doc.observation_id,
        status=doc.status,
        failure_class=None,
        failure_reason=(
            redact_sensitive_text(doc.failure_reason) if doc.failure_reason else None
        ),
        source_url=doc.source_url,
        final_url=doc.final_url,
        external_source_id=None,
        candidate_count=doc.candidate_count or 0,
        candidates=doc.candidates or [],
        normalized_sha256=doc.normalized_sha256,
        normalized_content_sha256=None,
        elapsed_ms=doc.elapsed_ms,
        started_at=_parse_iso(doc.started_at),
        completed_at=_parse_iso(doc.completed_at),
        runtime=doc.runtime,
        network=doc.network,
        raw_artifact=doc.raw_artifact,
        evidence_directory=doc.evidence_directory,
        correlation_id=correlation_id,
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
    return RetrievalObservation(
        discovery_run_id=run.id,
        workspace_id=run.workspace_id,
        query_id=query_id,
        schema_version=OBSERVATION_SCHEMA_VERSION,
        capability="discovery",
        provider_variant=str(plan.get("provider_variant") or "unknown"),
        config_sha256=str(plan.get("config_sha256") or "0" * 64),
        observation_id=f"{run.id}:{query_id}:unclassified",
        status="failed",
        failure_class=failure_class,
        failure_reason=redact_sensitive_text(failure_reason),
        candidate_count=0,
        candidates=[],
        evidence_directory=str(output_root),
        correlation_id=correlation_id,
    )


def _outcome_to_row(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    output_root: Path,
    outcome: _AttemptOutcome,
) -> RetrievalObservation:
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
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="transport_timeout",
            failure_reason=(
                f"retrieval attempt exceeded {timeout_seconds:g}s and was killed"
            ),
        )

    if result.evidence_unreadable:
        # The authoritative disk document exists but cannot be read; the
        # stdout projection must never stand in for it.
        return _AttemptOutcome(
            evidence_directory=str(output_root),
            failure_class="evidence_unreadable",
            failure_reason=(
                "observation.json could not be read from the evidence "
                f"directory (stderr tail: {result.stderr_tail!r})"
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
                evidence_directory=str(doc.evidence_directory),
                failure_class="contract_violation",
                failure_reason=(
                    f"observation capability {doc.capability!r} is not "
                    f"{EXPECTED_CAPABILITY!r}"
                ),
            )
        return _AttemptOutcome(evidence_directory=str(doc.evidence_directory), doc=doc)

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


def _roll_up_run(
    session: Session, run: DiscoveryRun, planned_ids: tuple[str, ...], correlation_id: str
) -> None:
    """Recount observations under lock and close the run when complete.

    Only observations whose query_id appears in method_plan['queries'] count
    toward completion, and an already-terminal run is never transitioned
    again.
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

    run.completed_at = _now()
    run.status = final_status
    run.metrics = {
        "counts": dict(sorted(Counter(statuses).items())),
        "total_elapsed_ms": sum(row.elapsed_ms or 0 for row in rows),
        "cost_usd": None,
    }
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
    *,
    overrides_refused: bool,
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
        violation_reason: str | None = None
        if QUERY_ID_PATTERN.fullmatch(query_id) is None:
            violation_reason = (
                f"query id {query_id!r} does not match ^[A-Za-z0-9_-]{{1,64}}$"
            )
        elif overrides_refused:
            violation_reason = (
                "spawn overrides were provided while allow_overrides is False; "
                "untrusted spawn inputs are refused, never silently ignored"
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

        # The elif chain above records a violation whenever the id is absent
        # from the plan, so a claimed invocation always carries an entry.
        assert entry is not None
        return "claimed", _Claim(run_id=run_id, planned_ids=planned_ids, entry=entry)


async def _spawn_attempt(
    query_id: str, claim: _Claim, config: _AttemptConfig
) -> _AttemptOutcome:
    """Phase 2: spawn the CLI — no DB tx is open, kwargs are already vetted."""
    output_root = config.evidence_root / str(claim.run_id)

    input_path = output_root / f"input-{query_id}.json"
    output_root.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps({"queries": [claim.entry]}))

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
    overrides: dict[str, object] | None = None,
    allow_overrides: bool = False,
) -> str:
    """Execute one query of one discovery run; returns the run's status.

    Spawn overrides are honored only when the caller explicitly passes
    allow_overrides=True (tests do; the registered worker function does not).
    Overrides handed to a non-trusting invocation are recorded as a
    contract_violation observation rather than silently ignored.
    """
    del ctx  # arq passes its worker context; the runner does not need it.
    settings = get_settings()
    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        overrides_refused = bool(overrides) and not allow_overrides
        marker, claim = _claim_run(
            manager,
            uuid.UUID(run_id),
            correlation_id,
            query_id,
            overrides_refused=overrides_refused,
        )
        if marker != "claimed" or claim is None:
            return marker

        config = _resolve_config(overrides if allow_overrides else None)
        outcome = await _spawn_attempt(query_id, claim, config)

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
