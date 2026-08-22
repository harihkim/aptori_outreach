"""Write authentication at the FastAPI app boundary."""

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


def test_reads_stay_open_to_the_local_operator(migrated_test_database: str) -> None:
    with make_client(API_TOKEN, migrated_test_database) as client:
        response = client.get("/campaigns")

    assert response.status_code == 200
    assert response.json() == []
