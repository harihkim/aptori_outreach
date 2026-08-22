import hashlib
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse

from app.campaigns import service
from app.campaigns.schemas import CampaignCreate, CampaignResponse, CampaignUpdate
from app.deps import SessionDep, WorkspaceDep, WritePrincipalDep
from app.idempotency import service as idempotency

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_campaign(
    request: Request,
    payload: CampaignCreate,
    session: SessionDep,
    workspace: WorkspaceDep,
    actor: WritePrincipalDep,
) -> JSONResponse:
    key = _require_idempotency_key(request)
    fingerprint = _fingerprint("POST", "/campaigns", payload.model_dump(mode="json"))
    replay = _claim(session, workspace.id, key, fingerprint)
    if replay is not None:
        return JSONResponse(replay.body, status_code=replay.status_code)
    try:
        campaign = service.create_campaign(session, workspace.id, actor, payload)
        code, body = status.HTTP_201_CREATED, _campaign_body(campaign)
    except HTTPException as error:
        code, body = error.status_code, {"detail": error.detail}
    _record(session, workspace.id, key, code, body)
    return JSONResponse(body, status_code=code)


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
    try:
        campaign = service.get_campaign(session, workspace.id, campaign_id)
    except service.CampaignNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "campaign_not_found", "message": "Campaign not found."},
        ) from None
    return CampaignResponse.model_validate(campaign)


@router.patch("/{campaign_id}")
def update_campaign(
    request: Request,
    campaign_id: Annotated[UUID, Path()],
    payload: CampaignUpdate,
    session: SessionDep,
    workspace: WorkspaceDep,
    actor: WritePrincipalDep,
) -> JSONResponse:
    key = _require_idempotency_key(request)
    fingerprint = _fingerprint(
        "PATCH",
        f"/campaigns/{campaign_id}",
        payload.model_dump(mode="json", exclude_unset=True),
    )
    replay = _claim(session, workspace.id, key, fingerprint)
    if replay is not None:
        return JSONResponse(replay.body, status_code=replay.status_code)
    try:
        campaign = service.update_campaign(
            session, workspace.id, campaign_id, actor, payload
        )
        code, body = status.HTTP_200_OK, _campaign_body(campaign)
    except service.CampaignNotFound:
        code, body = status.HTTP_404_NOT_FOUND, {
            "detail": {"code": "campaign_not_found", "message": "Campaign not found."}
        }
    except service.CampaignArchivedError:
        code, body = status.HTTP_409_CONFLICT, {
            "detail": {
                "code": "campaign_archived",
                "message": "Archived campaigns are read-only.",
            }
        }
    except service.InvalidCampaignTransitionError as error:
        code, body = status.HTTP_409_CONFLICT, {
            "detail": {
                "code": "campaign_invalid_transition",
                "message": f"{error.current} -> {error.requested} is not a legal campaign transition.",
            }
        }
    _record(session, workspace.id, key, code, body)
    return JSONResponse(body, status_code=code)


def _campaign_body(campaign: Any) -> dict[str, Any]:
    return CampaignResponse.model_validate(campaign).model_dump(mode="json")


def _require_idempotency_key(request: Request) -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "idempotency_key_required",
                "message": "Writes require an Idempotency-Key header.",
            },
        )
    return key[:200]


def _fingerprint(method: str, path: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{method} {path} {canonical}".encode()).hexdigest()


def _claim(
    session: SessionDep, workspace_id: UUID, key: str, fingerprint: str
) -> idempotency.Replay | None:
    try:
        return idempotency.claim(
            session,
            workspace_id=workspace_id,
            key=key,
            request_fingerprint=fingerprint,
        )
    except idempotency.KeyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_key_conflict",
                "message": "This key was already used for a different request.",
            },
        ) from None
    except idempotency.KeyInProgressError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "idempotency_key_in_progress",
                "message": "This key's original request has not finished; retry shortly.",
            },
        ) from None


def _record(
    session: SessionDep,
    workspace_id: UUID,
    key: str,
    code: int,
    body: dict[str, Any],
) -> None:
    idempotency.record(
        session,
        workspace_id=workspace_id,
        key=key,
        status_code=code,
        body=body,
    )
