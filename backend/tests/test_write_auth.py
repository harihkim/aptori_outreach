"""Campaign authentication and OpenAPI behavior at the FastAPI boundary."""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.main import create_app

API_TOKEN = "test-token"


def make_client(api_token: str | None, migrated_test_database: str) -> TestClient:
    return TestClient(create_app(database_url=migrated_test_database, api_token=api_token))


def create_payload() -> dict[str, Any]:
    return {
        "name": "API security listening",
        "promotion_posture": "expertise_first",
    }


@pytest.fixture(autouse=True)
def clean_campaign_rows(migrated_test_database: str) -> Iterator[None]:
    yield
    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(text("DELETE FROM audit_events"))
        connection.execute(text("DELETE FROM idempotency_events"))
        connection.execute(text("DELETE FROM campaigns"))


def test_writes_fail_closed_when_no_token_is_configured(
    migrated_test_database: str,
) -> None:
    with make_client(None, migrated_test_database) as client:
        response = client.post("/campaigns", json=create_payload())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "api_token_unconfigured"


def test_writes_reject_a_missing_bearer_token(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        response = client.post("/campaigns", json=create_payload())

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_writes_reject_a_wrong_bearer_token(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        response = client.post(
            "/campaigns",
            json=create_payload(),
            headers={"Authorization": "Bearer not-the-token"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_writes_accept_the_configured_bearer_token(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        response = client.post(
            "/campaigns",
            json=create_payload(),
            headers={
                "Authorization": f"Bearer {API_TOKEN}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
def test_an_empty_configured_token_is_treated_as_unconfigured(
    migrated_test_database: str,
) -> None:
    with make_client("", migrated_test_database) as client:
        denied = client.post(
            "/campaigns",
            json=create_payload(),
            headers={
                "Authorization": "Bearer ",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )

    assert denied.status_code == 503
    assert denied.json()["detail"]["code"] == "api_token_unconfigured"


def test_settings_normalizes_an_empty_token_to_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings

    monkeypatch.setenv("APTORI_API_TOKEN", "")
    settings = Settings(_env_file=None)

    assert settings.api_token is None


def test_reads_require_the_bearer_token(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        denied = client.get("/campaigns")
        allowed = client.get(
            "/campaigns", headers={"Authorization": f"Bearer {API_TOKEN}"}
        )

    assert denied.status_code == 401
    assert denied.json()["detail"]["code"] == "unauthorized"
    assert allowed.status_code == 200


def test_openapi_documents_campaign_contracts(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        spec = client.get("/openapi.json").json()

    post = spec["paths"]["/campaigns"]["post"]
    assert "$ref" in post["responses"]["201"]["content"]["application/json"]["schema"]
    patch = spec["paths"]["/campaigns/{campaign_id}"]["patch"]
    assert "$ref" in patch["responses"]["200"]["content"]["application/json"]["schema"]
    assert spec["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert post["security"] == [{"HTTPBearer": []}]
    assert patch["security"] == [{"HTTPBearer": []}]
    assert any(
        parameter["in"] == "header" and parameter["name"] == "Idempotency-Key"
        for parameter in post["parameters"]
    )
    assert "headers" not in post["responses"]["201"]
    list_responses = spec["paths"]["/campaigns"]["get"]["responses"]
    assert "400" not in list_responses
    assert "409" not in list_responses
    assert "security" not in spec["paths"]["/health"]["get"]
    assert spec["components"]["schemas"]["ErrorResponse"]
