import hashlib
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status

from app.campaigns import service
from app.campaigns.schemas import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    ErrorResponse,
)
from app.deps import PrincipalDep, SessionDep, WorkspaceDep, require_principal
from app.idempotency import service as idempotency

router = APIRouter(
    prefix="/campaigns", tags=["campaigns"], dependencies=[Depends(require_principal)]
)

_IDEMPOTENCY_HEADER = {
    "description": "Unique key for this write; replays return the original result."
}

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Malformed write request."},
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    404: {"model": ErrorResponse, "description": "Campaign not found."},
    409: {"model": ErrorResponse, "description": "Conflicting state or key."},
    503: {"model": ErrorResponse, "description": "API token or workspace unconfigured."},
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        **_ERROR_RESPONSES,
        201: {
            "model": CampaignResponse,
            "description": "Created Campaign.",
            "headers": {"Idempotency-Key": _IDEMPOTENCY_HEADER},
        },
    },
)
def create_campaign(
    payload: CampaignCreate,
    session: SessionDep,
    workspace: WorkspaceDep,
    actor: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CampaignResponse:
    key = _required_key(idempotency_key)
    fingerprint = _fingerprint("POST", "/campaigns", payload.model_dump(mode="json"))
    replay = _claim(session, workspace.id, key, fingerprint)
    if replay is not None:
        return _replayed(replay)
    campaign = service.create_campaign(session, workspace.id, actor, payload)
    # Load server-generated values (created_at/updated_at) so the recorded
    # replay body is byte-identical to the live response.
    session.flush()
    session.refresh(campaign)
    body = _campaign_body(campaign)
    idempotency.attach(
        session, workspace_id=workspace.id, key=key, status_code=201, body=body
    )
    session.commit()
    return CampaignResponse.model_validate(campaign)


@router.get("", responses=_ERROR_RESPONSES)
def list_campaigns(
    session: SessionDep, workspace: WorkspaceDep
) -> list[CampaignResponse]:
    return [
        CampaignResponse.model_validate(campaign)
        for campaign in service.list_campaigns(session, workspace.id)
    ]


@router.get("/{campaign_id}", responses=_ERROR_RESPONSES)
def get_campaign(
    campaign_id: Annotated[UUID, Path()], session: SessionDep, workspace: WorkspaceDep
) -> CampaignResponse:
    try:
        campaign = service.get_campaign(session, workspace.id, campaign_id)
    except service.CampaignNotFound:
        raise _not_found() from None
    return CampaignResponse.model_validate(campaign)


@router.patch(
    "/{campaign_id}",
    responses={
        **_ERROR_RESPONSES,
        200: {
            "model": CampaignResponse,
            "description": "Updated Campaign.",
            "headers": {"Idempotency-Key": _IDEMPOTENCY_HEADER},
        },
    },
)
def update_campaign(
    campaign_id: Annotated[UUID, Path()],
    payload: CampaignUpdate,
    session: SessionDep,
    workspace: WorkspaceDep,
    actor: PrincipalDep,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CampaignResponse:
    key = _required_key(idempotency_key)
    fingerprint = _fingerprint(
        "PATCH",
        f"/campaigns/{campaign_id}",
        payload.model_dump(mode="json", exclude_unset=True),
    )
    replay = _claim(session, workspace.id, key, fingerprint)
    if replay is not None:
        return _replayed(replay)
    try:
        campaign = service.update_campaign(
            session, workspace.id, campaign_id, actor, payload
        )
    except service.CampaignNotFound:
        raise _not_found() from None
    except service.CampaignArchivedError:
        raise _http_conflict(
            "campaign_archived", "Archived campaigns are read-only."
        ) from None
    except service.InvalidCampaignTransitionError as error:
        raise _http_conflict(
            "campaign_invalid_transition",
            f"{error.current} -> {error.requested} is not a legal campaign transition.",
        ) from None
    session.flush()
    session.refresh(campaign)
    body = _campaign_body(campaign)
    idempotency.attach(
        session, workspace_id=workspace.id, key=key, status_code=200, body=body
    )
    session.commit()
    return CampaignResponse.model_validate(campaign)


def _campaign_body(campaign: Any) -> dict[str, Any]:
    return CampaignResponse.model_validate(campaign).model_dump(mode="json")


def _replayed(replay: idempotency.Replay) -> CampaignResponse:
    return CampaignResponse.model_validate(replay.body)


def _required_key(idempotency_key: str | None) -> str:
    key = (idempotency_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_error_body(
                "idempotency_key_required",
                "Writes require an Idempotency-Key header.",
            ),
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
        raise _http_conflict(
            "idempotency_key_conflict",
            "This key was already used for a different request.",
        ) from None


def _error_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=_error_body("campaign_not_found", "Campaign not found."),
    )


def _http_conflict(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=_error_body(code, message)
    )
