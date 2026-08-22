"""Migration behavior: the domain baseline (Workspace, Campaign, AuditEvent) round-trips."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.conftest import TEST_DATABASE_URL

HEAD_REVISION = "0002_campaigns_audit"


def _alembic_config(database_url: str) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    return alembic_cfg


def test_domain_migration_applies_and_rolls_back_cleanly(migrated_test_database: str) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)

    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    from alembic.runtime.migration import MigrationContext

    with create_engine(migrated_test_database).connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == HEAD_REVISION
        tables = set(inspect(connection).get_table_names())
        assert tables == {"alembic_version", "workspaces", "campaigns", "audit_events"}


def test_migration_seeds_the_default_workspace(migrated_test_database: str) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)

    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    with create_engine(TEST_DATABASE_URL).connect() as connection:
        seeded = connection.execute(text("SELECT id FROM workspaces")).fetchall()

    assert [row[0] for row in seeded] == [DEFAULT_WORKSPACE_ID]
