"""Campaign REST API at the FastAPI app boundary."""

import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

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
    response = client.post("/campaigns", headers=write_headers(), json=create_payload(name="   "))

    assert response.status_code == 422


def test_create_validation_rejects_unknown_posture(client: TestClient) -> None:
    response = client.post("/campaigns", headers=write_headers(), json=create_payload(promotion_posture="aggressive"))

    assert response.status_code == 422


def test_create_contract_is_closed_to_unknown_fields(client: TestClient) -> None:
    response = client.post("/campaigns", headers=write_headers(), json=create_payload(surprise="value"))

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
    response = client.post("/campaigns", headers=write_headers(), json=create_payload(**overrides))
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


def test_list_campaigns_orders_newest_first(client: TestClient) -> None:
    first = created_campaign(client, name="first campaign")
    second = created_campaign(client, name="second campaign")

    response = client.get("/campaigns")

    assert response.status_code == 200
    assert [campaign["name"] for campaign in response.json()] == [
        "second campaign",
        "first campaign",
    ]


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
    assert [campaign["name"] for campaign in listing.json()] == []
    assert client.get(f"/campaigns/{foreign_campaign}").status_code == 404
    assert (
        client.patch(f"/campaigns/{foreign_campaign}", headers=write_headers(), json={"name": "x"}).status_code
        == 404
    )


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

    response = client.patch(f"/campaigns/{created['id']}", headers=write_headers(), json={"surprise": 1})

    assert response.status_code == 422


def test_lifecycle_walks_the_legal_path_and_audits_transitions(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    for target in ("active", "paused", "active", "archived"):
        response = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": target})
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

    response = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "paused"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "campaign_invalid_transition"
    assert "draft -> paused" in response.json()["detail"]["message"]
    assert client.get(f"/campaigns/{campaign_id}").json()["status"] == "draft"

    assert (
        client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "archived"}).status_code
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
            client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": target}).status_code
            == 200
        )

    field_edit = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"name": "X"})
    reopen = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "active"})
    same_status = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "archived"})

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
        client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "active"}).status_code
        == 200
    )
    before_events = audit_events(migrated_test_database, campaign_id)

    response = client.patch(f"/campaigns/{campaign_id}", headers=write_headers(), json={"status": "active"})

    assert response.status_code == 200
    assert audit_events(migrated_test_database, campaign_id) == before_events


def test_writes_require_an_idempotency_key(client: TestClient) -> None:
    response = client.post(
        "/campaigns", json=create_payload(), headers={"Authorization": f"Bearer {API_TOKEN}"}
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "idempotency_key_required"


def test_create_replay_returns_the_original_campaign_without_duplicating(
    client: TestClient, migrated_test_database: str
) -> None:
    key = str(uuid.uuid4())
    first = client.post("/campaigns", json=create_payload(), headers=write_headers(key))
    second = client.post("/campaigns", json=create_payload(), headers=write_headers(key))

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json() == first.json()
    listing = client.get("/campaigns").json()
    assert [campaign["id"] for campaign in listing] == [first.json()["id"]]
    assert [
        event.action for event in audit_events(migrated_test_database, first.json()["id"])
    ] == ["campaign.created"]


def test_key_reuse_with_a_different_payload_conflicts(client: TestClient) -> None:
    key = str(uuid.uuid4())
    created = client.post("/campaigns", json=create_payload(), headers=write_headers(key))
    assert created.status_code == 201

    conflict = client.post(
        "/campaigns", json=create_payload(name="A different campaign"), headers=write_headers(key)
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


def test_patch_rejects_explicit_null_fields(client: TestClient) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]

    for field in ("name", "keywords", "promotion_posture", "status", "product_context"):
        response = client.patch(
            f"/campaigns/{campaign_id}",
            json={field: None},
            headers=write_headers(),
        )
        assert response.status_code == 422, field

    # Nothing slipped through to the stored campaign.
    assert client.get(f"/campaigns/{campaign_id}").json() == created


def test_transition_races_cannot_revive_an_archived_campaign(
    client: TestClient, migrated_test_database: str
) -> None:
    created = created_campaign(client)
    campaign_id = created["id"]
    assert (
        client.patch(
            f"/campaigns/{campaign_id}", json={"status": "active"}, headers=write_headers()
        ).status_code
        == 200
    )

    def concurrent_archive() -> None:
        engine = create_engine(migrated_test_database)
        with engine.begin() as connection:
            # Takes and holds the campaign's row lock in an open
            # transaction while the API request below arrives.
            connection.execute(
                text(
                    "UPDATE campaigns SET status = 'archived', archived_at = now()"
                    " WHERE id = :id"
                ),
                {"id": campaign_id},
            )
            time.sleep(0.4)
        engine.dispose()

    thread = threading.Thread(target=concurrent_archive)
    thread.start()
    time.sleep(0.1)

    response = client.patch(
        f"/campaigns/{campaign_id}", json={"status": "paused"}, headers=write_headers()
    )
    thread.join()

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "campaign_archived"
    stored = client.get(f"/campaigns/{campaign_id}").json()
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
    write = client.post(
        "/campaigns", json=create_payload(), headers=write_headers()
    )

    assert listing.status_code == 503
    assert listing.json()["detail"]["code"] == "workspace_unconfigured"
    assert write.status_code == 503
    assert write.json()["detail"]["code"] == "workspace_unconfigured"
