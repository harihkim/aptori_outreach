"""Migration behavior: the domain baseline (Workspace, Campaign, AuditEvent) round-trips."""

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.conftest import TEST_DATABASE_URL

HEAD_REVISION = "0005_stable_page_order"


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
        assert tables == {
            "alembic_version",
            "workspaces",
            "campaigns",
            "audit_events",
            "idempotency_events",
        }
        campaign_columns = {column["name"] for column in inspect(connection).get_columns("campaigns")}
        audit_columns = {column["name"] for column in inspect(connection).get_columns("audit_events")}
        assert "creation_order" in campaign_columns
        assert "event_order" in audit_columns


def test_migration_seeds_the_default_workspace(migrated_test_database: str) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)

    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")

    with create_engine(TEST_DATABASE_URL).connect() as connection:
        seeded = connection.execute(text("SELECT id FROM workspaces")).fetchall()

    assert [row[0] for row in seeded] == [DEFAULT_WORKSPACE_ID]


def test_migration_reconciles_legacy_pending_idempotency_rows(
    migrated_test_database: str,
) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)
    command.downgrade(alembic_cfg, "0003_idempotency_events")

    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text("DELETE FROM idempotency_events WHERE key = 'legacy-pending'")
        )
        connection.execute(
            text(
                "INSERT INTO idempotency_events "
                "(id, key, workspace_id, request_fingerprint) "
                "VALUES (:id, :key, :workspace, :fingerprint)"
            ),
            {
                "id": "00000000-0000-0000-0000-000000000004",
                "key": "legacy-pending",
                "workspace": str(DEFAULT_WORKSPACE_ID),
                "fingerprint": "a" * 64,
            },
        )

    command.upgrade(alembic_cfg, "head")

    with create_engine(migrated_test_database).connect() as connection:
        row = connection.execute(
            text(
                "SELECT status_code, response_body FROM idempotency_events "
                "WHERE key = 'legacy-pending'"
            )
        ).one()

    assert row.status_code == 409
    assert row.response_body["detail"]["code"] == (
        "idempotency_key_reconciliation_required"
    )

    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text("DELETE FROM idempotency_events WHERE key = 'legacy-pending'")
        )


def test_stable_order_migration_backfills_existing_rows(
    migrated_test_database: str,
) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)
    command.downgrade(alembic_cfg, "0004_reconcile_idempotency")
    campaign_id = "00000000-0000-0000-0000-000000000005"
    event_id = "00000000-0000-0000-0000-000000000006"

    with create_engine(migrated_test_database).begin() as connection:
        connection.execute(
            text(
                "INSERT INTO campaigns "
                "(id, workspace_id, name, promotion_posture) "
                "VALUES (:id, :workspace, 'legacy', 'expertise_first')"
            ),
            {"id": campaign_id, "workspace": str(DEFAULT_WORKSPACE_ID)},
        )
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, actor, action, target_type, target_id) "
                "VALUES (:id, 'operator', 'campaign.created', 'campaign', :target)"
            ),
            {"id": event_id, "target": campaign_id},
        )

    command.upgrade(alembic_cfg, "head")

    with create_engine(migrated_test_database).begin() as connection:
        campaign_order = connection.execute(
            text("SELECT creation_order FROM campaigns WHERE id = :id"),
            {"id": campaign_id},
        ).scalar_one()
        event_order = connection.execute(
            text("SELECT event_order FROM audit_events WHERE id = :id"),
            {"id": event_id},
        ).scalar_one()
        assert campaign_order > 0
        assert event_order > 0
        connection.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id})
        connection.execute(text("DELETE FROM campaigns WHERE id = :id"), {"id": campaign_id})
