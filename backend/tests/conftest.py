"""Shared test fixtures: migrate a dedicated test database before the suite."""

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from psycopg import connect, sql
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get(
    "APTORI_TEST_DATABASE_URL",
    "postgresql+psycopg://@/aptori_outreach_test",
)


def configured_database_url(database_name: str) -> str:
    """Use the configured test server while selecting a dedicated database."""
    return (
        make_url(TEST_DATABASE_URL)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


def admin_database_url(database_url: str) -> str:
    """Connect to the configured PostgreSQL server's administrative database."""
    return (
        make_url(database_url)
        .set(drivername="postgresql", database="postgres")
        .render_as_string(hide_password=False)
    )


def _ensure_database(database_url: str) -> None:
    """Create the test database if it does not exist (superuser/owner only)."""
    database = make_url(database_url).database
    if not database:
        raise RuntimeError(f"Test database URL has no database name: {database_url}")
    with connect(admin_database_url(database_url), autocommit=True) as connection:
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
