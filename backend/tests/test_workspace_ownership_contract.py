"""Workspace ownership contracts shared by ORM, audit, and idempotency code."""

import uuid
from typing import Any, cast

from sqlalchemy import ForeignKeyConstraint, Table, UniqueConstraint
from sqlalchemy.orm import Session

from app.auditing.models import AuditEvent
from app.auditing.service import record_audit
from app.campaigns.models import Campaign
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.idempotency.models import IdempotencyEvent


def _unique_constraint(model: Any, name: str) -> UniqueConstraint:
    constraint = next(
        constraint
        for constraint in _table(model).constraints
        if isinstance(constraint, UniqueConstraint) and constraint.name == name
    )
    return constraint


def _foreign_key_constraint(model: Any, name: str) -> ForeignKeyConstraint:
    constraint = next(
        constraint
        for constraint in _table(model).constraints
        if isinstance(constraint, ForeignKeyConstraint) and constraint.name == name
    )
    return constraint


def _table(model: Any) -> Table:
    return cast(Table, model.__table__)


def test_domain_rows_expose_workspace_candidate_keys() -> None:
    expected = ("workspace_id", "id")
    assert (
        tuple(
            _unique_constraint(Campaign, "uq_campaigns_workspace_id_id").columns.keys()
        )
        == expected
    )
    assert (
        tuple(
            _unique_constraint(
                DiscoveryRun, "uq_discovery_runs_workspace_id_id"
            ).columns.keys()
        )
        == expected
    )
    assert (
        tuple(
            _unique_constraint(
                RetrievalObservation, "uq_retrieval_observations_workspace_id_id"
            ).columns.keys()
        )
        == expected
    )


def test_child_rows_use_workspace_scoped_foreign_keys() -> None:
    run_fk = _foreign_key_constraint(
        DiscoveryRun, "fk_discovery_runs_workspace_id_campaign_id_campaigns"
    )
    assert tuple(run_fk.columns.keys()) == ("workspace_id", "campaign_id")
    assert tuple(element.target_fullname for element in run_fk.elements) == (
        "campaigns.workspace_id",
        "campaigns.id",
    )

    observation_fk = _foreign_key_constraint(
        RetrievalObservation,
        "fk_retrieval_observations_workspace_id_discovery_run_id_discovery_runs",
    )
    assert tuple(observation_fk.columns.keys()) == (
        "workspace_id",
        "discovery_run_id",
    )
    assert tuple(element.target_fullname for element in observation_fk.elements) == (
        "discovery_runs.workspace_id",
        "discovery_runs.id",
    )


def test_child_identifiers_have_no_unscoped_foreign_keys() -> None:
    """A parent ID alone must never bypass the Workspace ownership key."""
    run_ownership_fks = [
        constraint
        for constraint in _table(DiscoveryRun).foreign_key_constraints
        if "campaign_id" in constraint.column_keys
    ]
    assert [tuple(constraint.column_keys) for constraint in run_ownership_fks] == [
        ("workspace_id", "campaign_id")
    ]
    observation_ownership_fks = [
        constraint
        for constraint in _table(RetrievalObservation).foreign_key_constraints
        if "discovery_run_id" in constraint.column_keys
    ]
    assert [
        tuple(constraint.column_keys) for constraint in observation_ownership_fks
    ] == [("workspace_id", "discovery_run_id")]


def test_audit_and_idempotency_keep_workspace_scoped_contracts() -> None:
    audit_workspace_fk = _foreign_key_constraint(
        AuditEvent, "fk_audit_events_workspace_id_workspaces"
    )
    assert tuple(audit_workspace_fk.columns.keys()) == ("workspace_id",)
    assert tuple(
        element.target_fullname for element in audit_workspace_fk.elements
    ) == ("workspaces.id",)
    assert _table(AuditEvent).c["workspace_id"].nullable is False
    audit_index = next(
        index
        for index in _table(AuditEvent).indexes
        if index.name == "ix_audit_events_workspace_target_order"
    )
    assert tuple(column.name for column in audit_index.columns) == (
        "workspace_id",
        "target_type",
        "target_id",
        "event_order",
    )

    idempotency_key = _unique_constraint(
        IdempotencyEvent, "uq_idempotency_events_workspace_key"
    )
    assert tuple(idempotency_key.columns.keys()) == ("workspace_id", "key")
    idempotency_workspace_fk = next(
        constraint
        for constraint in _table(IdempotencyEvent).constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and constraint.name == "fk_idempotency_events_workspace_id_workspaces"
    )
    assert tuple(
        element.target_fullname for element in idempotency_workspace_fk.elements
    ) == ("workspaces.id",)


def test_record_audit_carries_the_authoritative_workspace() -> None:
    workspace_id = uuid.uuid4()
    session = Session()
    try:
        record_audit(
            session,
            actor="test",
            action="campaign.created",
            target_type="campaign",
            target_id=uuid.uuid4(),
            workspace_id=workspace_id,
        )
        event = next(iter(session.new))
        assert isinstance(event, AuditEvent)
        assert event.workspace_id == workspace_id
    finally:
        session.close()
