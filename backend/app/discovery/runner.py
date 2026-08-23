"""Worker-side execution of one discovery query against one retrieval CLI.

The runner is the domain seam between the arq queue and the immutable
observation store. One invocation owns exactly one transaction: it locks the
run row, transitions queued->running, spawns the CLI, classifies the outcome,
writes the observation, and rolls the run up — committing once.
"""

import asyncio
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
)

# Ruling sets for the run roll-up. Succeeded means nothing was lost;
# usable includes incomplete because partial evidence still has value.
SUCCEEDED_STATUSES = frozenset({"success", "no_results"})
USABLE_STATUSES = frozenset({"success", "no_results", "incomplete"})

# Stderr fingerprints emitted by the retrieval CLI's runtime gate.
RUNTIME_VERIFICATION_MARKERS = ("verifyRuntime", "Node version", "Obscura version")


@dataclass(frozen=True)
class _AttemptConfig:
    """Resolved spawn parameters; tests inject every value."""

    node_bin: str
    cli_path: str
    config_path: str
    evidence_root: Path
    timeout_seconds: float


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
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _plan_queries(method_plan: dict[str, object]) -> list[dict[str, Any]]:
    queries = method_plan.get("queries") or []
    return cast(list[dict[str, Any]], queries)


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
        failure_reason=doc.failure_reason,
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
        failure_reason=failure_reason,
        candidate_count=0,
        candidates=[],
        evidence_directory=str(output_root),
        correlation_id=correlation_id,
    )


def _classify_result(
    run: DiscoveryRun,
    query_id: str,
    correlation_id: str,
    output_root: Path,
    result: cli.CliResult,
    timeout_seconds: float,
) -> RetrievalObservation:
    if result.timed_out:
        return _unclassified_observation(
            run,
            query_id,
            correlation_id,
            output_root,
            failure_class="transport_timeout",
            failure_reason=(
                f"retrieval attempt exceeded {timeout_seconds:g}s and was killed"
            ),
        )

    if result.observation_doc is not None:
        raw_doc = result.observation_doc
        try:
            doc = parse_observation(raw_doc)
        except UnknownObservationSchemaVersion as error:
            return _unclassified_observation(
                run,
                query_id,
                correlation_id,
                output_root,
                failure_class="unknown_observation_schema",
                failure_reason=str(error),
            )
        except UnknownObservationStatus as error:
            return _unclassified_observation(
                run,
                query_id,
                correlation_id,
                output_root,
                failure_class="unknown_observation_status",
                failure_reason=str(error),
            )
        return _document_observation(run, query_id, correlation_id, doc)

    if result.exit_code == 1:
        if any(marker in result.stderr_tail for marker in RUNTIME_VERIFICATION_MARKERS):
            failure_class = "runtime_verification_failed"
        else:
            failure_class = "wrapper_error"
    else:
        failure_class = "transport_error"
    return _unclassified_observation(
        run,
        query_id,
        correlation_id,
        output_root,
        failure_class=failure_class,
        failure_reason=(
            f"retrieval CLI exited {result.exit_code} without an observation "
            f"(stderr tail: {result.stderr_tail[-500:]!r})"
        ),
    )


def _roll_up_run(
    session: Session, run: DiscoveryRun, expected_queries: int, correlation_id: str
) -> None:
    """Recount observations under lock and close the run when complete."""
    rows = list(
        session.scalars(
            select(RetrievalObservation)
            .where(RetrievalObservation.discovery_run_id == run.id)
            .with_for_update()
        )
    )
    if len(rows) < expected_queries:
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


async def run_discovery_query(
    ctx: object,
    *,
    run_id: str,
    correlation_id: str,
    query_id: str,
    overrides: dict[str, object] | None = None,
) -> str:
    """Execute one query of one discovery run; returns the run's status."""
    del ctx  # arq passes its worker context; the runner does not need it.
    config = _resolve_config(overrides)
    settings = get_settings()
    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        with manager.session_factory() as session, session.begin():
            run = session.execute(
                select(DiscoveryRun)
                .where(DiscoveryRun.id == uuid.UUID(run_id))
                .with_for_update()
            ).scalar_one_or_none()
            if run is None:
                return "run_missing"

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

            queries = _plan_queries(run.method_plan)

            # Replay guard: an observation for this pair already exists, so
            # neither the spawn nor a duplicate insert may happen again.
            already_recorded = session.execute(
                select(RetrievalObservation.id).where(
                    RetrievalObservation.discovery_run_id == run.id,
                    RetrievalObservation.query_id == query_id,
                )
            ).scalar_one_or_none()
            if already_recorded is not None:
                return run.status

            output_root = config.evidence_root / run_id
            entry = next(
                (q for q in queries if str(q.get("id")) == query_id), None
            )
            if entry is None:
                session.add(
                    _unclassified_observation(
                        run,
                        query_id,
                        correlation_id,
                        output_root,
                        failure_class="contract_violation",
                        failure_reason=(
                            f"query {query_id!r} is not present in the run's method plan"
                        ),
                    )
                )
                _roll_up_run(session, run, len(queries), correlation_id)
                return run.status

            input_path = output_root / f"input-{query_id}.json"
            output_root.mkdir(parents=True, exist_ok=True)
            input_path.write_text(json.dumps({"queries": [entry]}))

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

            session.add(
                _classify_result(
                    run, query_id, correlation_id, output_root, result, config.timeout_seconds
                )
            )
            session.flush()
            _roll_up_run(session, run, len(queries), correlation_id)
            return run.status
    finally:
        manager.dispose()
