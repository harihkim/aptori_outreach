from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, status

from app.campaigns import service
from app.campaigns.models import Campaign
from app.campaigns.schemas import CampaignCreate, CampaignResponse, CampaignUpdate
from app.deps import SessionDep, WorkspaceDep

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreate, session: SessionDep, workspace: WorkspaceDep
) -> CampaignResponse:
    campaign = service.create_campaign(session, workspace.id, payload)
    return CampaignResponse.model_validate(campaign)


@router.get("")
def list_campaigns(
    session: SessionDep, workspace: WorkspaceDep
) -> list[CampaignResponse]:
    return [
        CampaignResponse.model_validate(campaign)
        for campaign in service.list_campaigns(session, workspace.id)
    ]


@router.get("/{campaign_id}")
def get_campaign(
    campaign_id: Annotated[UUID, Path()], session: SessionDep, workspace: WorkspaceDep
) -> CampaignResponse:
    campaign = _get_or_404(session, workspace.id, campaign_id)
    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}")
def update_campaign(
    campaign_id: Annotated[UUID, Path()],
    payload: CampaignUpdate,
    session: SessionDep,
    workspace: WorkspaceDep,
) -> CampaignResponse:
    _get_or_404(session, workspace.id, campaign_id)
    try:
        campaign = service.update_campaign(session, workspace.id, campaign_id, payload)
    except service.CampaignArchivedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "campaign_archived",
                "message": "Archived campaigns are read-only.",
            },
        ) from None
    except service.InvalidCampaignTransitionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "campaign_invalid_transition",
                "message": f"{error.current} -> {error.requested} is not a legal campaign transition.",
            },
        ) from None
    return CampaignResponse.model_validate(campaign)


def _get_or_404(
    session: SessionDep, workspace_id: UUID, campaign_id: UUID
) -> Campaign:
    try:
        return service.get_campaign(session, workspace_id, campaign_id)
    except service.CampaignNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "campaign_not_found", "message": "Campaign not found."},
        ) from None
