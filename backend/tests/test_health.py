"""Health endpoint, session management, and migration behavior on the test database."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from alembic.config import Config
from app.db import DatabaseSessionManager
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL


def test_health_reports_ok_with_unified_contract(migrated_test_database: str) -> None:
    with TestClient(create_app(database_url=migrated_test_database)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api": "reachable",
        "database": "ok",
        "detail": None,
    }


def test_health_reports_degraded_without_leaking_diagnostics(
    migrated_test_database: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(database_url=migrated_test_database)
    leaky_diagnostic = (
        "OperationalError against db-host-internal/no_such_db "
        "(password=super_secret user=secret_user)"
    )
    app.state.database.probe = lambda: (False, leaky_diagnostic)

    with caplog.at_level(logging.WARNING):
        with TestClient(app) as client:
            response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["api"] == "reachable"
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    # The response carries the safe constant only; nothing from the diagnostic.
    assert body["detail"] == "database unavailable"
    for secret in ("super_secret", "secret_user", "db-host-internal"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_probe_logs_classification_without_credentials(caplog: pytest.LogCaptureFixture) -> None:
    # Local socket + missing database fails fast; credentials ride along to prove
    # they never reach the log.
    manager = DatabaseSessionManager("postgresql+psycopg://secret_user:super_secret@/no_such_db")
    with caplog.at_level(logging.WARNING):
        healthy, diagnostic = manager.probe()

    assert healthy is False
    assert diagnostic is not None
    assert "OperationalError" in diagnostic
    assert "/no_such_db" in diagnostic
    assert "super_secret" not in diagnostic
    assert "super_secret" not in caplog.text
    assert "OperationalError" in caplog.text


def test_lifespan_disposes_the_session_manager(migrated_test_database: str) -> None:
    app = create_app(database_url=migrated_test_database)
    manager = app.state.database
    calls: list[str] = []
    original_dispose = manager.dispose

    def spy() -> None:
        calls.append("dispose")
        original_dispose()

    manager.dispose = spy

    with TestClient(app) as client:
        assert calls == []
        assert client.get("/health").status_code == 200

    assert calls == ["dispose"]


def test_session_manager_yields_working_sessions(migrated_test_database: str) -> None:
    manager = DatabaseSessionManager(migrated_test_database)
    sessions = manager.session()
    session = next(sessions)
    assert session.execute(text("SELECT 1")).scalar() == 1
    sessions.close()


def test_baseline_migration_applies_and_rolls_back_cleanly(migrated_test_database: str) -> None:
    # Domain-table round-trip behavior lives in test_migrations.py; this test
    # pins the shared downgrade/upgrade machinery itself on the baseline step.
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", migrated_test_database)

    command.downgrade(alembic_cfg, "0001_baseline")
    command.upgrade(alembic_cfg, "head")

    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    with create_engine(migrated_test_database).connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() is not None
        assert "alembic_version" in set(inspect(connection).get_table_names())
