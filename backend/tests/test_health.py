"""Health endpoint and migration behavior against the migrated test database."""

from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL


def test_health_reports_ok_when_database_is_reachable(migrated_test_database: str) -> None:
    client = TestClient(create_app(database_url=migrated_test_database))
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_degraded_when_database_is_unreachable() -> None:
    unreachable = "postgresql+psycopg://@/no_such_database_health_probe"
    client = TestClient(create_app(database_url=unreachable))
    response = client.get("/health")
    assert response.status_code == 503


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
        # The baseline creates no domain tables; only Alembic's own bookkeeping exists.
        tables = set(inspect(connection).get_table_names())
        assert tables == {"alembic_version"}
