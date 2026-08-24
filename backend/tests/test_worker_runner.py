"""Worker runner: one discovery query end-to-end against a stub CLI.

Immutability posture: retrieval_observations can never be deleted, so every
test seeds its own uuid-keyed campaign/run rows in a dedicated worker test
database and asserts by run id. No trigger is ever bypassed; the dedicated
database keeps those append-only rows away from suites that clean shared
tables.
"""

import asyncio
import json
import textwrap
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from psycopg import connect, sql
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.auditing.models import AuditEvent
from app.campaigns.models import Campaign
from app.config import get_settings
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.discovery.runner import _parse_iso, run_discovery_query
from app.discovery.worker import reap_stale_running_runs
from app.workspaces import DEFAULT_WORKSPACE_ID

WORKER_DATABASE_NAME = "aptori_outreach_worker_test"
WORKER_DATABASE_URL = f"postgresql+psycopg://@/{WORKER_DATABASE_NAME}"


@pytest.fixture(scope="session")
def worker_database_url() -> Iterator[str]:
    """Migrate a dedicated append-only database for discovery worker tests."""
    with connect("postgresql://", autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (WORKER_DATABASE_NAME,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(WORKER_DATABASE_NAME))
            )
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", WORKER_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield WORKER_DATABASE_URL


@pytest.fixture()
def worker_db(worker_database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Point cached settings at the worker database for the duration."""
    monkeypatch.setenv("APTORI_DATABASE_URL", worker_database_url)
    get_settings.cache_clear()
    yield worker_database_url
    get_settings.cache_clear()


def write_stub_node(tmp_path: Path, docs_dir: Path, *, sleep_seconds: int | None = None) -> Path:
    """Generate a fake node binary serving fixture docs keyed by query id."""
    if sleep_seconds is not None:
        tail = f"sleep {sleep_seconds}\nexit 0\n"
    else:
        tail = (
            'DOC="$DOCS/$ID.json"\n'
            'sed -e "s|@@EVIDENCE@@|$OUT|g" -e "s|@@QID@@|$ID|g" '
            '"$DOC" > "$ATTEMPT_DIR/observation.json"\n'
            'cat "$ATTEMPT_DIR/observation.json"\n'
            "exit 0\n"
        )
    return write_raw_stub(tmp_path, f'DOCS="{docs_dir}"\n' + tail)


def write_raw_stub(tmp_path: Path, tail: str) -> Path:
    """Generate a fake node binary running an arbitrary bash tail."""
    stub = tmp_path / "fake-node.js"
    stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            OUT=""
            ID=""
            while [[ $# -gt 0 ]]; do
              case "$1" in
                --output-root) OUT="$2"; shift 2 ;;
                --id) ID="$2"; shift 2 ;;
                *) shift ;;
              esac
            done
            ATTEMPT_DIR="$OUT/attempt-$ID"
            mkdir -p "$ATTEMPT_DIR"
            """
        )
        + textwrap.dedent(tail)
    )
    stub.chmod(0o755)
    return stub


def fixture_doc(qid: str, status: str = "success", **overrides: object) -> dict[str, object]:
    """A discovery-shaped document matching packages/obscura-retrieval."""
    doc: dict[str, object] = {
        "schemaVersion": 1,
        "observationId": f"attempt-{qid}",
        "capability": "discovery",
        "providerVariant": "obscura-duckduckgo-lite",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00Z",
        "completedAt": "2026-08-23T00:00:01Z",
        "elapsedMs": {"q-a": 1200, "q-b": 300}.get(qid, 800),
        "status": status,
        "failureReason": None if status == "success" else f"because {status}",
        "input": {"id": qid, "query": f"search {qid}"},
        "sourceUrl": "https://lite.duckduckgo.com/lite/?q=x",
        "finalUrl": "https://lite.duckduckgo.com/lite/?q=x",
        "response": {"navigationStatus": 200},
        "normalizedSha256": "a" * 64,
        "candidateCount": 3,
        "candidates": [{"title": "t", "url": "https://reddit.com/r/x"}],
        "network": {"requests": 2},
        "runtime": {"node": "20.18.0"},
        "evidenceDirectory": "@@EVIDENCE@@/attempt-@@QID@@",
    }
    doc.update(overrides)
    return doc


class StubHarness:
    """Stub executable plus fixture docs for one test."""

    def __init__(self, tmp_path: Path, *, sleep_seconds: int | None = None) -> None:
        self.docs_dir = tmp_path / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_root = tmp_path / "evidence-runs"
        self.node_bin = write_stub_node(tmp_path, self.docs_dir, sleep_seconds=sleep_seconds)
        self.cli_path = tmp_path / "retrieval-cli.js"
        self.config_path = tmp_path / "provider-config.json"
        self.config_path.write_text(json.dumps({"providerVariant": "stub"}))
        self.timeout_seconds = 10

    def add_doc(self, qid: str, doc: dict[str, object]) -> None:
        (self.docs_dir / f"{qid}.json").write_text(json.dumps(doc))

    def overrides(self) -> dict[str, object]:
        return {
            "node_bin": str(self.node_bin),
            "cli_path": str(self.cli_path),
            "provider_config_path": str(self.config_path),
            "evidence_root": str(self.evidence_root),
            "timeout_seconds": self.timeout_seconds,
        }


def seed_run(database_url: str, *, correlation_id: str, query_ids: list[str]) -> uuid.UUID:
    """Insert an ACTIVE campaign and a QUEUED run referencing the queries."""
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            campaign = Campaign(
                workspace_id=DEFAULT_WORKSPACE_ID,
                name=f"worker-{uuid.uuid4().hex}",
                promotion_posture="expertise_first",
                status="active",
            )
            session.add(campaign)
            session.flush()
            method_plan = {
                "provider_variant": "obscura-duckduckgo-lite",
                "config_sha256": "0" * 64,
                "queries": [
                    {"id": qid, "query": f"search {qid}", "subreddits": ["cybersecurity"]}
                    for qid in query_ids
                ],
            }
            run = DiscoveryRun(
                workspace_id=DEFAULT_WORKSPACE_ID,
                campaign_id=campaign.id,
                status="queued",
                method_plan=method_plan,
                correlation_id=correlation_id,
            )
            session.add(run)
            session.flush()
            run_id = run.id
            session.commit()
            return run_id
    finally:
        engine.dispose()


def invoke(run_id: uuid.UUID, qid: str, harness: StubHarness) -> str:
    return asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id=qid,
            overrides=harness.overrides(),
            allow_overrides=True,
        )
    )


def raw_overrides(stub: Path, tmp_path: Path, *, timeout_seconds: float = 10) -> dict[str, object]:
    """Spawn overrides pointing at an ad-hoc stub for classification tests."""
    config_path = tmp_path / "provider-config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps({"providerVariant": "stub"}))
    return {
        "node_bin": str(stub),
        "cli_path": str(tmp_path / "retrieval-cli.js"),
        "provider_config_path": str(config_path),
        "evidence_root": str(tmp_path / "evidence-runs"),
        "timeout_seconds": timeout_seconds,
    }


def load_run(database_url: str, run_id: uuid.UUID) -> DiscoveryRun:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            run = session.get(DiscoveryRun, run_id)
            assert run is not None
            session.expunge(run)
            return run
    finally:
        engine.dispose()


def load_rows(database_url: str, run_id: uuid.UUID) -> list[RetrievalObservation]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            rows = list(
                session.scalars(
                    select(RetrievalObservation)
                    .where(RetrievalObservation.discovery_run_id == run_id)
                    .order_by(RetrievalObservation.creation_order)
                )
            )
            for row in rows:
                session.expunge(row)
            return rows
    finally:
        engine.dispose()


def load_audit(database_url: str, run_id: uuid.UUID) -> list[AuditEvent]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            events = list(
                session.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.target_id == run_id)
                    .order_by(AuditEvent.event_order)
                )
            )
            for event in events:
                session.expunge(event)
            return events
    finally:
        engine.dispose()


def row_by_query(rows: list[RetrievalObservation], qid: str) -> RetrievalObservation:
    matches = [row for row in rows if row.query_id == qid]
    assert len(matches) == 1, f"expected exactly one row for {qid}, got {len(matches)}"
    return matches[0]


def test_success_and_no_results_complete_the_run(worker_db: str, tmp_path: Path) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    harness.add_doc("q-b", fixture_doc("q-b", "no_results"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a", harness)
    final_status = invoke(run_id, "q-b", harness)

    assert final_status == "succeeded"
    run = load_run(worker_db, run_id)
    assert run.status == "succeeded"
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.metrics is not None
    assert run.metrics["counts"] == {"success": 1, "no_results": 1}
    assert run.metrics["total_elapsed_ms"] == 1500
    assert run.metrics["cost_usd"] is None

    rows = load_rows(worker_db, run_id)
    success_row = row_by_query(rows, "q-a")
    no_results_row = row_by_query(rows, "q-b")
    assert success_row.status == "success"
    assert success_row.failure_class is None
    assert success_row.candidate_count == 3
    assert success_row.observation_id == "attempt-q-a"
    assert success_row.evidence_directory.endswith("attempt-q-a")
    assert no_results_row.status == "no_results"


def test_success_plus_blocked_is_partial(worker_db: str, tmp_path: Path) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    harness.add_doc("q-b", fixture_doc("q-b", "blocked"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a", harness)
    final_status = invoke(run_id, "q-b", harness)

    assert final_status == "partial"
    run = load_run(worker_db, run_id)
    assert run.status == "partial"
    blocked_row = row_by_query(load_rows(worker_db, run_id), "q-b")
    assert blocked_row.status == "blocked"
    assert blocked_row.failure_class is None


def test_blocked_and_rate_limited_fail_the_run(worker_db: str, tmp_path: Path) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "blocked"))
    harness.add_doc("q-b", fixture_doc("q-b", "rate_limited"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a", harness)
    final_status = invoke(run_id, "q-b", harness)

    assert final_status == "failed"
    run = load_run(worker_db, run_id)
    assert run.status == "failed"
    assert run.metrics is not None
    assert run.metrics["counts"] == {"blocked": 1, "rate_limited": 1}


def test_unknown_schema_version_persists_unclassified_failure(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    harness.add_doc("q-bad", fixture_doc("q-bad", "success", schemaVersion=99))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-bad"])

    invoke(run_id, "q-a", harness)
    final_status = invoke(run_id, "q-bad", harness)

    assert final_status == "partial"
    run = load_run(worker_db, run_id)
    assert run.status == "partial"

    bad_row = row_by_query(load_rows(worker_db, run_id), "q-bad")
    assert bad_row.status == "failed"
    assert bad_row.failure_class == "unknown_observation_schema"
    assert bad_row.observation_id == f"{run_id}:q-bad:unclassified"
    assert bad_row.evidence_directory == str(harness.evidence_root / str(run_id))


def test_replay_same_query_does_not_duplicate_observation(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    first_status = invoke(run_id, "q-a", harness)
    # The completed run is terminal, so a redelivery observes 'already_done'.
    second_status = invoke(run_id, "q-a", harness)

    assert first_status == "succeeded"
    assert second_status == "already_done"
    assert len(load_rows(worker_db, run_id)) == 1
    started_events = [
        event for event in load_audit(worker_db, run_id) if event.action == "discovery_run.started"
    ]
    assert len(started_events) == 1


def test_correlation_id_flows_to_observations_and_audit(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    invoke(run_id, "q-a", harness)

    rows = load_rows(worker_db, run_id)
    assert [row.correlation_id for row in rows] == ["corr-123"]
    events = load_audit(worker_db, run_id)
    actions = sorted(event.action for event in events)
    assert actions == ["discovery_run.completed", "discovery_run.started"]
    assert all(event.actor == "worker" for event in events)
    assert all(event.correlation_id == "corr-123" for event in events)
    completed = next(event for event in events if event.action == "discovery_run.completed")
    assert completed.before == {"status": "running"}
    assert completed.after == {"status": "succeeded"}


def test_timeout_classifies_transport_timeout(worker_db: str, tmp_path: Path) -> None:
    harness = StubHarness(tmp_path, sleep_seconds=30)
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-slow"])
    harness.timeout_seconds = 1

    final_status = invoke(run_id, "q-slow", harness)

    assert final_status == "failed"
    run = load_run(worker_db, run_id)
    assert run.status == "failed"
    slow_row = row_by_query(load_rows(worker_db, run_id), "q-slow")
    assert slow_row.status == "failed"
    assert slow_row.failure_class == "transport_timeout"


def test_wrapper_error_classified_from_plain_exit_one(worker_db: str, tmp_path: Path) -> None:
    stub = write_raw_stub(tmp_path, 'echo "boom: wrapper crashed" >&2\nexit 1\n')
    overrides = raw_overrides(stub, tmp_path)
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    final_status = asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id="q-x",
            overrides=overrides,
            allow_overrides=True,
        )
    )

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "wrapper_error"


def test_transport_error_classified_from_other_nonzero_exit(
    worker_db: str, tmp_path: Path
) -> None:
    stub = write_raw_stub(tmp_path, 'echo "segfault-ish" >&2\nexit 2\n')
    overrides = raw_overrides(stub, tmp_path)
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id="q-x",
            overrides=overrides,
            allow_overrides=True,
        )
    )

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.failure_class == "transport_error"


def test_runtime_verification_marker_is_classified(worker_db: str, tmp_path: Path) -> None:
    stub = write_raw_stub(
        tmp_path, 'echo "Error: verifyRuntime failed: Node version too old" >&2\nexit 1\n'
    )
    overrides = raw_overrides(stub, tmp_path)
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id="q-x",
            overrides=overrides,
            allow_overrides=True,
        )
    )

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.failure_class == "runtime_verification_failed"


def test_oversized_document_field_is_contract_violation(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success", observationId="x" * 300))
    harness.add_doc("q-b", fixture_doc("q-b", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a", harness)
    final_status = invoke(run_id, "q-b", harness)

    assert final_status == "partial"
    bad_row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert bad_row.status == "failed"
    assert bad_row.failure_class == "contract_violation"
    assert bad_row.observation_id == f"{run_id}:q-a:unclassified"


def test_unknown_observation_status_persists_classification(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "kind_of_fine"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    final_status = invoke(run_id, "q-a", harness)

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert row.status == "failed"
    assert row.failure_class == "unknown_observation_status"


def test_non_discovery_capability_is_contract_violation(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success", capability="thread_fetch"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    final_status = invoke(run_id, "q-a", harness)

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert row.failure_class == "contract_violation"
    assert "capability" in (row.failure_reason or "")


def test_evidence_unreadable_beats_stdout_projection(
    worker_db: str, tmp_path: Path
) -> None:
    """Garbage disk document plus a plausible stdout projection must fail.

    The stdout projection lacks schemaVersion guarantees, so it can never
    feed the full parser; the honest outcome is evidence_unreadable.
    """
    stub = write_raw_stub(
        tmp_path,
        'printf "garbage not json" > "$ATTEMPT_DIR/observation.json"\n'
        'printf \'{"status":"success","observationId":"attempt-%s",'
        '"evidenceDirectory":"%s"}\' "$ID" "$ATTEMPT_DIR"\n'
        "exit 0\n",
    )
    overrides = raw_overrides(stub, tmp_path)
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    final_status = asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id="q-x",
            overrides=overrides,
            allow_overrides=True,
        )
    )

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "evidence_unreadable"


def test_reaper_fails_stale_running_run(worker_db: str) -> None:
    run_id = seed_run(worker_db, correlation_id="corr-reap", query_ids=["q-a"])
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            run = session.get(DiscoveryRun, run_id)
            assert run is not None
            run.status = "running"
            run.started_at = datetime.now(UTC) - timedelta(hours=1)
            session.commit()
    finally:
        engine.dispose()

    # Append-only database: earlier suites may have left other stale rows,
    # so only this run's own outcome may be asserted exactly.
    reaped = asyncio.run(reap_stale_running_runs(None))
    assert reaped >= 1

    stale_run = load_run(worker_db, run_id)
    assert stale_run.status == "failed"
    assert stale_run.completed_at is not None
    assert stale_run.metrics is not None
    assert stale_run.metrics["reaped"] is True
    events = load_audit(worker_db, run_id)
    reaped_events = [event for event in events if event.action == "discovery_run.reaped"]
    assert len(reaped_events) == 1
    assert reaped_events[0].correlation_id == "corr-reap"
    assert reaped_events[0].before == {"status": "running"}
    assert reaped_events[0].after == {"status": "failed"}


def test_reaper_leaves_fresh_runs_alone(worker_db: str) -> None:
    run_id = seed_run(worker_db, correlation_id="corr-fresh", query_ids=["q-a"])
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            run = session.get(DiscoveryRun, run_id)
            assert run is not None
            run.status = "running"
            run.started_at = datetime.now(UTC)
            session.commit()
    finally:
        engine.dispose()

    asyncio.run(reap_stale_running_runs(None))

    fresh_run = load_run(worker_db, run_id)
    assert fresh_run.status == "running"
    assert fresh_run.metrics is None
    reaped_events = [
        event
        for event in load_audit(worker_db, run_id)
        if event.action == "discovery_run.reaped"
    ]
    assert reaped_events == []


def test_overrides_are_refused_without_allow_overrides_flag(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    final_status = asyncio.run(
        run_discovery_query(
            None,
            run_id=str(run_id),
            correlation_id="corr-123",
            query_id="q-a",
            overrides=harness.overrides(),
            allow_overrides=False,
        )
    )

    # The refusal is recorded, never silently ignored — and nothing spawned.
    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert row.failure_class == "contract_violation"
    assert "allow_overrides" in (row.failure_reason or "")
    assert not (harness.evidence_root / str(run_id)).exists()


def test_invalid_query_id_charset_is_contract_violation(
    worker_db: str, tmp_path: Path
) -> None:
    harness = StubHarness(tmp_path)
    harness.add_doc("q-a", fixture_doc("q-a", "success"))
    harness.add_doc("q-b", fixture_doc("q-b", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    def call(qid: str) -> str:
        return asyncio.run(
            run_discovery_query(
                None,
                run_id=str(run_id),
                correlation_id="corr-123",
                query_id=qid,
                overrides=harness.overrides(),
                allow_overrides=True,
            )
        )

    first = call("q-a")
    hostile = call("../escape/id")
    final_status = call("q-b")

    assert first == "running"
    # The hostile invocation is recorded but never satisfies the plan: only
    # planned query ids rule the run, and both of those succeeded.
    assert final_status == "succeeded"
    rows = load_rows(worker_db, run_id)
    assert len(rows) == 3
    hostile_row = next(row for row in rows if row.query_id == "../escape/id")
    assert hostile_row.failure_class == "contract_violation"
    assert "A-Za-z0-9_-" in (hostile_row.failure_reason or "")
    run = load_run(worker_db, run_id)
    assert run.metrics is not None
    counts = run.metrics["counts"]
    assert isinstance(counts, dict)
    assert set(counts) == {"success"}  # the hostile row does not count
    # The hostile id never reached the filesystem.
    assert not list(harness.evidence_root.rglob("*escape*"))


def test_parse_iso_rejects_timezone_naive_timestamps() -> None:
    aware = _parse_iso("2026-08-23T00:00:00Z")
    assert aware is not None
    assert aware.tzinfo is not None

    naive = _parse_iso("2026-08-23T00:00:00")
    assert naive is None

    garbage = _parse_iso("not a timestamp")
    assert garbage is None

    absent = _parse_iso(None)
    assert absent is None


def test_midrun_replay_returns_running_without_respawning(
    worker_db: str, tmp_path: Path
) -> None:
    """A redelivery while other queries are pending must not rerun the CLI."""
    counter = tmp_path / "spawns.log"
    stub = write_raw_stub(
        tmp_path,
        f'echo x >> "{counter}"\n'
        'DOC="$OUT/../docs/$ID.json"\n'
        'sed -e "s|@@EVIDENCE@@|$OUT|g" -e "s|@@QID@@|$ID|g" '
        '"$DOC" > "$ATTEMPT_DIR/observation.json"\n'
        'cat "$ATTEMPT_DIR/observation.json"\n'
        "exit 0\n",
    )
    overrides = raw_overrides(stub, tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "q-a.json").write_text(json.dumps(fixture_doc("q-a", "success")))
    (docs_dir / "q-b.json").write_text(json.dumps(fixture_doc("q-b", "blocked")))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    def call(qid: str) -> str:
        return asyncio.run(
            run_discovery_query(
                None,
                run_id=str(run_id),
                correlation_id="corr-123",
                query_id=qid,
                overrides=overrides,
                allow_overrides=True,
            )
        )

    first = call("q-a")
    replayed = call("q-a")

    assert first == "running"
    assert replayed == "running"
    assert counter.read_text().count("x") == 1
    assert len(load_rows(worker_db, run_id)) == 1


def test_worker_settings_registers_the_plain_runner() -> None:
    """The worker trusts settings alone: no overrides, one try, no results kept."""
    import inspect

    from arq.connections import RedisSettings

    from app.discovery.worker import WorkerSettings

    assert WorkerSettings.functions == [run_discovery_query]
    assert inspect.signature(run_discovery_query).parameters["allow_overrides"].default is False
    assert isinstance(WorkerSettings.redis_settings, RedisSettings)
    assert WorkerSettings.max_tries == 1
    assert WorkerSettings.keep_result == 0
    assert WorkerSettings.job_timeout == (
        get_settings().retrieval_attempt_timeout_seconds + 60
    )

    cron_jobs = WorkerSettings.cron_jobs
    assert [job.coroutine for job in cron_jobs] == [reap_stale_running_runs]
    reaper_cron = cron_jobs[0]
    minutes = reaper_cron.minute
    assert isinstance(minutes, set)
    assert sorted(minutes) == list(range(0, 60, 5))  # every 300 seconds
