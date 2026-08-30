"""Enforce Workspace ownership across relational and audit records.

The legacy schema used globally unique identifiers in single-column foreign
keys.  This revision makes the Workspace part of the relational ownership
contract, and backfills the same authoritative Workspace onto audit events.
Existing data is checked before any DDL or backfill is attempted: a mismatch
or an unresolved polymorphic audit target aborts with the affected IDs.

Revision ID: 0011_workspace_ownership
Revises: 0010_obs_workspace_idx
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = "0011_workspace_ownership"
down_revision = "0010_obs_workspace_idx"
branch_labels = None
depends_on = None


def _preflight_discovery_ownership(bind: Connection) -> None:
    """Collect every cross-Workspace relation before changing any schema."""
    run_campaign_mismatches = list(
        bind.execute(
            sa.text(
                "SELECT run.id AS run_id, run.workspace_id AS run_workspace_id, "
                "campaign.id AS campaign_id, "
                "campaign.workspace_id AS campaign_workspace_id "
                "FROM discovery_runs AS run "
                "JOIN campaigns AS campaign ON campaign.id = run.campaign_id "
                "WHERE run.workspace_id <> campaign.workspace_id "
                "ORDER BY run.id"
            )
        ).mappings()
    )
    observation_run_mismatches = list(
        bind.execute(
            sa.text(
                "SELECT observation.id AS observation_id, "
                "observation.workspace_id AS observation_workspace_id, "
                "run.id AS run_id, run.workspace_id AS run_workspace_id "
                "FROM retrieval_observations AS observation "
                "JOIN discovery_runs AS run "
                "ON run.id = observation.discovery_run_id "
                "WHERE observation.workspace_id <> run.workspace_id "
                "ORDER BY observation.id"
            )
        ).mappings()
    )

    if run_campaign_mismatches or observation_run_mismatches:
        details: list[str] = []
        if run_campaign_mismatches:
            run_details = "; ".join(
                "run {run_id} (Workspace {run_workspace_id}) -> "
                "campaign {campaign_id} (Workspace {campaign_workspace_id})".format(
                    **row
                )
                for row in run_campaign_mismatches
            )
            details.append(
                f"{len(run_campaign_mismatches)} DiscoveryRun/Campaign mismatch(es): "
                f"{run_details}"
            )
        if observation_run_mismatches:
            observation_details = "; ".join(
                "observation {observation_id} (Workspace {observation_workspace_id}) -> "
                "run {run_id} (Workspace {run_workspace_id})".format(**row)
                for row in observation_run_mismatches
            )
            details.append(
                f"{len(observation_run_mismatches)} "
                f"RetrievalObservation/DiscoveryRun mismatch(es): "
                f"{observation_details}"
            )
        raise RuntimeError(
            "refusing 0011_workspace_ownership: found "
            f"{len(run_campaign_mismatches) + len(observation_run_mismatches)} "
            f"cross-Workspace ownership mismatch(es): {'; '.join(details)}"
        )


def _preflight_audit_targets(bind: Connection) -> None:
    unresolved_targets = list(
        bind.execute(
            sa.text(
                "SELECT event.id AS event_id, event.target_type, event.target_id "
                "FROM audit_events AS event "
                "LEFT JOIN campaigns AS campaign "
                "ON event.target_type = 'campaign' "
                "AND campaign.id = event.target_id "
                "LEFT JOIN discovery_runs AS run "
                "ON event.target_type = 'discovery_run' "
                "AND run.id = event.target_id "
                "WHERE (event.target_type = 'campaign' AND campaign.id IS NULL) "
                "OR (event.target_type = 'discovery_run' AND run.id IS NULL) "
                "OR event.target_type NOT IN ('campaign', 'discovery_run') "
                "ORDER BY event.id"
            )
        ).mappings()
    )
    if unresolved_targets:
        details = "; ".join(
            "event {event_id} (target {target_type}:{target_id})".format(**row)
            for row in unresolved_targets
        )
        raise RuntimeError(
            "refusing 0011_workspace_ownership: found "
            f"{len(unresolved_targets)} unknown or unresolvable audit target(s): "
            f"{details}"
        )


def _preflight(bind: Connection) -> None:
    """Reject unsafe legacy rows before changing schema or data."""
    _preflight_discovery_ownership(bind)
    _preflight_audit_targets(bind)


def upgrade() -> None:
    bind = op.get_bind()
    _preflight(bind)

    op.create_unique_constraint(
        "uq_campaigns_workspace_id_id", "campaigns", ["workspace_id", "id"]
    )
    op.create_unique_constraint(
        "uq_discovery_runs_workspace_id_id",
        "discovery_runs",
        ["workspace_id", "id"],
    )
    op.create_unique_constraint(
        "uq_retrieval_observations_workspace_id_id",
        "retrieval_observations",
        ["workspace_id", "id"],
    )

    op.drop_constraint(
        "fk_discovery_runs_campaign_id_campaigns",
        "discovery_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_discovery_runs_workspace_id_campaign_id_campaigns",
        "discovery_runs",
        "campaigns",
        ["workspace_id", "campaign_id"],
        ["workspace_id", "id"],
    )
    op.drop_constraint(
        "fk_retrieval_observations_discovery_run_id_discovery_runs",
        "retrieval_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_retrieval_observations_workspace_id_discovery_run_id_discovery_runs",
        "retrieval_observations",
        "discovery_runs",
        ["workspace_id", "discovery_run_id"],
        ["workspace_id", "id"],
    )

    op.add_column("audit_events", sa.Column("workspace_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE audit_events AS event "
            "SET workspace_id = CASE event.target_type "
            "WHEN 'campaign' THEN ( "
            "SELECT campaign.workspace_id FROM campaigns AS campaign "
            "WHERE campaign.id = event.target_id ) "
            "WHEN 'discovery_run' THEN ( "
            "SELECT run.workspace_id FROM discovery_runs AS run "
            "WHERE run.id = event.target_id ) "
            "END"
        )
    )
    op.alter_column(
        "audit_events",
        "workspace_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_audit_events_workspace_id_workspaces",
        "audit_events",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )
    op.drop_index("ix_audit_events_target_order", table_name="audit_events")
    op.create_index(
        "ix_audit_events_workspace_target_order",
        "audit_events",
        ["workspace_id", "target_type", "target_id", "event_order"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_workspace_target_order", table_name="audit_events")
    op.create_index(
        "ix_audit_events_target_order",
        "audit_events",
        ["target_type", "target_id", "event_order"],
        unique=False,
    )
    op.drop_constraint(
        "fk_audit_events_workspace_id_workspaces",
        "audit_events",
        type_="foreignkey",
    )
    op.drop_column("audit_events", "workspace_id")

    op.drop_constraint(
        "fk_retrieval_observations_workspace_id_discovery_run_id_discovery_runs",
        "retrieval_observations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_retrieval_observations_discovery_run_id_discovery_runs",
        "retrieval_observations",
        "discovery_runs",
        ["discovery_run_id"],
        ["id"],
    )
    op.drop_constraint(
        "fk_discovery_runs_workspace_id_campaign_id_campaigns",
        "discovery_runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_discovery_runs_campaign_id_campaigns",
        "discovery_runs",
        "campaigns",
        ["campaign_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_retrieval_observations_workspace_id_id",
        "retrieval_observations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_discovery_runs_workspace_id_id", "discovery_runs", type_="unique"
    )
    op.drop_constraint("uq_campaigns_workspace_id_id", "campaigns", type_="unique")
