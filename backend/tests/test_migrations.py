"""Migration behavior: the domain baseline (Workspace, Campaign, AuditEvent) round-trips."""

import uuid
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError

from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.conftest import TEST_DATABASE_URL

HEAD_REVISION = "0011_workspace_ownership"


def _alembic_config(database_url: str) -> Config:
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    return alembic_cfg


def _purge_observations(database_url: str) -> None:
    """Test-only cleanup: the table OWNER disables its guard triggers.

    No privileged runtime surface exists in production (the SECURITY DEFINER
    helper was removed in 0008); tests use plain owner SQL instead.
    """
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE retrieval_observations DISABLE TRIGGER USER")
            )
            connection.execute(text("TRUNCATE retrieval_observations"))
            connection.execute(
                text("ALTER TABLE retrieval_observations ENABLE TRIGGER USER")
            )
    finally:
        engine.dispose()


def observation_count(database_url: str) -> int:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return int(
                connection.execute(
                    text("SELECT count(*) FROM retrieval_observations")
                ).scalar_one()
            )
    finally:
        engine.dispose()


def test_domain_migration_applies_and_rolls_back_cleanly(
    migrated_test_database: str,
) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)

    # A previous suite may have left immutable evidence behind; only the
    # owner-side purge may empty the table before a full round trip.
    _purge_observations(migrated_test_database)

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
            "discovery_runs",
            "retrieval_observations",
        }
        campaign_columns = {
            column["name"] for column in inspect(connection).get_columns("campaigns")
        }
        audit_columns = {
            column["name"] for column in inspect(connection).get_columns("audit_events")
        }
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
        event_workspace = connection.execute(
            text("SELECT workspace_id FROM audit_events WHERE id = :id"),
            {"id": event_id},
        ).scalar_one()
        assert campaign_order > 0
        assert event_order > 0
        assert event_workspace == DEFAULT_WORKSPACE_ID
        connection.execute(
            text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id}
        )
        connection.execute(
            text("DELETE FROM campaigns WHERE id = :id"), {"id": campaign_id}
        )


def _prepare_legacy_ownership_database(database_url: str) -> Config:
    """Return a clean 0010 database for data-dependent migration tests."""
    _purge_observations(database_url)
    alembic_cfg = _alembic_config(database_url)
    command.downgrade(alembic_cfg, "0010_obs_workspace_idx")
    return alembic_cfg


def _delete_rows(
    connection: Connection, table: str, row_ids: tuple[uuid.UUID, ...]
) -> None:
    """Delete test rows by id; table names are fixed by the callers below."""
    if not row_ids:
        return
    reflected = Table(table, MetaData(), autoload_with=connection)
    connection.execute(reflected.delete().where(reflected.c.id.in_(row_ids)))


def _finish_legacy_ownership_case(
    database_url: str,
    alembic_cfg: Config,
    engine: Engine,
    *,
    audit_ids: tuple[uuid.UUID, ...] = (),
    campaign_ids: tuple[uuid.UUID, ...] = (),
    run_ids: tuple[uuid.UUID, ...] = (),
    workspace_ids: tuple[uuid.UUID, ...] = (),
) -> None:
    """Restore head after deleting the rows owned by one migration test."""
    _purge_observations(database_url)
    with engine.begin() as connection:
        _delete_rows(connection, "audit_events", audit_ids)
        _delete_rows(connection, "discovery_runs", run_ids)
        _delete_rows(connection, "campaigns", campaign_ids)
        _delete_rows(connection, "workspaces", workspace_ids)
    engine.dispose()
    command.upgrade(alembic_cfg, "head")


def _insert_row(
    connection: Connection, table_name: str, values: dict[str, Any]
) -> None:
    """Insert a migration fixture row using the revision's live table shape."""
    table = Table(table_name, MetaData(), autoload_with=connection)
    connection.execute(table.insert(), values)


def _insert_workspace(
    connection: Connection, workspace_id: uuid.UUID, *, name: str
) -> None:
    _insert_row(connection, "workspaces", {"id": workspace_id, "name": name})


def _insert_campaign(
    connection: Connection,
    campaign_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    name: str,
) -> None:
    _insert_row(
        connection,
        "campaigns",
        {
            "id": campaign_id,
            "workspace_id": workspace_id,
            "name": name,
            "promotion_posture": "expertise_first",
        },
    )


def _insert_run(
    connection: Connection,
    run_id: uuid.UUID,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    correlation_id: str,
) -> None:
    _insert_row(
        connection,
        "discovery_runs",
        {
            "id": run_id,
            "workspace_id": workspace_id,
            "campaign_id": campaign_id,
            "status": "queued",
            "method_plan": {},
            "correlation_id": correlation_id,
        },
    )


def _insert_observation(
    connection: Connection,
    observation_id: uuid.UUID,
    run_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    query_id: str,
    correlation_id: str,
) -> None:
    _insert_row(
        connection,
        "retrieval_observations",
        {
            "id": observation_id,
            "discovery_run_id": run_id,
            "workspace_id": workspace_id,
            "query_id": query_id,
            "schema_version": 1,
            "capability": "discovery",
            "provider_variant": "test",
            "config_sha256": "a" * 64,
            "observation_id": f"obs-{query_id}",
            "status": "success",
            "evidence_directory": f"/tmp/{query_id}",
            "correlation_id": correlation_id,
        },
    )


def _insert_legacy_audit_event(
    connection: Connection,
    event_id: uuid.UUID,
    target_type: str,
    target_id: uuid.UUID,
) -> None:
    _insert_row(
        connection,
        "audit_events",
        {
            "id": event_id,
            "actor": "migration-test",
            "action": "legacy",
            "target_type": target_type,
            "target_id": target_id,
        },
    )


def test_workspace_ownership_schema_and_idempotency_parity(
    migrated_test_database: str,
) -> None:
    """Head exposes composite ownership while idempotency stays unchanged."""
    command.upgrade(_alembic_config(migrated_test_database), "head")

    with create_engine(migrated_test_database).connect() as connection:
        inspector = inspect(connection)
        for table, name in (
            ("campaigns", "uq_campaigns_workspace_id_id"),
            ("discovery_runs", "uq_discovery_runs_workspace_id_id"),
            ("retrieval_observations", "uq_retrieval_observations_workspace_id_id"),
        ):
            constraints = {
                constraint["name"]: tuple(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table)
            }
            assert constraints[name] == ("workspace_id", "id")

        for table, name, constrained, referred in (
            (
                "discovery_runs",
                "fk_discovery_runs_workspace_id_campaign_id_campaigns",
                ["workspace_id", "campaign_id"],
                ["workspace_id", "id"],
            ),
            (
                "retrieval_observations",
                "fk_retrieval_observations_workspace_id_discovery_run_id_discovery_runs",
                ["workspace_id", "discovery_run_id"],
                ["workspace_id", "id"],
            ),
        ):
            foreign_key = next(
                foreign_key
                for foreign_key in inspector.get_foreign_keys(table)
                if foreign_key["name"] == name
            )
            assert foreign_key["constrained_columns"] == constrained
            assert foreign_key["referred_columns"] == referred

        audit_columns = {
            column["name"]: column for column in inspector.get_columns("audit_events")
        }
        assert audit_columns["workspace_id"]["nullable"] is False
        audit_foreign_keys = {
            foreign_key["name"]: foreign_key
            for foreign_key in inspector.get_foreign_keys("audit_events")
        }
        assert audit_foreign_keys["fk_audit_events_workspace_id_workspaces"][
            "constrained_columns"
        ] == ["workspace_id"]
        audit_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in inspector.get_indexes("audit_events")
        }
        assert audit_indexes["ix_audit_events_workspace_target_order"] == (
            "workspace_id",
            "target_type",
            "target_id",
            "event_order",
        )

        idempotency_constraints = {
            constraint["name"]: tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("idempotency_events")
        }
        assert idempotency_constraints["uq_idempotency_events_workspace_key"] == (
            "workspace_id",
            "key",
        )


def test_head_composite_foreign_keys_reject_cross_workspace_rows(
    migrated_test_database: str,
) -> None:
    """A child cannot point at a same-ID parent from another Workspace."""
    command.upgrade(_alembic_config(migrated_test_database), "head")
    campaign_id, run_id, observation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    campaign_workspace, run_workspace = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrated_test_database)
    try:
        with engine.begin() as connection:
            _insert_workspace(
                connection, campaign_workspace, name=f"owner-{campaign_id}"
            )
            _insert_workspace(connection, run_workspace, name=f"owner-{run_id}")
            _insert_campaign(connection, campaign_id, campaign_workspace, name="owned")

        with pytest.raises(DBAPIError), engine.begin() as connection:
            _insert_run(
                connection,
                run_id,
                run_workspace,
                campaign_id,
                correlation_id="cross-run",
            )

        with engine.begin() as connection:
            _insert_run(
                connection,
                run_id,
                campaign_workspace,
                campaign_id,
                correlation_id="owned-run",
            )

        with pytest.raises(DBAPIError), engine.begin() as connection:
            _insert_observation(
                connection,
                observation_id,
                run_id,
                run_workspace,
                query_id="q-cross",
                correlation_id="cross-observation",
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM discovery_runs WHERE id = :id"),
                {"id": str(run_id)},
            )
            connection.execute(
                text("DELETE FROM campaigns WHERE id = :id"),
                {"id": str(campaign_id)},
            )
            connection.execute(
                text("DELETE FROM workspaces WHERE id IN (:campaign, :run)"),
                {"campaign": str(campaign_workspace), "run": str(run_workspace)},
            )
        engine.dispose()


def test_audit_backfill_resolves_campaign_and_run_workspaces(
    migrated_test_database: str,
) -> None:
    """Legacy audit rows inherit Workspace only from their resolved targets."""
    alembic_cfg = _prepare_legacy_ownership_database(migrated_test_database)
    campaign_id, run_id = uuid.uuid4(), uuid.uuid4()
    campaign_event_id, run_event_id = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrated_test_database)
    try:
        with engine.begin() as connection:
            _insert_campaign(
                connection, campaign_id, DEFAULT_WORKSPACE_ID, name="backfill"
            )
            _insert_run(
                connection,
                run_id,
                DEFAULT_WORKSPACE_ID,
                campaign_id,
                correlation_id="backfill",
            )
            _insert_legacy_audit_event(
                connection, campaign_event_id, "campaign", campaign_id
            )
            _insert_legacy_audit_event(
                connection, run_event_id, "discovery_run", run_id
            )

        command.upgrade(alembic_cfg, "head")

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT workspace_id FROM audit_events WHERE id IN "
                    "(:campaign_event, :run_event)"
                ),
                {
                    "campaign_event": str(campaign_event_id),
                    "run_event": str(run_event_id),
                },
            ).fetchall()
        assert len(rows) == 2
        assert {row.workspace_id for row in rows} == {DEFAULT_WORKSPACE_ID}
    finally:
        _finish_legacy_ownership_case(
            migrated_test_database,
            alembic_cfg,
            engine,
            audit_ids=(campaign_event_id, run_event_id),
            campaign_ids=(campaign_id,),
            run_ids=(run_id,),
        )


def test_ownership_migration_rejects_cross_workspace_relations_before_ddl(
    migrated_test_database: str,
) -> None:
    """Preflight reports both relation mismatches and leaves rows untouched."""
    alembic_cfg = _prepare_legacy_ownership_database(migrated_test_database)
    campaign_id, run_id, observation_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    run_workspace, observation_workspace = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrated_test_database)
    try:
        with engine.begin() as connection:
            _insert_workspace(connection, run_workspace, name=f"run-{run_id}")
            _insert_workspace(
                connection, observation_workspace, name=f"observation-{observation_id}"
            )
            _insert_campaign(
                connection, campaign_id, DEFAULT_WORKSPACE_ID, name="preflight"
            )
            _insert_run(
                connection,
                run_id,
                run_workspace,
                campaign_id,
                correlation_id="preflight-run",
            )
            _insert_observation(
                connection,
                observation_id,
                run_id,
                observation_workspace,
                query_id="q-preflight",
                correlation_id="preflight-observation",
            )

        with pytest.raises(RuntimeError, match="cross-Workspace") as error:
            command.upgrade(alembic_cfg, "head")
        message = str(error.value)
        assert "2 cross-Workspace" in message
        assert str(campaign_id) in message
        assert str(run_id) in message
        assert str(observation_id) in message

        with engine.connect() as connection:
            run_row = connection.execute(
                text(
                    "SELECT workspace_id, campaign_id FROM discovery_runs "
                    "WHERE id = :id"
                ),
                {"id": str(run_id)},
            ).one()
            observation_row = connection.execute(
                text(
                    "SELECT workspace_id, discovery_run_id "
                    "FROM retrieval_observations WHERE id = :id"
                ),
                {"id": str(observation_id)},
            ).one()
        assert run_row.workspace_id == run_workspace
        assert run_row.campaign_id == campaign_id
        assert observation_row.workspace_id == observation_workspace
        assert observation_row.discovery_run_id == run_id
    finally:
        _finish_legacy_ownership_case(
            migrated_test_database,
            alembic_cfg,
            engine,
            campaign_ids=(campaign_id,),
            run_ids=(run_id,),
            workspace_ids=(run_workspace, observation_workspace),
        )


def test_ownership_migration_rejects_unknown_audit_target_before_ddl(
    migrated_test_database: str,
) -> None:
    """Unknown polymorphic targets abort with the event and target IDs."""
    alembic_cfg = _prepare_legacy_ownership_database(migrated_test_database)
    event_id, target_id = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrated_test_database)
    try:
        with engine.begin() as connection:
            _insert_legacy_audit_event(connection, event_id, "future_target", target_id)

        with pytest.raises(RuntimeError, match="unresolvable audit target") as error:
            command.upgrade(alembic_cfg, "head")
        message = str(error.value)
        assert "1 unknown or unresolvable" in message
        assert str(event_id) in message
        assert str(target_id) in message

        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT count(*) FROM audit_events WHERE id = :id"),
                    {"id": str(event_id)},
                ).scalar_one()
                == 1
            )
    finally:
        _finish_legacy_ownership_case(
            migrated_test_database, alembic_cfg, engine, audit_ids=(event_id,)
        )


def _seed_run_and_observation(connection: Connection) -> tuple[str, str]:
    """Insert one campaign, discovery run, and retrieval observation; return their ids."""
    campaign_id = "00000000-0000-0000-0000-000000000007"
    run_id = "00000000-0000-0000-0000-000000000008"
    observation_id = "00000000-0000-0000-0000-000000000009"
    connection.execute(
        text(
            "INSERT INTO campaigns "
            "(id, workspace_id, name, promotion_posture) "
            "VALUES (:id, :workspace, 'discovery-immutability', 'expertise_first') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": campaign_id, "workspace": str(DEFAULT_WORKSPACE_ID)},
    )
    connection.execute(
        text(
            "INSERT INTO discovery_runs "
            "(id, workspace_id, campaign_id, status, method_plan, correlation_id) "
            "VALUES (:id, :workspace, :campaign, 'succeeded', '{}'::jsonb, 'corr-immutable') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": run_id,
            "workspace": str(DEFAULT_WORKSPACE_ID),
            "campaign": campaign_id,
        },
    )
    connection.execute(
        text(
            "INSERT INTO retrieval_observations "
            "(id, discovery_run_id, workspace_id, query_id, schema_version, capability, "
            "provider_variant, config_sha256, observation_id, status, evidence_directory, "
            "correlation_id) "
            "VALUES (:id, :run, :workspace, 'q-1', 1, 'discovery', 'test-variant', :config, "
            "'obs-1', 'success', '/tmp/evidence/obs-1', 'corr-immutable') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {
            "id": observation_id,
            "run": run_id,
            "workspace": str(DEFAULT_WORKSPACE_ID),
            "config": "a" * 64,
        },
    )
    return run_id, observation_id


def test_retrieval_observations_reject_update_and_delete_at_sql_level(
    migrated_test_database: str,
) -> None:
    engine = create_engine(migrated_test_database)
    with engine.begin() as connection:
        _, observation_id = _seed_run_and_observation(connection)
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("UPDATE retrieval_observations SET status = 'failed' WHERE id = :id"),
            {"id": observation_id},
        )
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text("DELETE FROM retrieval_observations WHERE id = :id"),
            {"id": observation_id},
        )

    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status FROM retrieval_observations WHERE id = :id"),
            {"id": observation_id},
        ).one()

    assert row.status == "success"


def test_truncate_is_rejected_by_guard_trigger(migrated_test_database: str) -> None:
    engine = create_engine(migrated_test_database)
    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(text("TRUNCATE retrieval_observations"))


def test_security_definer_purge_surface_is_gone_at_head(
    migrated_test_database: str,
) -> None:
    """SEC: no callable privileged purge exists in the shipped schema."""
    alembic_cfg = _alembic_config(migrated_test_database)
    command.upgrade(alembic_cfg, "head")

    with create_engine(migrated_test_database).connect() as connection:
        functions = connection.execute(
            text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname = 'aptori_force_drop_observations'"
            )
        ).scalar_one()
    assert functions == 0


def test_failure_class_check_round_trips(migrated_test_database: str) -> None:
    """0009: NULL stays legal for native statuses; junk classes are rejected."""
    alembic_cfg = _alembic_config(migrated_test_database)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(migrated_test_database)

    def _constraint_present() -> bool:
        with engine.connect() as connection:
            names = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conname = "
                        "'ck_retrieval_observations_failure_class_values'"
                    )
                )
            }
        return bool(names)

    assert _constraint_present()

    with engine.begin() as connection:
        _seed_run_and_observation(connection)
    assert observation_count(migrated_test_database) >= 1  # NULL class accepted

    with pytest.raises(DBAPIError), engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO retrieval_observations "
                "(id, discovery_run_id, workspace_id, query_id, schema_version, "
                "capability, provider_variant, config_sha256, observation_id, "
                "status, failure_class, evidence_directory, correlation_id) "
                "VALUES ('00000000-0000-0000-0000-00000000000a', "
                "'00000000-0000-0000-0000-000000000008', :workspace, 'q-bogus', "
                "1, 'discovery', 'test-variant', :config, 'obs-bogus', 'failed', "
                "'totally_made_up_class', '/tmp/evidence/bogus', 'corr-bogus')"
            ),
            {"workspace": str(DEFAULT_WORKSPACE_ID), "config": "b" * 64},
        )

    command.downgrade(alembic_cfg, "0008_observation_vocabulary")
    assert not _constraint_present()

    command.upgrade(alembic_cfg, "head")
    assert _constraint_present()


def test_owner_purge_empties_table_and_restores_triggers(
    migrated_test_database: str,
) -> None:
    """Test cleanup path: owner disables triggers, truncates, re-enables."""
    # Start from a clean table regardless of what earlier tests left behind.
    _purge_observations(migrated_test_database)

    engine = create_engine(migrated_test_database)
    with engine.begin() as connection:
        _seed_run_and_observation(connection)
    assert observation_count(migrated_test_database) == 1

    _purge_observations(migrated_test_database)
    assert observation_count(migrated_test_database) == 0

    # The row triggers are re-enabled after the purge.
    with pytest.raises(DBAPIError), engine.begin() as connection:
        _seed_run_and_observation(connection)
        connection.execute(
            text(
                "UPDATE retrieval_observations SET status = 'failed' "
                "WHERE id = '00000000-0000-0000-0000-000000000009'"
            )
        )


def test_discovery_migration_round_trips_through_previous_revision(
    migrated_test_database: str,
) -> None:
    alembic_cfg = _alembic_config(migrated_test_database)

    # Immutable evidence blocks the downgrade until it is purged.
    with create_engine(migrated_test_database).begin() as connection:
        _seed_run_and_observation(connection)
    assert observation_count(migrated_test_database) >= 1
    with pytest.raises(RuntimeError, match="retrieval_observations"):
        command.downgrade(alembic_cfg, "0005_stable_page_order")

    _purge_observations(migrated_test_database)
    command.downgrade(alembic_cfg, "0005_stable_page_order")

    with create_engine(migrated_test_database).connect() as connection:
        tables = set(inspect(connection).get_table_names())
        assert "discovery_runs" not in tables
        assert "retrieval_observations" not in tables
        triggers_left = connection.execute(
            text(
                "SELECT count(*) FROM pg_trigger "
                "WHERE tgname LIKE '%retrieval_observation%'"
            )
        ).scalar_one()
        functions_left = connection.execute(
            text(
                "SELECT count(*) FROM pg_proc "
                "WHERE proname = 'suppress_retrieval_observation_mutation'"
            )
        ).scalar_one()
        assert triggers_left == 0
        assert functions_left == 0

    command.upgrade(alembic_cfg, "head")

    from alembic.runtime.migration import MigrationContext

    with create_engine(migrated_test_database).connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == HEAD_REVISION
        tables = set(inspect(connection).get_table_names())
        assert {"discovery_runs", "retrieval_observations"} <= tables
