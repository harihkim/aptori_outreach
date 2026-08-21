"""Shared test fixtures: migrate a dedicated test database before the suite."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from psycopg import connect, sql

TEST_DATABASE_URL = os.environ.get(
    "APTORI_TEST_DATABASE_URL",
    "postgresql+psycopg://@/aptori_outreach_test",
)


def _ensure_database(database_url: str) -> None:
    """Create the test database if it does not exist (superuser/owner only)."""
    prefix = "postgresql+psycopg://"
    if not database_url.startswith(prefix):
        raise RuntimeError(f"Unsupported test database URL: {database_url}")
    admin_url = "postgresql://" + database_url[len(prefix):]
    base, _, database = admin_url.rpartition("/")
    with connect(base or "postgresql://", autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
        ).fetchone()
        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database))
            )


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> Iterator[str]:
    _ensure_database(TEST_DATABASE_URL)
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
    yield TEST_DATABASE_URL
