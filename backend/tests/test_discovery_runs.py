"""Discovery-run REST API at the FastAPI app boundary.

Isolation posture: retrieval observations are immutable (INV-012) and their
runs/campaigns therefore cannot be fully cleaned up afterwards. Leftover rows
would break the shared test database's blanket campaign cleanup, so this
module points the app at a dedicated migrated database; every assertion is
scoped to freshly generated ids. No trigger is ever bypassed.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.discovery import router as discovery_router
from app.discovery import service as discovery_service
from app.main import create_app
from app.workspaces import DEFAULT_WORKSPACE_ID

API_TOKEN = "test-token"
DISCOVERY_DATABASE_NAME = "aptori_outreach_discovery_test"
DISCOVERY_DATABASE_URL = f"postgresql+psycopg://@/{DISCOVERY_DATABASE_NAME}"

HEX64 = re.compile(r"^[0-9a-f]{64}$")
CORRELATION = re.compile(r"^[0-9a-f]{16}$")


@pytest.fixture(scope="session")
def discovery_database_url() -> Iterator[str]:
    """Create and migrate a dedicated append-only database for this module."""
    from psycopg import connect, sql
    from alembic import command
    from alembic.config import Config

    with connect("postgresql://", autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (DISCOVERY_DATABASE_NAME,),
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DISCOVERY_DATABASE_NAME))
            )
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", DISCOVERY_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield DISCOVERY_DATABASE_URL


@pytest.fixture(autouse=True)
def clean_discovery_writes(discovery_database_url: str) -> Iterator[None]:
    """Clear only deletable rows; runs/observations stay by design."""
    yield
    engine = create_engine(discovery_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM audit_events"))
            connection.execute(text("DELETE FROM idempotency_events"))
    finally:
        engine.dispose()


@pytest.fixture()
def api(discovery_database_url: str) -> Iterator[TestClient]:
    app = create_app(database_url=discovery_database_url, api_token=API_TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        yield client


def write_headers(key: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


def active_campaign(api: TestClient) -> dict[str, Any]:
    created = api.post(
        "/campaigns", headers=write_headers(), json={"name": "Discovery API", "promotion_posture": "expertise_first"}
    ).json()
    assert isinstance(created, dict)
    api.patch(f"/campaigns/{created['id']}", headers=write_headers(), json={"status": "active"})
    return created


def start_run(api: TestClient, campaign_id: str, key: str | None = None) -> Any:
    return api.post(
        f"/campaigns/{campaign_id}/discovery-runs",
        headers=write_headers(key),
    )


class FakeEnqueue:
    """Synchronous stand-in for the arq queue port."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[str]]] = []
        self.fail_next = False

    def __call__(self, run_id: object, correlation_id: str, query_ids: list[str]) -> None:
        call: tuple[str, str, list[str]] = (str(run_id), correlation_id, list(query_ids))
        self.calls.append(call)
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("redis unavailable")


@pytest.fixture()
def fake_enqueue(monkeypatch: pytest.MonkeyPatch) -> FakeEnqueue:
    fake = FakeEnqueue()
    monkeypatch.setattr(discovery_router, "DEFAULT_ENQUEUE", fake)
    return fake


def run_rows(engine_url: str, query: str, params: dict[str, Any]) -> list[Any]:
    engine = create_engine(engine_url)
    try:
        with engine.connect() as connection:
            return list(connection.execute(text(query), params))
    finally:
        engine.dispose()


def insert_observation(engine_url: str, run_id: str, qid: str, status: str) -> None:
    from app.discovery.models import RetrievalObservation

    engine = create_engine(engine_url)
    try:
        with Session(engine) as session:
            session.add(
                RetrievalObservation(
                    discovery_run_id=uuid.UUID(run_id),
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    query_id=qid,
                    schema_version=1,
                    capability="discovery",
                    provider_variant="obscura-duckduckgo-lite@2026-08-21",
                    config_sha256="0" * 64,
                    observation_id=f"attempt-{qid}",
                    status=status,
                    evidence_directory=f"/evidence-runs/{run_id}/attempt-{qid}",
                    correlation_id="corr-api-test",
                )
            )
            session.commit()
    finally:
        engine.dispose()


def started_run(api: TestClient, fake_enqueue: FakeEnqueue) -> tuple[dict[str, Any], str]:
    campaign = active_campaign(api)
    response = start_run(api, campaign["id"])
    assert response.status_code == 201
    body = response.json()
    return body, campaign["id"]


def test_start_on_active_campaign_returns_queued_frozen_plan(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    campaign = active_campaign(api)

    response = start_run(api, campaign["id"])

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["campaign_id"] == campaign["id"]
    assert body["workspace_id"] == str(DEFAULT_WORKSPACE_ID)
    assert CORRELATION.match(body["correlation_id"])
    # Honest not-reported: nothing has run yet.
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["metrics"] is None

    plan = body["method_plan"]
    assert plan["source"] == "prototype-smoke"
    assert plan["provider_variant"].startswith("obscura-duckduckgo-lite")
    assert HEX64.match(plan["config_sha256"])
    assert HEX64.match(plan["document_sha256"])
    queries = plan["queries"]
    assert len(queries) == 10
    assert all(q["id"].startswith(f"q{i:02d}-") for i, q in enumerate(queries, start=1))
    assert all(isinstance(q["query"], str) and q["query"] for q in queries)
    assert all(isinstance(q.get("subreddits"), list) for q in queries)

    # Hashes are honest fingerprints of the exact frozen bytes on disk.
    from app.config import get_settings

    settings = get_settings()
    document_bytes = settings.discovery_query_document_path.read_bytes()
    config_bytes = settings.discovery_provider_config_path.read_bytes()
    assert plan["document_sha256"] == hashlib.sha256(document_bytes).hexdigest()
    assert plan["config_sha256"] == hashlib.sha256(config_bytes).hexdigest()

    # Exactly one enqueue carrying every query id.
    assert len(fake_enqueue.calls) == 1
    run_id, correlation_id, query_ids = fake_enqueue.calls[0]
    assert run_id == body["id"]
    assert correlation_id == body["correlation_id"]
    assert query_ids == [q["id"] for q in queries]

    rows = run_rows(
        discovery_database_url,
        "SELECT count(*) FROM discovery_runs WHERE campaign_id = :c",
        {"c": campaign["id"]},
    )
    assert rows[0][0] == 1


def test_same_key_replays_identical_body_and_reenqueues(
    api: TestClient, fake_enqueue: FakeEnqueue
) -> None:
    campaign = active_campaign(api)
    key = "replay-key-discovery"

    first = start_run(api, campaign["id"], key=key)
    second = start_run(api, campaign["id"], key=key)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.content == first.content  # byte-identical replay
    # Ruling 7: replay re-enqueues safely via deterministic job ids.
    assert len(fake_enqueue.calls) == 2
    assert fake_enqueue.calls[0] == fake_enqueue.calls[1]


@pytest.mark.parametrize("status", ["draft", "paused", "archived"])
def test_non_active_campaign_conflicts(
    api: TestClient, fake_enqueue: FakeEnqueue, status: str
) -> None:
    created = api.post(
        "/campaigns", headers=write_headers(), json={"name": f"Not {status}", "promotion_posture": "balanced"}
    ).json()
    if status != "draft":
        # Legal path: draft -> active -> paused|archived.
        api.patch(f"/campaigns/{created['id']}", headers=write_headers(), json={"status": "active"})
        if status != "active":
            api.patch(f"/campaigns/{created['id']}", headers=write_headers(), json={"status": status})

    response = start_run(api, created["id"])

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "campaign_not_active"
    assert status in detail["message"]


def test_unknown_campaign_is_not_found(api: TestClient, fake_enqueue: FakeEnqueue) -> None:
    response = start_run(api, str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "campaign_not_found"


def test_missing_idempotency_key_is_rejected(api: TestClient) -> None:
    campaign = active_campaign(api)

    response = api.post(f"/campaigns/{campaign['id']}/discovery-runs")

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_required"


def test_service_rejects_principal_without_workspace_access(
    discovery_database_url: str,
) -> None:
    from app.auth import Principal

    engine = create_engine(discovery_database_url)
    principal = Principal(actor="outsider", workspace_ids=frozenset())
    try:
        with Session(engine) as session:
            with pytest.raises(discovery_service.WorkspaceAccessDenied):
                discovery_service.start_discovery_run(
                    session,
                    principal,
                    DEFAULT_WORKSPACE_ID,
                    uuid.uuid4(),
                    key="outsider-key",
                    plan_loader=lambda: (_ for _ in ()).throw(AssertionError("not reached")),
                    enqueue=lambda *a: None,
                )
    finally:
        engine.dispose()


def test_foreign_workspace_run_is_invisible(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    foreign_workspace, foreign_run = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(discovery_database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
                {"id": str(foreign_workspace), "name": f"other-{uuid.uuid4().hex[:8]}"},
            )
            campaign_row = connection.execute(
                text(
                    "INSERT INTO campaigns (id, workspace_id, name, keywords,"
                    " subreddits, competitors, approved_claims, prohibited_claims,"
                    " promotion_posture, status)"
                    " VALUES (:id, :workspace, :name, '[]'::jsonb, '[]'::jsonb,"
                    " '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'balanced', 'active')"
                    " RETURNING id"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "workspace": str(foreign_workspace),
                    "name": f"foreign-{uuid.uuid4().hex[:8]}",
                },
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO discovery_runs (id, workspace_id, campaign_id,"
                    " status, method_plan, correlation_id)"
                    " VALUES (:id, :workspace, :campaign,"
                    " 'running', '{}'::jsonb, 'corr-foreign')"
                ),
                {
                    "id": str(foreign_run),
                    "workspace": str(foreign_workspace),
                    "campaign": str(campaign_row),
                },
            )
    finally:
        engine.dispose()

    assert api.get(f"/discovery-runs/{foreign_run}").status_code == 404
    observations = api.get(f"/discovery-runs/{foreign_run}/observations")
    assert observations.status_code == 404


def test_enqueue_failure_keeps_committed_run_and_retry_succeeds(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    campaign = active_campaign(api)
    key = "flaky-worker-key"
    fake_enqueue.fail_next = True

    failed = start_run(api, campaign["id"], key=key)

    assert failed.status_code == 503
    detail = failed.json()["detail"]
    assert detail["code"] == "worker_queue_unavailable"
    assert "same" in detail["message"].lower() and "key" in detail["message"].lower()

    # The run row exists committed despite the queue failure.
    rows = run_rows(
        discovery_database_url,
        "SELECT id FROM discovery_runs WHERE campaign_id = :c",
        {"c": campaign["id"]},
    )
    assert len(rows) == 1

    retried = start_run(api, campaign["id"], key=key)
    assert retried.status_code == 201
    body = retried.json()
    assert body["status"] == "queued"
    assert body["id"] == str(rows[0][0])
    # Retry re-enqueued deterministically for the same run.
    assert [call[0] for call in fake_enqueue.calls] == [str(rows[0][0])] * 2

    again = start_run(api, campaign["id"], key=key)
    assert again.status_code == 201
    assert again.content == retried.content


def test_get_run_contract_and_unknown_404(
    api: TestClient, fake_enqueue: FakeEnqueue
) -> None:
    body, _campaign_id = started_run(api, fake_enqueue)

    response = api.get(f"/discovery-runs/{body['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == body["id"]
    assert detail["status"] == "queued"
    assert detail["method_plan"] == body["method_plan"]
    assert detail["correlation_id"] == body["correlation_id"]
    assert detail["metrics"] is None
    assert set(detail) >= {
        "id", "campaign_id", "workspace_id", "status", "method_plan",
        "correlation_id", "metrics", "started_at", "completed_at",
        "created_at", "updated_at",
    }

    missing = api.get(f"/discovery-runs/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "discovery_run_not_found"


def test_observations_page_walks_creation_order_with_cursor(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    body, _campaign_id = started_run(api, fake_enqueue)
    run_id = body["id"]

    empty = api.get(f"/discovery-runs/{run_id}/observations")
    assert empty.status_code == 200
    assert empty.json() == {"items": [], "next_cursor": None}

    insert_observation(discovery_database_url, run_id, "q01-api-security-broad", "success")
    insert_observation(discovery_database_url, run_id, "q02-appsec-tools-broad", "blocked")

    page_one = api.get(f"/discovery-runs/{run_id}/observations", params={"limit": 1}).json()
    assert [item["query_id"] for item in page_one["items"]] == ["q01-api-security-broad"]
    assert page_one["items"][0]["status"] == "success"
    assert page_one["next_cursor"] is not None

    page_two = api.get(
        f"/discovery-runs/{run_id}/observations",
        params={"limit": 1, "cursor": page_one["next_cursor"]},
    ).json()
    assert [item["query_id"] for item in page_two["items"]] == ["q02-appsec-tools-broad"]
    assert page_two["items"][0]["status"] == "blocked"
    assert page_two["next_cursor"] is None

    item = page_one["items"][0]
    assert set(item) >= {
        "id", "query_id", "capability", "status", "failure_class", "failure_reason",
        "provider_variant", "config_sha256", "schema_version", "candidate_count",
        "candidates", "normalized_sha256", "elapsed_ms", "evidence_directory",
        "correlation_id", "started_at", "completed_at", "created_at",
    }
    assert item["failure_class"] is None


def test_api_never_recomputes_metrics_from_direct_rows(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    body, _campaign_id = started_run(api, fake_enqueue)
    insert_observation(discovery_database_url, body["id"], "q01-api-security-broad", "blocked")
    insert_observation(discovery_database_url, body["id"], "q02-appsec-tools-broad", "success")

    detail = api.get(f"/discovery-runs/{body['id']}").json()

    assert detail["status"] == "queued"
    assert detail["metrics"] is None


def _write_plan_files(
    tmp_path: Path, queries: list[dict[str, object]]
) -> tuple[Path, Path]:
    document_path = tmp_path / "queries.json"
    document_path.write_text(
        json.dumps({"schemaVersion": 1, "queries": queries}),
        encoding="utf-8",
    )
    config_path = tmp_path / "provider-config.json"
    config_path.write_text(
        json.dumps({"providerVariant": "obscura-duckduckgo-lite"}), encoding="utf-8"
    )
    return document_path, config_path


def test_load_frozen_plan_accepts_boring_unique_query_ids(tmp_path: Path) -> None:
    document_path, config_path = _write_plan_files(
        tmp_path,
        [
            {"id": "q01-api-security", "query": "API security"},
            {"id": "q02-appsec-tools", "query": "application security"},
        ],
    )

    plan = discovery_service.load_frozen_plan(document_path, config_path)

    assert [q.id for q in plan.queries] == ["q01-api-security", "q02-appsec-tools"]


def test_load_frozen_plan_rejects_hostile_query_id_charset(tmp_path: Path) -> None:
    document_path, config_path = _write_plan_files(
        tmp_path, [{"id": "../escape", "query": "path traversal"}]
    )

    with pytest.raises(discovery_service.RetrievalInputsInvalid, match="A-Za-z0-9_-"):
        discovery_service.load_frozen_plan(document_path, config_path)


def test_load_frozen_plan_rejects_oversized_query_ids(tmp_path: Path) -> None:
    document_path, config_path = _write_plan_files(
        tmp_path, [{"id": "x" * 65, "query": "too long"}]
    )

    with pytest.raises(discovery_service.RetrievalInputsInvalid, match="A-Za-z0-9_-"):
        discovery_service.load_frozen_plan(document_path, config_path)


def test_load_frozen_plan_rejects_duplicate_query_ids(tmp_path: Path) -> None:
    document_path, config_path = _write_plan_files(
        tmp_path,
        [
            {"id": "q-duplicate", "query": "first"},
            {"id": "q-duplicate", "query": "second"},
        ],
    )

    with pytest.raises(discovery_service.RetrievalInputsInvalid, match="more than once"):
        discovery_service.load_frozen_plan(document_path, config_path)


def test_discovery_run_created_audit_carries_correlation_id(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    body, campaign_id = started_run(api, fake_enqueue)

    events = run_rows(
        discovery_database_url,
        "SELECT action, correlation_id FROM audit_events WHERE target_id = :id",
        {"id": uuid.UUID(body["id"])},
    )
    created = [row for row in events if row.action == "discovery_run.created"]
    assert len(created) == 1
    assert created[0].correlation_id == body["correlation_id"]
    del campaign_id


def test_api_distinguishes_unpriced_from_zero(
    api: TestClient, fake_enqueue: FakeEnqueue, discovery_database_url: str
) -> None:
    """cost_status='unpriced' with cost_usd=null passes through untouched."""
    body, _campaign_id = started_run(api, fake_enqueue)
    rolled_up_metrics = (
        '{"counts": {"success": 1}, "total_elapsed_ms": 1250, '
        '"cost_usd": null, "cost_status": "unpriced", '
        '"usage": {"request_count": 14, "bytes_transferred": null}}'
    )
    update_engine = create_engine(discovery_database_url)
    try:
        with update_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE discovery_runs SET status = 'succeeded', "
                    "metrics = CAST(:m AS jsonb) WHERE id = :id"
                ),
                {"m": rolled_up_metrics, "id": uuid.UUID(body["id"])},
            )
    finally:
        update_engine.dispose()

    detail = api.get(f"/discovery-runs/{body['id']}")
    assert detail.status_code == 200
    metrics = detail.json()["metrics"]

    # Null means "no pricing exists"; it must never collapse into 0.
    assert "cost_usd" in metrics
    assert metrics["cost_usd"] is None
    assert metrics["cost_status"] == "unpriced"
    assert metrics["usage"]["request_count"] == 14
    assert metrics["usage"]["bytes_transferred"] is None
