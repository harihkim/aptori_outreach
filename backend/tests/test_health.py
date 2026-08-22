"""Health endpoint, session management, and migration behavior on the test database."""

from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from alembic.config import Config
from app.db import DatabaseSessionManager
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL


def client() -> TestClient:
    return TestClient(create_app(database_url=TEST_DATABASE_URL))


def test_health_reports_ok_with_unified_contract(migrated_test_database: str) -> None:
    response = client().get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "api": "reachable",
        "database": "ok",
        "detail": None,
    }


def test_health_reports_degraded_when_database_is_unreachable() -> None:
    unreachable = "postgresql+psycopg://@/no_such_database_health_probe"
    response = TestClient(create_app(database_url=unreachable)).get("/health")
    assert response.status_code == 503
    body = response.json()
    # The API answered; only the database is down. The shape matches 200 responses.
    assert body["api"] == "reachable"
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert body["detail"] is not None


def test_session_manager_yields_working_sessions(migrated_test_database: str) -> None:
    manager = DatabaseSessionManager(migrated_test_database)
    sessions = manager.session()
    session = next(sessions)
    assert session.execute(text("SELECT 1")).scalar() == 1
    sessions.close()


def test_baseline_migration_applies_and_rolls_back_cleanly(migrated_test_database: str) -> None:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", migrated_test_database)

    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, inspect

    with create_engine(migrated_test_database).connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0001_baseline"
        tables = set(inspect(connection).get_table_names())
        assert tables == {"alembic_version"}
