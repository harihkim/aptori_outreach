"""Worker runner: one discovery query end-to-end against a stub CLI.

Immutability posture: retrieval_observations can never be deleted, so every
test seeds its own uuid-keyed campaign/run rows in a dedicated worker test
database and asserts by run id. No trigger is ever bypassed; the dedicated
database keeps those append-only rows away from suites that clean shared
tables.

Spawn configuration flows exclusively through settings (env vars + settings
cache reset); the production runner has no override channel.
"""

import asyncio
import inspect
import json
import shlex
import textwrap
import uuid
from collections.abc import AsyncIterator, Iterator
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
from app.conversations import service as conversation_service
from app.conversations.identity import thread_fetch_query_id
from app.conversations.models import (
    Conversation,
    ConversationVersion,
    ConversationVersionObservation,
)
from app.conversations.normalizer import NORMALIZER_VERSION, normalize_reddit_thread
from app.conversations.runner import run_thread_fetch
from app.discovery import events as progress_events
from app.discovery import queue as discovery_queue
from app.discovery.events import ProgressEvent
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.discovery.observations import STATUS_VALUES
from app.discovery.runner import (
    _evidence_failure_reason,
    _parse_iso,
    run_discovery_query,
)
from app.discovery.worker import reap_stale_running_runs
from app.evidence.models import EvidenceBundle
from app.evidence.store import EvidenceStore, EvidenceStoreError
from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.conftest import admin_database_url, configured_database_url

WORKER_DATABASE_NAME = "aptori_outreach_worker_test"
WORKER_DATABASE_URL = configured_database_url(WORKER_DATABASE_NAME)


@pytest.fixture(scope="session")
def worker_database_url() -> Iterator[str]:
    """Migrate a dedicated append-only database for discovery worker tests."""
    with connect(
        admin_database_url(WORKER_DATABASE_URL), autocommit=True
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (WORKER_DATABASE_NAME,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(WORKER_DATABASE_NAME)
                )
            )
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", WORKER_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield WORKER_DATABASE_URL


@pytest.fixture()
def worker_db(
    worker_database_url: str, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """Point cached settings at the worker database for the duration."""
    monkeypatch.setenv("APTORI_DATABASE_URL", worker_database_url)
    get_settings.cache_clear()
    yield worker_database_url
    get_settings.cache_clear()


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


DOCS_SERVING_TAIL = (
    'DOC="$DOCS/$ID.json"\n'
    "printf 'raw evidence\\n' > \"$ATTEMPT_DIR/raw-page.html\"\n"
    'sed -e "s|@@EVIDENCE@@|$OUT|g" -e "s|@@QID@@|$ID|g" '
    '"$DOC" > "$ATTEMPT_DIR/observation.json"\n'
    'cat "$ATTEMPT_DIR/observation.json"\n'
    "exit 0\n"
)


class StubHarness:
    """Stub CLI runtime wired through settings; install() activates it."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        *,
        sleep_seconds: int | None = None,
        tail: str | None = None,
        timeout_seconds: float = 10,
    ) -> None:
        self.monkeypatch = monkeypatch
        self.tmp_path = tmp_path
        self.docs_dir = tmp_path / "docs"
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_root = tmp_path / "evidence-runs"
        self.staging_root = tmp_path / "retrieval-staging"
        self.input_root = tmp_path / "input-scratch"
        self.cli_path = tmp_path / "retrieval-cli.js"
        self.config_path = tmp_path / "provider-config.json"
        self.config_path.write_text(json.dumps({"providerVariant": "stub"}))
        self.timeout_seconds = timeout_seconds
        if tail is None:
            tail = (
                f"sleep {sleep_seconds}\nexit 0\n"
                if sleep_seconds
                else DOCS_SERVING_TAIL
            )
        body = f'DOCS="{self.docs_dir}"\n' + tail
        self.node_bin = write_raw_stub(tmp_path, body)

    def use_tail(self, tail: str) -> None:
        """Swap in a custom stub tail and re-install the settings seam."""
        self.node_bin = write_raw_stub(
            self.tmp_path, f'DOCS="{self.docs_dir}"\n' + tail
        )
        self.install()

    def write_doc(self, qid: str, doc: dict[str, object]) -> None:
        (self.docs_dir / f"{qid}.json").write_text(json.dumps(doc))

    def install(self) -> None:
        mp = self.monkeypatch
        mp.setenv("APTORI_RETRIEVAL_NODE_BIN", str(self.node_bin))
        mp.setenv("APTORI_RETRIEVAL_CLI_PATH", str(self.cli_path))
        mp.setenv("APTORI_DISCOVERY_PROVIDER_CONFIG_PATH", str(self.config_path))
        mp.setenv("APTORI_THREAD_PROVIDER_CONFIG_PATH", str(self.config_path))
        mp.setenv("APTORI_RETRIEVAL_EVIDENCE_ROOT", str(self.evidence_root))
        mp.setenv("APTORI_RETRIEVAL_STAGING_ROOT", str(self.staging_root))
        mp.setenv("APTORI_RETRIEVAL_INPUT_SCRATCH_ROOT", str(self.input_root))
        mp.setenv("APTORI_RETRIEVAL_ATTEMPT_TIMEOUT_SECONDS", str(self.timeout_seconds))
        get_settings.cache_clear()


class RecordingEventBus:
    """Capture worker progress without requiring Redis."""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def publish(self, event: ProgressEvent) -> None:
        self.events.append(event)

    async def subscribe(
        self, workspace_id: uuid.UUID, run_id: uuid.UUID
    ) -> AsyncIterator[ProgressEvent | None]:
        del workspace_id, run_id
        if False:
            yield None


@pytest.fixture()
def harness(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[StubHarness]:
    """A default installed stub runtime for one test."""
    stub_harness = StubHarness(monkeypatch, tmp_path)
    stub_harness.install()
    yield stub_harness
    get_settings.cache_clear()


def fixture_doc(
    qid: str, status: str = "success", **overrides: object
) -> dict[str, object]:
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
        "network": {"requests": {"q-a": 14, "q-b": 7}.get(qid, 5)},
        "runtime": {"node": "20.18.0"},
        "evidenceDirectory": "@@EVIDENCE@@/attempt-@@QID@@",
        "rawArtifact": {
            "path": "@@EVIDENCE@@/attempt-@@QID@@/raw-page.html",
            "filename": "raw-page.html",
            "bytes": 0,
            "sha256": "0" * 64,
        },
    }
    doc.update(overrides)
    return doc


def seed_run(
    database_url: str, *, correlation_id: str, query_ids: list[str]
) -> uuid.UUID:
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
                    {
                        "id": qid,
                        "query": f"search {qid}",
                        "subreddits": ["cybersecurity"],
                    }
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


def invoke(
    run_id: uuid.UUID,
    qid: str,
    *,
    workspace_id: uuid.UUID = DEFAULT_WORKSPACE_ID,
    correlation_id: str = "corr-123",
) -> str:
    return asyncio.run(
        run_discovery_query(
            None,
            workspace_id=str(workspace_id),
            run_id=str(run_id),
            correlation_id=correlation_id,
            query_id=qid,
        )
    )


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


def load_bundles(database_url: str, bundle_ids: set[uuid.UUID]) -> list[EvidenceBundle]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            bundles = list(
                session.scalars(
                    select(EvidenceBundle).where(EvidenceBundle.id.in_(bundle_ids))
                )
            )
            for bundle in bundles:
                session.expunge(bundle)
            return bundles
    finally:
        engine.dispose()


def bundle_count(database_url: str) -> int:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            return len(list(session.scalars(select(EvidenceBundle.id))))
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


def test_worker_cannot_claim_run_from_foreign_workspace(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-foreign", query_ids=["q-a"])
    foreign_workspace = uuid.UUID("00000000-0000-0000-0000-000000000002")

    assert invoke(run_id, "q-a", workspace_id=foreign_workspace) == "run_missing"
    assert load_run(worker_db, run_id).status == "queued"
    assert load_rows(worker_db, run_id) == []


def test_success_and_no_results_complete_the_run(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    harness.write_doc("q-b", fixture_doc("q-b", "no_results"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a")
    final_status = invoke(run_id, "q-b")

    assert final_status == "succeeded"
    run = load_run(worker_db, run_id)
    assert run.status == "succeeded"
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.metrics is not None
    # Emitted shape must equal the pinned contract keys exactly (FINDING-2).
    from app.discovery.runner import RUN_METRICS_KEYS, RUN_USAGE_KEYS

    assert set(run.metrics) == RUN_METRICS_KEYS
    usage = run.metrics["usage"]
    assert isinstance(usage, dict)
    assert set(usage) == RUN_USAGE_KEYS
    assert run.metrics["counts"] == {"no_results": 1, "success": 1}
    # Measured retrieval usage only: sums of what the attempts reported.
    assert run.metrics["total_elapsed_ms"] == 1500
    assert run.metrics["cost_usd"] is None
    assert run.metrics["cost_status"] == "unpriced"
    assert run.metrics["usage"] == {
        "request_count": 21,  # 14 + 7, exactly as the fixtures measured
        "bytes_transferred": None,  # never measured: null, not zero
    }

    rows = load_rows(worker_db, run_id)
    success_row = row_by_query(rows, "q-a")
    no_results_row = row_by_query(rows, "q-b")
    assert success_row.status == "success"
    assert success_row.failure_class is None
    assert success_row.candidate_count == 3
    assert success_row.observation_id == "attempt-q-a"
    assert success_row.evidence_state == "bundle"
    assert success_row.evidence_bundle_id is not None
    assert success_row.evidence_directory is None
    assert success_row.raw_artifact is not None
    assert "path" not in success_row.raw_artifact
    assert no_results_row.evidence_state == "bundle"
    assert no_results_row.evidence_bundle_id == success_row.evidence_bundle_id
    assert success_row.evidence_bundle_id is not None
    bundles = load_bundles(worker_db, {success_row.evidence_bundle_id})
    assert len(bundles) == 1
    manifest = bundles[0].artifact_manifest
    assert set(manifest) == {"manifest_version", "artifacts"}
    assert manifest["manifest_version"] == "evidence-bundle/v1"
    assert manifest["artifacts"] == [success_row.raw_artifact]
    assert success_row.network == {"requests": 14}
    assert no_results_row.status == "no_results"
    assert no_results_row.failure_class is None

    # Python owns input staging; the CLI-owned evidence root never gains
    # python-written input files (ADR ownership split).
    staged_input = harness.input_root / str(run_id) / "input-q-a.json"
    assert staged_input.is_file()
    assert list(staged_input.parent.glob("input-q-b.json"))
    leaked_inputs = [path.name for path in harness.evidence_root.rglob("input-*.json")]
    assert leaked_inputs == []
    assert not (harness.staging_root / str(run_id)).exists()


def test_success_plus_blocked_is_partial(harness: StubHarness, worker_db: str) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    harness.write_doc("q-b", fixture_doc("q-b", "blocked"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a")
    final_status = invoke(run_id, "q-b")

    assert final_status == "partial"
    run = load_run(worker_db, run_id)
    assert run.status == "partial"
    blocked_row = row_by_query(load_rows(worker_db, run_id), "q-b")
    assert blocked_row.status == "blocked"
    assert blocked_row.failure_class is None


def test_blocked_and_rate_limited_fail_the_run(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "blocked"))
    harness.write_doc("q-b", fixture_doc("q-b", "rate_limited"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a")
    final_status = invoke(run_id, "q-b")

    assert final_status == "failed"
    run = load_run(worker_db, run_id)
    assert run.status == "failed"
    assert run.metrics is not None
    assert run.metrics["counts"] == {"blocked": 1, "rate_limited": 1}


def test_unknown_schema_version_persists_unclassified_failure(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    harness.write_doc("q-bad", fixture_doc("q-bad", "success", schemaVersion=99))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-bad"])

    invoke(run_id, "q-a")
    final_status = invoke(run_id, "q-bad")

    assert final_status == "partial"
    run = load_run(worker_db, run_id)
    assert run.status == "partial"

    bad_row = row_by_query(load_rows(worker_db, run_id), "q-bad")
    assert bad_row.status == "failed"
    assert bad_row.failure_class == "unknown_observation_schema"
    assert bad_row.observation_id == f"{run_id}:q-bad:unclassified"
    assert bad_row.evidence_state == "none"
    assert bad_row.evidence_bundle_id is None
    assert bad_row.evidence_directory is None


def test_replay_same_query_does_not_duplicate_observation(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    first_status = invoke(run_id, "q-a")
    # The completed run is terminal, so a redelivery observes 'already_done'.
    second_status = invoke(run_id, "q-a")

    assert first_status == "succeeded"
    assert second_status == "already_done"
    assert len(load_rows(worker_db, run_id)) == 1
    first_row = load_rows(worker_db, run_id)[0]
    assert first_row.evidence_bundle_id is not None
    assert len(load_bundles(worker_db, {first_row.evidence_bundle_id})) == 1
    started_events = [
        event
        for event in load_audit(worker_db, run_id)
        if event.action == "discovery_run.started"
    ]
    assert len(started_events) == 1


def test_correlation_id_flows_to_observations_and_audit(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    invoke(run_id, "q-a")

    rows = load_rows(worker_db, run_id)
    assert [row.correlation_id for row in rows] == ["corr-123"]
    events = load_audit(worker_db, run_id)
    actions = sorted(event.action for event in events)
    assert actions == ["discovery_run.completed", "discovery_run.started"]
    assert all(event.actor == "worker" for event in events)
    assert all(event.correlation_id == "corr-123" for event in events)
    completed = next(
        event for event in events if event.action == "discovery_run.completed"
    )
    assert completed.before == {"status": "running"}
    assert completed.after == {"status": "succeeded"}


def test_worker_publishes_live_progress_after_persisting_observation(
    harness: StubHarness,
    worker_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-events", query_ids=["q-a"])
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)

    assert invoke(run_id, "q-a", correlation_id="corr-events") == "succeeded"

    assert [item.type for item in bus.events] == [
        "discovery.started",
        "discovery.candidate_found",
        "retrieval.observed",
        "discovery.completed",
        # The fixture Candidate carries no externalSourceId, so nothing is
        # expected downstream and the run's completion closes the stage.
        "conversation.processing_completed",
    ]
    assert all(item.run_id == run_id for item in bus.events)
    assert all(item.workspace_id == DEFAULT_WORKSPACE_ID for item in bus.events)
    assert all(item.correlation_id == "corr-events" for item in bus.events)
    assert bus.events[1].payload["query_id"] == "q-a"
    assert bus.events[2].payload["status"] == "success"
    assert bus.events[3].payload["status"] == "succeeded"


def test_candidate_fetch_commits_bundle_before_normalization_and_emits_transition(
    harness: StubHarness,
    worker_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = {
        "rank": 1,
        "url": "https://www.reddit.com/r/example/comments/post/example/",
        "externalSourceId": "t3_post",
        "subreddit": "example",
        "title": "Example",
        "snippet": "Body",
        "displayedUrl": None,
    }
    candidate_url = candidate["url"]
    assert isinstance(candidate_url, str)
    discovery_doc = fixture_doc(
        "q-a", "success", candidateCount=1, candidates=[candidate]
    )
    harness.write_doc("q-a", discovery_doc)

    async def fake_enqueue(*args: object, **kwargs: object) -> list[str]:
        del args, kwargs
        return ["thread-job"]

    monkeypatch.setattr(
        "app.discovery.queue.enqueue_thread_fetch_candidates", fake_enqueue
    )
    run_id = seed_run(worker_db, correlation_id="corr-thread", query_ids=["q-a"])
    assert invoke(run_id, "q-a", correlation_id="corr-thread") == "succeeded"

    raw_payload = [
        {
            "data": {
                "children": [
                    {
                        "kind": "t3",
                        "data": {
                            "id": "post",
                            "name": "t3_post",
                            "title": "Example",
                            "author": "op",
                            "score": 5,
                            "upvote_ratio": 0.9,
                            "subreddit_name_prefixed": "r/example",
                            "num_comments": 1,
                            "created_utc": 1_700_000_000,
                            "selftext": "Body",
                            "permalink": "/r/example/comments/post/example/",
                            "is_self": True,
                            "locked": False,
                        },
                    }
                ]
            }
        },
        {
            "data": {
                "children": [
                    {
                        "kind": "t1",
                        "data": {
                            "id": "comment",
                            "name": "t1_comment",
                            "author": "person",
                            "score": 1,
                            "depth": 0,
                            "parent_id": "t3_post",
                            "created_utc": 1_700_000_001,
                            "body": "Reply",
                            "replies": "",
                        },
                    }
                ]
            }
        },
    ]
    projected = normalize_reddit_thread(raw_payload)
    query_id = thread_fetch_query_id("t3_post")
    thread_doc: dict[str, object] = {
        "schemaVersion": 1,
        "observationId": f"attempt-{query_id}",
        "capability": "thread_fetch",
        "providerVariant": "obscura-reddit-thread-test",
        "configSha256": "b" * 64,
        "startedAt": "2026-09-01T10:00:00Z",
        "completedAt": "2026-09-01T10:00:01Z",
        "elapsedMs": 1000,
        "status": "success",
        "failureReason": None,
        "sourceUrl": candidate_url,
        "finalUrl": candidate_url,
        "externalSourceId": "t3_post",
        "normalizedSha256": projected.normalized_sha256,
        "normalizedContentSha256": projected.normalized_content_sha256,
        "network": {"requests": 2},
        "runtime": {"node": "20.18.0"},
        "evidenceDirectory": "@@EVIDENCE@@/attempt-@@QID@@",
        "rawArtifact": {
            "path": "@@EVIDENCE@@/attempt-@@QID@@/raw-thread-response.json",
            "filename": "raw-thread-response.json",
            "bytes": 1,
            "sha256": "0" * 64,
        },
    }
    harness.write_doc(query_id, thread_doc)
    raw_json = json.dumps(raw_payload, separators=(",", ":"))
    harness.use_tail(
        'DOC="$DOCS/$ID.json"\n'
        f"printf '%s' {shlex.quote(raw_json)} > \"$ATTEMPT_DIR/raw-thread-response.json\"\n"
        'sed -e "s|@@EVIDENCE@@|$OUT|g" -e "s|@@QID@@|$ID|g" '
        '"$DOC" > "$ATTEMPT_DIR/observation.json"\n'
        'cat "$ATTEMPT_DIR/observation.json"\n'
        "exit 0\n"
    )
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)
    original_normalize = conversation_service.normalize_observation
    checked = False

    def assert_committed_then_normalize(
        session: Session,
        store: EvidenceStore,
        workspace_id: uuid.UUID,
        observation_id: uuid.UUID,
        *,
        normalizer_version: str = NORMALIZER_VERSION,
    ) -> conversation_service.NormalizationRecord:
        nonlocal checked
        engine = create_engine(worker_db)
        try:
            with Session(engine) as independent:
                persisted = independent.scalar(
                    select(RetrievalObservation).where(
                        RetrievalObservation.discovery_run_id == run_id,
                        RetrievalObservation.capability == "thread_fetch",
                    )
                )
                assert persisted is not None
                assert persisted.evidence_state == "bundle"
                assert persisted.evidence_bundle_id is not None
                assert (
                    independent.get(EvidenceBundle, persisted.evidence_bundle_id)
                    is not None
                )
                checked = True
        finally:
            engine.dispose()
        return original_normalize(
            session,
            store,
            workspace_id,
            observation_id,
            normalizer_version=normalizer_version,
        )

    monkeypatch.setattr(
        conversation_service, "normalize_observation", assert_committed_then_normalize
    )
    result = asyncio.run(
        run_thread_fetch(
            None,
            workspace_id=str(DEFAULT_WORKSPACE_ID),
            run_id=str(run_id),
            correlation_id="corr-thread",
            external_source_id="t3_post",
            url=candidate_url,
        )
    )

    assert result == "normalized"
    assert checked
    rows = load_rows(worker_db, run_id)
    assert [row.capability for row in rows] == ["discovery", "thread_fetch"]
    assert rows[1].status == "success"
    assert rows[1].evidence_state == "bundle"
    assert [event.type for event in bus.events] == [
        "retrieval.observed",
        "conversation.normalized",
        "conversation.processing_completed",
    ]
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.canonical_external_discussion_id == "t3_post"
                )
            )
            assert conversation is not None
            version = session.scalar(
                select(ConversationVersion).where(
                    ConversationVersion.conversation_id == conversation.id
                )
            )
            assert version is not None
            assert version.source_tree_exhausted is True
            provenance = session.scalar(
                select(ConversationVersionObservation).where(
                    ConversationVersionObservation.conversation_version_id == version.id
                )
            )
            assert provenance is not None
    finally:
        engine.dispose()

    assert (
        asyncio.run(
            run_thread_fetch(
                None,
                workspace_id=str(uuid.uuid4()),
                run_id=str(run_id),
                correlation_id="corr-thread",
                external_source_id="t3_post",
                url=candidate_url,
            )
        )
        == "run_missing"
    )


def test_timeout_without_disk_evidence_classifies_transport_timeout(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = StubHarness(monkeypatch, tmp_path, sleep_seconds=30, timeout_seconds=5)
    harness.install()
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-slow"])

    final_status = invoke(run_id, "q-slow")

    assert final_status == "failed"
    run = load_run(worker_db, run_id)
    assert run.status == "failed"
    slow_row = row_by_query(load_rows(worker_db, run_id), "q-slow")
    assert slow_row.status == "failed"
    assert slow_row.failure_class == "transport_timeout"


def test_timeout_with_written_evidence_recovers_completed_observation(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """P0 recovery: SIGKILL after the evidence was written still completes."""
    harness = StubHarness(monkeypatch, tmp_path, timeout_seconds=5)
    harness.use_tail(
        'DOC="$DOCS/$ID.json"\n'
        "printf 'raw evidence\\n' > \"$ATTEMPT_DIR/raw-page.html\"\n"
        'sed -e "s|@@EVIDENCE@@|$OUT|g" -e "s|@@QID@@|$ID|g" '
        '"$DOC" > "$ATTEMPT_DIR/observation.json"\n'
        "sleep 30\n"
        "exit 0\n"
    )
    harness.write_doc("q-rec", fixture_doc("q-rec", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-rec"])

    final_status = invoke(run_id, "q-rec")

    # The killed attempt resolved through its authoritative disk artifact.
    assert final_status == "succeeded"
    recovered_row = row_by_query(load_rows(worker_db, run_id), "q-rec")
    assert recovered_row.status == "success"
    assert recovered_row.failure_class is None
    assert recovered_row.observation_id == "attempt-q-rec"
    run = load_run(worker_db, run_id)
    assert run.status == "succeeded"
    assert not [
        event
        for event in load_audit(worker_db, run_id)
        if event.action == "discovery_run.reaped"
    ]


def test_wrapper_error_classified_from_plain_exit_one(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = StubHarness(
        monkeypatch, tmp_path, tail='echo "boom: wrapper crashed" >&2\nexit 1\n'
    )
    harness.install()
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    final_status = invoke(run_id, "q-x")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "wrapper_error"


def test_transport_error_classified_from_other_nonzero_exit(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = StubHarness(
        monkeypatch, tmp_path, tail='echo "segfault-ish" >&2\nexit 2\n'
    )
    harness.install()
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    invoke(run_id, "q-x")

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.failure_class == "transport_error"


def test_runtime_verification_marker_is_classified(
    worker_db: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    harness = StubHarness(
        monkeypatch,
        tmp_path,
        tail='echo "Error: verifyRuntime failed: Node version too old" >&2\nexit 1\n',
    )
    harness.install()
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    invoke(run_id, "q-x")

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.failure_class == "runtime_verification_failed"


def test_oversized_document_field_is_contract_violation(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success", observationId="x" * 300))
    harness.write_doc("q-b", fixture_doc("q-b", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    invoke(run_id, "q-a")
    final_status = invoke(run_id, "q-b")

    assert final_status == "partial"
    bad_row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert bad_row.status == "failed"
    assert bad_row.failure_class == "contract_violation"
    assert bad_row.observation_id == f"{run_id}:q-a:unclassified"


def test_unknown_observation_status_persists_classification(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "kind_of_fine"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    final_status = invoke(run_id, "q-a")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert row.status == "failed"
    assert row.failure_class == "unknown_observation_status"


def test_non_discovery_capability_is_contract_violation(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success", capability="thread_fetch"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a"])

    final_status = invoke(run_id, "q-a")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-a")
    assert row.failure_class == "contract_violation"
    assert "capability" in (row.failure_reason or "")


def test_unreadable_disk_evidence_beats_stdout_projection(
    harness: StubHarness, worker_db: str
) -> None:
    """Garbage disk document plus pointer-bearing stdout must fail honestly."""
    harness.use_tail(
        'printf "garbage not json" > "$ATTEMPT_DIR/observation.json"\n'
        'printf \'{"status":"success","observationId":"attempt-%s",'
        '"evidenceDirectory":"%s"}\' "$ID" "$ATTEMPT_DIR"\n'
        "exit 0\n"
    )
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    final_status = invoke(run_id, "q-x")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "evidence_unreadable"


def test_stdout_without_pointer_is_never_trusted_as_evidence(
    harness: StubHarness, worker_db: str
) -> None:
    """P0: stdout may locate evidence but can never BE the observation."""
    projection = {
        "schemaVersion": 1,
        "observationId": "attempt-q-x",
        "capability": "discovery",
        "providerVariant": "stub",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00Z",
        "completedAt": "2026-08-23T00:00:01Z",
        "status": "success",
        # Deliberately NO evidenceDirectory: nothing on disk to trust.
    }
    harness.use_tail(f"printf '%s' '{json.dumps(projection)}'\nexit 0\n")
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    final_status = invoke(run_id, "q-x")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "evidence_unlocated"
    assert "evidenceDirectory" in (row.failure_reason or "")
    assert row.observation_id == f"{run_id}:q-x:unclassified"


def test_stdout_projection_never_feeds_the_full_parser(
    harness: StubHarness, worker_db: str
) -> None:
    """Even a schema-breaking stdout doc stays unlocated, never parsed."""
    hostile_projection = {
        "schemaVersion": 99,  # would raise unknown_observation_schema if parsed
        "status": "kind_of_fine",  # would raise unknown_observation_status if parsed
        "observationId": "attempt-q-x",
    }
    harness.use_tail(f"printf '%s' '{json.dumps(hostile_projection)}'\nexit 0\n")
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    invoke(run_id, "q-x")

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.failure_class == "evidence_unlocated"


@pytest.mark.parametrize("native_status", STATUS_VALUES)
def test_every_native_status_round_trips_end_to_end(
    harness: StubHarness, worker_db: str, native_status: str
) -> None:
    qid = f"st-{native_status}"
    harness.write_doc(qid, fixture_doc(qid, native_status))
    run_id = seed_run(worker_db, correlation_id="corr-e2e", query_ids=[qid])

    final_status = invoke(run_id, qid, correlation_id="corr-e2e")

    row = row_by_query(load_rows(worker_db, run_id), qid)
    assert row.status == native_status
    assert row.failure_class is None
    assert row.correlation_id == "corr-e2e"

    # Single-query rollup ruling per status usability.
    if native_status in ("success", "no_results"):
        expected_rollup = "succeeded"
    elif native_status == "incomplete":
        # Usable evidence, but nothing was fully lost-or-found: partial.
        expected_rollup = "partial"
    else:
        expected_rollup = "failed"
    assert final_status == expected_rollup
    run = load_run(worker_db, run_id)
    assert run.status == expected_rollup


def test_all_twelve_statuses_roll_up_to_partial_with_usage_sums(
    harness: StubHarness, worker_db: str
) -> None:
    qids: list[str] = []
    total_requests = 0
    total_elapsed = 0
    for index, native_status in enumerate(STATUS_VALUES, start=1):
        qid = f"q{index:02d}"
        requests = index * 3
        elapsed = index * 100
        total_requests += requests
        total_elapsed += elapsed
        harness.write_doc(
            qid,
            fixture_doc(
                qid, native_status, network={"requests": requests}, elapsedMs=elapsed
            ),
        )
        qids.append(qid)

    run_id = seed_run(worker_db, correlation_id="corr-all12", query_ids=qids)
    for qid in qids[:-1]:
        invoke(run_id, qid)
    final_status = invoke(run_id, qids[-1])

    assert final_status == "partial"  # usable and unusable outcomes both present
    run = load_run(worker_db, run_id)
    assert run.metrics is not None
    counts = run.metrics["counts"]
    assert isinstance(counts, dict)
    assert sorted(counts) == sorted(STATUS_VALUES)
    assert all(count == 1 for count in counts.values())
    assert run.metrics["total_elapsed_ms"] == total_elapsed
    assert run.metrics["cost_status"] == "unpriced"
    assert run.metrics["cost_usd"] is None
    usage = run.metrics["usage"]
    assert isinstance(usage, dict)
    assert usage["request_count"] == total_requests
    assert usage["bytes_transferred"] is None

    rows = load_rows(worker_db, run_id)
    assert {row.status for row in rows} == set(STATUS_VALUES)
    assert all(row.failure_class is None for row in rows)


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
    reaped_events = [
        event for event in events if event.action == "discovery_run.reaped"
    ]
    assert len(reaped_events) == 1
    assert reaped_events[0].correlation_id == "corr-reap"
    assert reaped_events[0].before == {"status": "running"}
    assert reaped_events[0].after == {"status": "failed"}


def test_reaper_leaves_fresh_queued_and_terminal_runs_alone(worker_db: str) -> None:
    fresh_running = seed_run(
        worker_db, correlation_id="corr-fresh-r", query_ids=["q-a"]
    )
    queued = seed_run(worker_db, correlation_id="corr-fresh-q", query_ids=["q-b"])
    terminal = seed_run(worker_db, correlation_id="corr-fresh-t", query_ids=["q-c"])
    stale_cutoff = datetime.now(UTC) - timedelta(hours=2)
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            running = session.get(DiscoveryRun, fresh_running)
            assert running is not None
            running.status = "running"
            running.started_at = datetime.now(UTC)
            terminal_run = session.get(DiscoveryRun, terminal)
            assert terminal_run is not None
            terminal_run.status = "cancelled"
            terminal_run.started_at = stale_cutoff
            queued_run = session.get(DiscoveryRun, queued)
            assert queued_run is not None
            queued_run.created_at = stale_cutoff  # old but never claimed
            session.commit()
    finally:
        engine.dispose()

    asyncio.run(reap_stale_running_runs(None))

    assert load_run(worker_db, fresh_running).status == "running"
    assert load_run(worker_db, queued).status == "queued"
    assert load_run(worker_db, terminal).status == "cancelled"
    for run_id in (fresh_running, queued, terminal):
        assert not [
            event
            for event in load_audit(worker_db, run_id)
            if event.action == "discovery_run.reaped"
        ]


def test_invalid_query_id_charset_is_contract_violation(
    harness: StubHarness, worker_db: str
) -> None:
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    harness.write_doc("q-b", fixture_doc("q-b", "success"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    first = invoke(run_id, "q-a")
    invoke(run_id, "../escape/id")
    final_status = invoke(run_id, "q-b")

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
    metrics_counts = run.metrics["counts"]
    assert isinstance(metrics_counts, dict)
    assert set(metrics_counts) == {"success"}  # the hostile row does not count
    # The hostile id never reached either filesystem root.
    assert not list(harness.evidence_root.rglob("*escape*"))
    assert not list(harness.input_root.rglob("*escape*"))


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
    harness: StubHarness, worker_db: str
) -> None:
    """A redelivery while other queries are pending must not rerun the CLI."""
    counter = harness.tmp_path / "spawns.log"
    spawn_counting_tail = f'echo x >> "{counter}"\n' + DOCS_SERVING_TAIL
    harness.use_tail(spawn_counting_tail)
    harness.write_doc("q-a", fixture_doc("q-a", "success"))
    harness.write_doc("q-b", fixture_doc("q-b", "blocked"))
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-a", "q-b"])

    first = invoke(run_id, "q-a")
    replayed = invoke(run_id, "q-a")

    assert first == "running"
    assert replayed == "running"
    assert counter.read_text().count("x") == 1
    assert len(load_rows(worker_db, run_id)) == 1


def test_exit_zero_without_any_evidence_is_unlocated_not_transport(
    harness: StubHarness, worker_db: str
) -> None:
    """Exit 0 without disk evidence or a pointer is an honesty gap."""
    harness.use_tail('printf "not json at all"\nexit 0\n')
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])
    before_bundle_count = bundle_count(worker_db)

    final_status = invoke(run_id, "q-x")

    assert final_status == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "evidence_unlocated"
    assert row.evidence_state == "none"
    assert row.evidence_bundle_id is None
    assert row.evidence_directory is None
    assert bundle_count(worker_db) == before_bundle_count
    assert "observation.json" in (row.failure_reason or "")


def test_genuine_transport_failure_stays_transport_error(
    harness: StubHarness, worker_db: str
) -> None:
    """A nonzero exit still classifies as transport_error, not unlocated."""
    harness.use_tail('printf "not json at all"\nexit 7\n')
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    invoke(run_id, "q-x")

    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "transport_error"


def test_cross_run_evidence_pointer_is_rejected_without_a_bundle(
    harness: StubHarness, worker_db: str
) -> None:
    """A valid document may not ingest an artifact from another run."""
    harness.write_doc("q-x", fixture_doc("q-x", "success"))
    harness.use_tail(
        'SIBLING="$OUT/../sibling-run/attempt-q-x"\n'
        'mkdir -p "$SIBLING"\n'
        'printf "raw evidence\\n" > "$SIBLING/raw-page.html"\n'
        'sed -e "s|@@EVIDENCE@@|$OUT/../sibling-run|g" '
        '-e "s|@@QID@@|$ID|g" "$DOCS/$ID.json" > '
        '"$SIBLING/observation.json"\n'
        'printf "{\\"evidenceDirectory\\":\\"%s\\"}" "$SIBLING"\n'
        "exit 0\n"
    )
    run_id = seed_run(worker_db, correlation_id="corr-123", query_ids=["q-x"])

    assert invoke(run_id, "q-x") == "failed"
    row = row_by_query(load_rows(worker_db, run_id), "q-x")
    assert row.status == "failed"
    assert row.failure_class == "evidence_unreadable"
    assert row.evidence_state == "none"
    assert row.evidence_bundle_id is None
    assert row.evidence_directory is None


def test_storage_failure_reason_does_not_include_exception_paths() -> None:
    error = EvidenceStoreError("/tmp/staging/run-123/raw-page.html")
    reason = _evidence_failure_reason(error)
    assert reason == "raw evidence could not be finalized (EvidenceStoreError)"
    assert "/tmp/staging" not in reason


def test_classification_outputs_stay_within_failure_class_vocabulary() -> None:
    """Audit: every classifier path emits NULL or a canonical class only."""
    from app.discovery.cli import CliResult
    from app.discovery.models import FAILURE_CLASSES
    from app.discovery.runner import _classify_result

    valid = fixture_doc("q-x", "success")
    bad_schema = fixture_doc("q-x", "success", schemaVersion=99)
    bad_status = fixture_doc("q-x", "kind_of_fine")
    oversized = fixture_doc("q-x", "success", observationId="x" * 300)
    wrong_capability = fixture_doc("q-x", "success", capability="thread_fetch")

    cases: list[tuple[CliResult, str | None]] = [
        (
            CliResult(exit_code=-1, stderr_tail="", timed_out=True),
            "transport_timeout",
        ),
        (CliResult(exit_code=0, stderr_tail="", timed_out=False), "evidence_unlocated"),
        (
            CliResult(exit_code=2, stderr_tail="boom", timed_out=False),
            "transport_error",
        ),
        (
            CliResult(exit_code=1, stderr_tail="plain crash", timed_out=False),
            "wrapper_error",
        ),
        (
            CliResult(exit_code=1, stderr_tail="verifyRuntime failed", timed_out=False),
            "runtime_verification_failed",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk_unreadable",
            ),
            "evidence_unreadable",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="no_evidence_pointer",
            ),
            "evidence_unlocated",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk",
                observation_doc=bad_schema,
            ),
            "unknown_observation_schema",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk",
                observation_doc=bad_status,
            ),
            "unknown_observation_status",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk",
                observation_doc=oversized,
            ),
            "contract_violation",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk",
                observation_doc=wrong_capability,
            ),
            "contract_violation",
        ),
        (
            CliResult(
                exit_code=0,
                stderr_tail="",
                timed_out=False,
                evidence_source="disk",
                observation_doc=valid,
            ),
            None,
        ),
    ]

    for result, expected_class in cases:
        outcome = _classify_result(result, Path("/tmp/evidence-out"), 10.0)
        assert outcome.failure_class == expected_class
        assert outcome.failure_class is None or outcome.failure_class in FAILURE_CLASSES


def test_worker_settings_registers_the_plain_runner() -> None:
    """The worker runs exactly the deployed configuration: no override channel."""
    from arq.connections import RedisSettings

    from app.conversations.runner import run_thread_fetch
    from app.discovery.worker import WorkerSettings

    assert WorkerSettings.functions == [run_discovery_query, run_thread_fetch]
    parameters = inspect.signature(run_discovery_query).parameters
    assert list(parameters) == [
        "ctx",
        "workspace_id",
        "run_id",
        "correlation_id",
        "query_id",
    ]
    assert "overrides" not in parameters
    assert "allow_overrides" not in parameters
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


def test_refused_enqueue_persists_failed_fetch_rows_and_closes_processing(
    harness: StubHarness,
    worker_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Candidate the queue refuses must not keep processing open forever."""
    # Conversations are Workspace-scoped identities shared across runs, so
    # this Candidate must not collide with one another test normalized.
    external_id = f"t3_{uuid.uuid4().hex[:10]}"
    candidate = {
        "rank": 1,
        "url": f"https://www.reddit.com/r/example/comments/{external_id[3:]}/x/",
        "externalSourceId": external_id,
        "title": "Example",
    }
    harness.write_doc(
        "q-a", fixture_doc("q-a", "success", candidateCount=1, candidates=[candidate])
    )

    async def refuse(*args: object, **kwargs: object) -> list[str]:
        del args, kwargs
        raise discovery_queue.ThreadFetchQueueError([external_id])

    monkeypatch.setattr("app.discovery.queue.enqueue_thread_fetch_candidates", refuse)
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)
    run_id = seed_run(worker_db, correlation_id="corr-refused", query_ids=["q-a"])

    assert invoke(run_id, "q-a", correlation_id="corr-refused") == "succeeded"

    rows = load_rows(worker_db, run_id)
    assert [row.capability for row in rows] == ["discovery", "thread_fetch"]
    refused = rows[1]
    assert refused.status == "failed"
    assert refused.failure_class == "transport_error"
    assert refused.evidence_state == "none"
    assert refused.external_source_id == external_id
    assert refused.source_url == candidate["url"]
    assert refused.query_id == thread_fetch_query_id(external_id)
    assert [item.type for item in bus.events] == [
        "discovery.started",
        "job.failed",
        "discovery.candidate_found",
        "retrieval.observed",
        "discovery.completed",
        "conversation.processing_completed",
    ]
    assert bus.events[-1].payload == {
        "expected_count": 1,
        "fetched_count": 1,
        "normalized_count": 0,
    }

    # Replaying the settled query is a no-op and never duplicates the row.
    assert invoke(run_id, "q-a", correlation_id="corr-refused") == "already_done"
    assert len(load_rows(worker_db, run_id)) == 2


def test_non_http_candidate_urls_are_neither_enqueued_nor_expected(
    harness: StubHarness,
    worker_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        {
            "rank": 1,
            "url": "reddit.com/r/example/comments/a/",
            "externalSourceId": "t3_a",
        },
        {"rank": 2, "url": "ftp://example.test/b", "externalSourceId": "t3_b"},
    ]
    harness.write_doc(
        "q-a", fixture_doc("q-a", "success", candidateCount=2, candidates=candidates)
    )
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)
    run_id = seed_run(worker_db, correlation_id="corr-nonhttp", query_ids=["q-a"])

    # No Redis is configured for tests: reaching the pool would raise, so the
    # early return on an empty enqueue set is itself the assertion.
    assert invoke(run_id, "q-a", correlation_id="corr-nonhttp") == "succeeded"

    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            transitions = conversation_service.list_run_transitions(
                session, DEFAULT_WORKSPACE_ID, run_id
            )
    finally:
        engine.dispose()
    assert transitions.expected_count == 0
    assert transitions.processing_complete is True
    assert bus.events[-1].type == "conversation.processing_completed"
