import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.auditing.models import AuditEvent
from app.auditing.service import record_audit
from app.campaigns.models import Campaign
from app.campaigns.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignStatus,
    CampaignUpdate,
)
from app.idempotency import service as idempotency
from app.pagination import decode_cursor, encode_cursor

# DRAFT -> ACTIVE -> PAUSED -> ACTIVE ; ACTIVE|PAUSED -> ARCHIVED
LEGAL_TRANSITIONS: set[tuple[CampaignStatus, CampaignStatus]] = {
    ("draft", "active"),
    ("active", "paused"),
    ("paused", "active"),
    ("active", "archived"),
    ("paused", "archived"),
}


class CampaignNotFound(LookupError):
    """No campaign with that id exists in the caller's workspace."""


class CampaignArchivedError(ValueError):
    """Archived campaigns are terminal; nothing about them may change."""


class InvalidCampaignTransitionError(ValueError):
    def __init__(self, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(f"{current} -> {requested} is not a legal campaign transition")


class WorkspaceAccessDenied(PermissionError):
    """The authenticated principal cannot operate on this workspace."""


def create_campaign(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    key: str,
    payload: CampaignCreate,
) -> idempotency.Replay:
    """Create a Campaign through the authorized, idempotent transaction seam."""
    _require_workspace_access(principal, workspace_id)

    def operation() -> idempotency.Replay:
        campaign = _stage_create_campaign(session, workspace_id, principal.actor, payload)
        return _campaign_result(session, campaign, status_code=201)

    return idempotency.execute(
        session,
        workspace_id=workspace_id,
        key=key,
        method="POST",
        path="/campaigns",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )


def _stage_create_campaign(
    session: Session, workspace_id: uuid.UUID, actor: str, payload: CampaignCreate
) -> Campaign:
    campaign = Campaign(workspace_id=workspace_id, **payload.model_dump())
    session.add(campaign)
    session.flush()
    record_audit(
        session,
        actor=actor,
        action="campaign.created",
        target_type="campaign",
        target_id=campaign.id,
        after={"status": campaign.status},
    )
    return campaign


def get_campaign(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
) -> Campaign:
    _require_workspace_access(principal, workspace_id)
    campaign = session.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.workspace_id == workspace_id
        )
    )
    if campaign is None:
        raise CampaignNotFound(str(campaign_id))
    return campaign


def list_campaigns(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[Campaign], str | None]:
    _require_workspace_access(principal, workspace_id)
    statement = select(Campaign).where(Campaign.workspace_id == workspace_id)
    if cursor is not None:
        statement = statement.where(
            Campaign.creation_order < decode_cursor("campaigns", cursor)
        )
    campaigns = list(
        session.scalars(
            statement.order_by(Campaign.creation_order.desc()).limit(limit + 1)
        )
    )
    page = campaigns[:limit]
    next_cursor = (
        encode_cursor("campaigns", page[-1].creation_order)
        if len(campaigns) > limit
        else None
    )
    return page, next_cursor


def list_campaign_audit(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[AuditEvent], str | None]:
    get_campaign(session, principal, workspace_id, campaign_id)
    statement = select(AuditEvent).where(
        AuditEvent.target_type == "campaign",
        AuditEvent.target_id == campaign_id,
    )
    if cursor is not None:
        statement = statement.where(
            AuditEvent.event_order < decode_cursor("campaign-audit", cursor)
        )
    events = list(
        session.scalars(
            statement.order_by(AuditEvent.event_order.desc()).limit(limit + 1)
        )
    )
    page = events[:limit]
    next_cursor = (
        encode_cursor("campaign-audit", page[-1].event_order)
        if len(events) > limit
        else None
    )
    return page, next_cursor


def _get_campaign_locked(
    session: Session, workspace_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign:
    """Fetch the campaign holding its row lock.

    Serializes concurrent writers: the read blocks on any open row lock and
    then observes the committed state the mutation must validate against,
    so a transition cannot validate against a stale status.
    """
    campaign = session.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
        .with_for_update()
    )
    if campaign is None:
        raise CampaignNotFound(str(campaign_id))
    return campaign


def update_campaign(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    key: str,
    payload: CampaignUpdate,
) -> idempotency.Replay:
    """Update a Campaign through the authorized, idempotent transaction seam."""
    _require_workspace_access(principal, workspace_id)

    def operation() -> idempotency.Replay:
        try:
            campaign = _stage_update_campaign(
                session,
                workspace_id,
                campaign_id,
                principal.actor,
                payload,
            )
        except CampaignNotFound:
            return _error_result(404, "campaign_not_found", "Campaign not found.")
        except CampaignArchivedError:
            return _error_result(
                409, "campaign_archived", "Archived campaigns are read-only."
            )
        except InvalidCampaignTransitionError as error:
            return _error_result(
                409,
                "campaign_invalid_transition",
                f"{error.current} -> {error.requested} is not a legal campaign transition.",
            )
        return _campaign_result(session, campaign, status_code=200)

    return idempotency.execute(
        session,
        workspace_id=workspace_id,
        key=key,
        method="PATCH",
        path=f"/campaigns/{campaign_id}",
        payload=payload.model_dump(mode="json", exclude_unset=True),
        operation=operation,
    )


def _stage_update_campaign(
    session: Session,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    actor: str,
    payload: CampaignUpdate,
) -> Campaign:
    campaign = _get_campaign_locked(session, workspace_id, campaign_id)
    updates: dict[str, Any] = payload.model_dump(exclude_unset=True)
    requested_status = updates.pop("status", None)

    _assert_mutable(campaign, updates, requested_status)
    if requested_status is not None and requested_status != campaign.status:
        _assert_transition(campaign.status, requested_status)

    if updates:
        for field, value in updates.items():
            setattr(campaign, field, value)
        record_audit(
            session,
            actor=actor,
            action="campaign.updated",
            target_type="campaign",
            target_id=campaign.id,
            after={"fields": sorted(updates)},
        )

    if requested_status is not None and requested_status != campaign.status:
        before = campaign.status
        campaign.status = requested_status
        if requested_status == "archived":
            campaign.archived_at = datetime.now(UTC)
        record_audit(
            session,
            actor=actor,
            action="campaign.transitioned",
            target_type="campaign",
            target_id=campaign.id,
            before={"status": before},
            after={"status": requested_status},
        )

    return campaign


def _campaign_result(
    session: Session, campaign: Campaign, *, status_code: int
) -> idempotency.Replay:
    session.flush()
    session.refresh(campaign)
    body = CampaignResponse.model_validate(campaign).model_dump(mode="json")
    return idempotency.Replay(status_code=status_code, body=body)


def _error_result(status_code: int, code: str, message: str) -> idempotency.Replay:
    return idempotency.Replay(
        status_code=status_code,
        body={"detail": {"code": code, "message": message}},
    )


def _require_workspace_access(
    principal: Principal, workspace_id: uuid.UUID
) -> None:
    if not principal.can_access(workspace_id):
        raise WorkspaceAccessDenied(str(workspace_id))


def _assert_mutable(
    campaign: Campaign, updates: dict[str, Any], requested_status: str | None
) -> None:
    # Archived is terminal and read-only: any PATCH carrying intent — field
    # edits or a status value, even the status it already has — is refused.
    if campaign.status == "archived" and (updates or requested_status is not None):
        raise CampaignArchivedError(str(campaign.id))


def _assert_transition(current: str, requested: CampaignStatus) -> None:
    if (current, requested) not in LEGAL_TRANSITIONS:
        raise InvalidCampaignTransitionError(current, requested)
