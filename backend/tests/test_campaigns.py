"""Campaign REST API at the FastAPI app boundary."""

import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.auth import Principal
from app.campaigns import service as campaigns_service
from app.main import create_app
from app.workspaces import DEFAULT_WORKSPACE_ID

API_TOKEN = "test-token"


def write_headers(key: str | None = None) -> dict[str, str]:
    """Authenticated write headers with a per-call idempotency key."""
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Idempotency-Key": key or str(uuid.uuid4()),
    }


@pytest.fixture()
def client(migrated_test_database: str) -> Iterator[TestClient]:
    app = create_app(database_url=migrated_test_database, api_token=API_TOKEN)
    # Default headers authenticate every write the suite issues.
    with TestClient(
        app, headers={"Authorization": f"Bearer {API_TOKEN}"}
    ) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_campaign_rows(migrated_test_database: str) -> Iterator[None]:
    yield
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(text("DELETE FROM audit_events"))
        connection.execute(text("DELETE FROM idempotency_events"))
        connection.execute(text("DELETE FROM campaigns"))
        # Tests may plant foreign workspaces to prove scoping, and one test
        # removes the seeded default to prove fail-closed behavior; restore
        # the seed so suite order never matters.
        connection.execute(
            text("DELETE FROM workspaces WHERE id <> :default"),
            {"default": str(DEFAULT_WORKSPACE_ID)},
        )
        connection.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES (:id, 'aptori')"
                " ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(DEFAULT_WORKSPACE_ID)},
        )


def create_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "API security listening",
        "product_context": "Aptori finds broken authorization in APIs",
        "icp": "Security engineers at API-first companies",
        "keywords": ["API security", "pentest", "CIEM"],
        "subreddits": ["cybersecurity"],
        "competitors": ["Burp Suite"],
        "approved_claims": ["Aptori runs in CI"],
        "prohibited_claims": ["100% vulnerability coverage"],
        "promotion_posture": "expertise_first",
    }
    payload.update(overrides)
    return payload


def test_create_campaign_returns_draft_in_default_workspace(client: TestClient) -> None:
    response = client.post("/campaigns", headers=write_headers(), json=create_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "API security listening"
    assert body["status"] == "draft"
    assert body["workspace_id"] == str(DEFAULT_WORKSPACE_ID)
    assert body["keywords"] == ["API security", "pentest", "CIEM"]
    assert body["promotion_posture"] == "expertise_first"
    assert body["archived_at"] is None
    uuid.UUID(body["id"])
    assert body["created_at"]
    assert body["updated_at"]


def test_create_validation_rejects_blank_names(client: TestClient) -> None:
    response = client.post(
        "/campaigns", headers=write_headers(), json=create_payload(name="   ")
    )

    assert response.status_code == 422


def test_create_validation_rejects_unknown_posture(client: TestClient) -> None:
    response = client.post(
        "/campaigns",
        headers=write_headers(),
        json=create_payload(promotion_posture="aggressive"),
    )

    assert response.status_code == 422


def test_create_contract_is_closed_to_unknown_fields(client: TestClient) -> None:
    response = client.post(
        "/campaigns", headers=write_headers(), json=create_payload(surprise="value")
    )

    assert response.status_code == 422


def test_create_normalizes_tag_lists(client: TestClient) -> None:
    response = client.post(
        "/campaigns",
        headers=write_headers(),
        json=create_payload(
            keywords=["API security", " API security ", "", "pentest"],
        ),
    )

    assert response.status_code == 201
    # Blank items drop, whitespace strips, duplicates collapse in order.
    assert response.json()["keywords"] == ["API security", "pentest"]


def created_campaign(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(
        "/campaigns", headers=write_headers(), json=create_payload(**overrides)
    )
    assert response.status_code == 201
    body: dict[str, Any] = response.json()
    return body


def audit_events(migrated_test_database: str, campaign_id: str) -> list[Any]:
    with create_engine(migrated_test_database).connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT action, before, after FROM audit_events"
                    " WHERE target_type = 'campaign' AND target_id = :id"
                    " ORDER BY occurred_at, id"
                ),
                {"id": campaign_id},
            )
        )


def test_get_campaign_returns_the_created_contract(client: TestClient) -> None:
    created = created_campaign(client)

    response = client.get(f"/campaigns/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_get_unknown_campaign_returns_stable_404(client: TestClient) -> None:
    response = client.get(f"/campaigns/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "campaign_not_found"


def test_list_campaigns_orders_newest_first_when_timestamps_tie(
    client: TestClient, migrated_test_database: str
) -> None:
    created_campaign(client, name="first campaign")
    created_campaign(client, name="second campaign")
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text("UPDATE campaigns SET created_at = '2026-08-23T00:00:00Z'")
        )

    response = client.get("/campaigns")

    assert response.status_code == 200
    assert [campaign["name"] for campaign in response.json()["items"]] == [
        "second campaign",
        "first campaign",
    ]
    assert response.json()["next_cursor"] is None


def test_list_campaigns_pages_without_duplicates(client: TestClient) -> None:
    first = created_campaign(client, name="first campaign")
    second = created_campaign(client, name="second campaign")
    third = created_campaign(client, name="third campaign")

    newest = client.get("/campaigns", params={"limit": 2})
    older = client.get(
        "/campaigns",
        params={"limit": 2, "cursor": newest.json()["next_cursor"]},
    )

    assert [item["id"] for item in newest.json()["items"]] == [
        third["id"],
        second["id"],
    ]
    assert [item["id"] for item in older.json()["items"]] == [first["id"]]
    assert older.json()["next_cursor"] is None


def test_list_campaigns_rejects_an_invalid_cursor(client: TestClient) -> None:
    response = client.get("/campaigns", params={"cursor": "not-a-cursor"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "page_cursor_invalid"


def test_foreign_workspace_campaigns_are_invisible(
    client: TestClient, migrated_test_database: str
) -> None:
    foreign_workspace, foreign_campaign = uuid.uuid4(), uuid.uuid4()
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES (:id, 'other')"),
            {"id": str(foreign_workspace)},
        )
        connection.execute(
            text(
                "INSERT INTO campaigns (id, workspace_id, name, keywords, subreddits,"
                " competitors, approved_claims, prohibited_claims, promotion_posture,"
                " status) VALUES (:id, :workspace, 'foreign', '[]'::jsonb, '[]'::jsonb,"
                " '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, 'balanced', 'draft')"
            ),
            {
                "id": str(foreign_campaign),
                "workspace": str(foreign_workspace),
            },
        )

    listing = client.get("/campaigns")
    assert [campaign["name"] for campaign in listing.json()["items"]] == []
    assert client.get(f"/campaigns/{foreign_campaign}").status_code == 404
    assert (
        client.patch(
            f"/campaigns/{foreign_campaign}",
            headers=write_headers(),
            json={"name": "x"},
        ).status_code
        == 404
    )


def test_campaign_service_rejects_a_principal_without_workspace_access(
    migrated_test_database: str,
) -> None:
    engine = create_engine(migrated_test_database)
    principal = Principal(actor="outsider", workspace_ids=frozenset())
    try:
        with (
            Session(engine) as session,
            pytest.raises(campaigns_service.WorkspaceAccessDenied),
        ):
            campaigns_service.list_campaigns(
                session,
                principal,
                DEFAULT_WORKSPACE_ID,
                limit=50,
                cursor=None,
            )
    finally:
        engine.dispose()


def test_patch_updates_fields_without_touching_status(client: TestClient) -> None:
    created = created_campaign(client)

    response = client.patch(
        f"/campaigns/{created['id']}",
        headers=write_headers(),
        json={"name": "Renamed", "keywords": ["API security"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["keywords"] == ["API security"]
    assert body["status"] == "draft"


def test_patch_contract_rejects_unknown_fields(client: TestClient) -> None:
    created = created_campaign(client)

    response = client.patch(
        f"/campaigns/{created['id']}", headers=write_headers(), json={"surprise": 1}
    )

    assert response.status_code == 422


def test_lifecycle_walks_the_legal_path_and_audits_transitions(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    for target in ("active", "paused", "active", "archived"):
        response = client.patch(
            f"/campaigns/{campaign_id}",
            headers=write_headers(),
            json={"status": target},
        )
        assert response.status_code == 200
        assert response.json()["status"] == target
    assert response.json()["archived_at"] is not None

    events = audit_events(migrated_test_database, campaign_id)
    assert [event.action for event in events] == [
        "campaign.created",
        "campaign.transitioned",
        "campaign.transitioned",
        "campaign.transitioned",
        "campaign.transitioned",
    ]
    transitions = [
        (event.before["status"], event.after["status"]) for event in events[1:]
    ]
    assert transitions == [
        ("draft", "active"),
        ("active", "paused"),
        ("paused", "active"),
        ("active", "archived"),
    ]


def test_illegal_transitions_rejected_with_stable_code(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    response = client.patch(
        f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "paused"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "campaign_invalid_transition"
    assert "draft -> paused" in response.json()["detail"]["message"]
    assert client.get(f"/campaigns/{campaign_id}").json()["status"] == "draft"

    assert (
        client.patch(
            f"/campaigns/{campaign_id}",
            headers=write_headers(),
            json={"status": "archived"},
        ).status_code
        == 409
    )


def test_field_update_with_illegal_transition_is_rejected_atomically(
    client: TestClient,
) -> None:
    created = created_campaign(client)

    response = client.patch(
        f"/campaigns/{created['id']}",
        headers=write_headers(),
        json={"name": "Should not stick", "status": "paused"},
    )

    assert response.status_code == 409
    assert client.get(f"/campaigns/{created['id']}").json()["name"] == created["name"]


def test_archived_campaign_is_read_only(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    for target in ("active", "archived"):
        assert (
            client.patch(
                f"/campaigns/{campaign_id}",
                headers=write_headers(),
                json={"status": target},
            ).status_code
            == 200
        )

    field_edit = client.patch(
        f"/campaigns/{campaign_id}", headers=write_headers(), json={"name": "X"}
    )
    reopen = client.patch(
        f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "active"}
    )
    same_status = client.patch(
        f"/campaigns/{campaign_id}",
        headers=write_headers(),
        json={"status": "archived"},
    )

    assert field_edit.status_code == 409
    assert field_edit.json()["detail"]["code"] == "campaign_archived"
    assert reopen.status_code == 409
    assert reopen.json()["detail"]["code"] == "campaign_archived"
    # Even repeating the archived status carries write intent and is refused;
    # read-only means no PATCH with any payload is accepted.
    assert same_status.status_code == 409
    assert same_status.json()["detail"]["code"] == "campaign_archived"


def test_same_status_patch_is_an_idempotent_noop(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    assert (
        client.patch(
            f"/campaigns/{campaign_id}",
            headers=write_headers(),
            json={"status": "active"},
        ).status_code
        == 200
    )
    before_events = audit_events(migrated_test_database, campaign_id)

    response = client.patch(
        f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "active"}
    )

    assert response.status_code == 200
    assert audit_events(migrated_test_database, campaign_id) == before_events


def test_writes_require_an_idempotency_key(client: TestClient) -> None:
    response = client.post(
        "/campaigns",
        json=create_payload(),
        headers={"Authorization": f"Bearer {API_TOKEN}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_required"


def test_writes_reject_overlong_idempotency_keys(client: TestClient) -> None:
    response = client.post(
        "/campaigns",
        json=create_payload(),
        headers=write_headers("x" * 201),
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_too_long"
    assert client.get("/campaigns").json()["items"] == []


def test_create_replay_returns_the_original_campaign_without_duplicating(
    client: TestClient, migrated_test_database: str
) -> None:
    key = str(uuid.uuid4())
    first = client.post("/campaigns", json=create_payload(), headers=write_headers(key))
    second = client.post(
        "/campaigns", json=create_payload(), headers=write_headers(key)
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    listing = client.get("/campaigns").json()
    assert [campaign["id"] for campaign in listing["items"]] == [first.json()["id"]]
    assert [
        event.action
        for event in audit_events(migrated_test_database, first.json()["id"])
    ] == ["campaign.created"]


def test_key_reuse_with_a_different_payload_conflicts(client: TestClient) -> None:
    key = str(uuid.uuid4())
    created = client.post(
        "/campaigns", json=create_payload(), headers=write_headers(key)
    )
    assert created.status_code == 201

    conflict = client.post(
        "/campaigns",
        json=create_payload(name="A different campaign"),
        headers=write_headers(key),
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_key_conflict"


def test_transition_replay_returns_the_original_response_without_duplicate_audits(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    key = str(uuid.uuid4())
    first = client.patch(
        f"/campaigns/{created['id']}",
        json={"status": "active"},
        headers=write_headers(key),
    )
    second = client.patch(
        f"/campaigns/{created['id']}",
        json={"status": "active"},
        headers=write_headers(key),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    transitions = [
        event
        for event in audit_events(migrated_test_database, created["id"])
        if event.action == "campaign.transitioned"
    ]
    assert len(transitions) == 1


def test_campaign_audit_is_authorized_and_cursor_paginated(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    assert (
        client.patch(
            f"/campaigns/{campaign_id}",
            headers=write_headers(),
            json={"name": "Renamed"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/campaigns/{campaign_id}",
            headers=write_headers(),
            json={"status": "active"},
        ).status_code
        == 200
    )

    newest = client.get(f"/campaigns/{campaign_id}/audit", params={"limit": 2})
    older = client.get(
        f"/campaigns/{campaign_id}/audit",
        params={"limit": 2, "cursor": newest.json()["next_cursor"]},
    )

    assert newest.status_code == 200
    assert [event["action"] for event in newest.json()["items"]] == [
        "campaign.transitioned",
        "campaign.updated",
    ]
    assert [event["action"] for event in older.json()["items"]] == ["campaign.created"]
    assert older.json()["next_cursor"] is None
    assert all(event["actor"] == "operator" for event in newest.json()["items"])


def test_campaign_audit_filters_events_by_workspace(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    foreign_workspace = uuid.uuid4()
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text("INSERT INTO workspaces (id, name) VALUES (:id, :name)"),
            {"id": str(foreign_workspace), "name": f"audit-{foreign_workspace}"},
        )
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, workspace_id, actor, action, target_type, target_id) "
                "VALUES (:id, :workspace, 'foreign', 'foreign.audit', 'campaign', "
                ":target)"
            ),
            {
                "id": str(uuid.uuid4()),
                "workspace": str(foreign_workspace),
                "target": created["id"],
            },
        )

    response = client.get(f"/campaigns/{created['id']}/audit")

    assert response.status_code == 200
    assert [event["action"] for event in response.json()["items"]] == [
        "campaign.created"
    ]


def test_campaign_audit_hides_unknown_campaigns_and_rejects_wrong_cursor(
    client: TestClient,
) -> None:
    unknown = client.get(f"/campaigns/{uuid.uuid4()}/audit")
    created = created_campaign(client)
    campaign_page = client.get("/campaigns", params={"limit": 1}).json()
    wrong_cursor = client.get(
        f"/campaigns/{created['id']}/audit",
        params={"cursor": campaign_page["next_cursor"] or "not-a-cursor"},
    )

    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "campaign_not_found"
    assert wrong_cursor.status_code == 400
    assert wrong_cursor.json()["detail"]["code"] == "page_cursor_invalid"


def test_transition_error_replay_preserves_the_original_result(
    client: TestClient,
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    key = str(uuid.uuid4())

    first = client.patch(
        f"/campaigns/{campaign_id}",
        json={"status": "paused"},
        headers=write_headers(key),
    )
    activated = client.patch(
        f"/campaigns/{campaign_id}",
        json={"status": "active"},
        headers=write_headers(),
    )
    replay = client.patch(
        f"/campaigns/{campaign_id}",
        json={"status": "paused"},
        headers=write_headers(key),
    )

    assert first.status_code == 409
    assert activated.status_code == 200
    assert replay.status_code == 409
    assert replay.json() == first.json()
    assert client.get(f"/campaigns/{campaign_id}").json()["status"] == "active"


def test_patch_rejects_explicit_null_on_non_nullable_fields(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    for field in ("name", "keywords", "promotion_posture", "status"):
        response = client.patch(
            f"/campaigns/{campaign_id}",
            json={field: None},
            headers=write_headers(),
        )
        assert response.status_code == 422, field

    # Nothing slipped through to the stored campaign.
    assert client.get(f"/campaigns/{campaign_id}").json() == created


def test_patch_clears_nullable_fields_with_explicit_null(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    response = client.patch(
        f"/campaigns/{campaign_id}",
        json={"product_context": None, "icp": None},
        headers=write_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_context"] is None
    assert body["icp"] is None


def test_concurrent_transitions_never_produce_a_half_archived_campaign(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    assert (
        client.patch(
            f"/campaigns/{campaign_id}",
            json={"status": "active"},
            headers=write_headers(),
        ).status_code
        == 200
    )

    app = client.app
    outcomes: dict[str, Any] = {}

    def api_pause() -> None:
        try:
            with TestClient(
                app, headers={"Authorization": f"Bearer {API_TOKEN}"}
            ) as writer:
                response = writer.patch(
                    f"/campaigns/{campaign_id}",
                    json={"status": "paused"},
                    headers=write_headers(),
                )
            outcomes["pause"] = response.status_code
        except BaseException as error:
            outcomes["error"] = error

    engine = create_engine(migrated_test_database)
    lock_connection = engine.connect()
    lock_transaction = lock_connection.begin()
    lock_holder_pid = lock_connection.execute(
        text("SELECT pg_backend_pid()")
    ).scalar_one()
    pause_thread = threading.Thread(target=api_pause)
    observed_lock_wait = False
    try:
        lock_connection.execute(
            text(
                "UPDATE campaigns SET status = 'archived', archived_at = now()"
                " WHERE id = :id"
            ),
            {"id": campaign_id},
        )
        pause_thread.start()

        deadline = time.monotonic() + 5
        with engine.connect() as observer:
            while time.monotonic() < deadline and pause_thread.is_alive():
                observed_lock_wait = bool(
                    observer.execute(
                        text(
                            "SELECT EXISTS ("
                            " SELECT 1 FROM pg_stat_activity AS activity"
                            " WHERE datname = current_database()"
                            " AND pid <> pg_backend_pid()"
                            " AND :holder_pid = ANY(pg_blocking_pids(activity.pid))"
                            ")"
                        ),
                        {"holder_pid": lock_holder_pid},
                    ).scalar_one()
                )
                if observed_lock_wait:
                    break
                time.sleep(0.01)
        lock_transaction.commit()
    finally:
        if lock_transaction.is_active:
            lock_transaction.rollback()
        lock_connection.close()
        engine.dispose()

    pause_thread.join(timeout=5)

    stored = client.get(f"/campaigns/{campaign_id}").json()
    assert not pause_thread.is_alive()
    assert "error" not in outcomes
    assert observed_lock_wait
    # The API read was forced to wait behind the archive row lock, so it must
    # validate the newly committed terminal state rather than a stale ACTIVE.
    assert outcomes["pause"] == 409
    assert stored["status"] == "archived"
    assert stored["archived_at"] is not None


def test_requests_fail_closed_when_the_default_workspace_is_missing(
    client: TestClient, migrated_test_database: str
) -> None:
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(text("DELETE FROM idempotency_events"))
        connection.execute(text("DELETE FROM campaigns"))
        connection.execute(text("DELETE FROM workspaces"))

    listing = client.get("/campaigns")
    write = client.post("/campaigns", json=create_payload(), headers=write_headers())

    assert listing.status_code == 503
    assert listing.json()["detail"]["code"] == "workspace_unconfigured"
    assert write.status_code == 503
    assert write.json()["detail"]["code"] == "workspace_unconfigured"


def test_crash_between_mutation_and_commit_rolls_back_and_retries_cleanly(
    client: TestClient, migrated_test_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_stage_create = campaigns_service._stage_create_campaign

    def crash_after_mutation(*args: Any, **kwargs: Any) -> Any:
        real_stage_create(*args, **kwargs)
        raise RuntimeError("crash between mutation and commit")

    monkeypatch.setattr(
        campaigns_service, "_stage_create_campaign", crash_after_mutation
    )
    key = str(uuid.uuid4())
    with pytest.raises(RuntimeError):
        client.post("/campaigns", json=create_payload(), headers=write_headers(key))
    monkeypatch.undo()

    with create_engine(migrated_test_database).connect() as connection:
        campaigns = connection.execute(
            text("SELECT count(*) FROM campaigns")
        ).scalar_one()
        claims = connection.execute(
            text("SELECT count(*) FROM idempotency_events")
        ).scalar_one()
    assert campaigns == 0
    assert claims == 0

    retried = client.post(
        "/campaigns", json=create_payload(), headers=write_headers(key)
    )

    assert retried.status_code == 201
    assert [c["id"] for c in client.get("/campaigns").json()["items"]] == [
        retried.json()["id"]
    ]
