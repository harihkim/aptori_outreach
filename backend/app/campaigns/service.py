import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditing.service import record_audit
from app.campaigns.models import Campaign
from app.campaigns.schemas import CampaignCreate, CampaignStatus, CampaignUpdate

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


def create_campaign(
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
    session.commit()
    return campaign


def get_campaign(
    session: Session, workspace_id: uuid.UUID, campaign_id: uuid.UUID
) -> Campaign:
    campaign = session.scalar(
        select(Campaign).where(
            Campaign.id == campaign_id, Campaign.workspace_id == workspace_id
        )
    )
    if campaign is None:
        raise CampaignNotFound(str(campaign_id))
    return campaign


def list_campaigns(session: Session, workspace_id: uuid.UUID) -> list[Campaign]:
    campaigns = session.scalars(
        select(Campaign)
        .where(Campaign.workspace_id == workspace_id)
        .order_by(Campaign.created_at.desc(), Campaign.id)
    )
    return list(campaigns)


def get_campaign_locked(
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
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    actor: str,
    payload: CampaignUpdate,
) -> Campaign:
    campaign = get_campaign_locked(session, workspace_id, campaign_id)
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

    session.commit()
    return campaign


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
