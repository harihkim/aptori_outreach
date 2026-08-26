from collections.abc import Callable
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from app.auditing.schemas import AuditEventPageResponse, AuditEventResponse
from app.campaigns import service
from app.campaigns.schemas import (
    CampaignCreate,
    CampaignPageResponse,
    CampaignResponse,
    CampaignUpdate,
    ErrorResponse,
)
from app.deps import PrincipalDep, SessionDep, WorkspaceDep
from app.idempotency import service as idempotency
from app.pagination import InvalidCursor

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    403: {"model": ErrorResponse, "description": "Workspace access denied."},
    503: {"model": ErrorResponse, "description": "API token or workspace unconfigured."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    400: {"model": ErrorResponse, "description": "Invalid idempotency key."},
    409: {"model": ErrorResponse, "description": "Conflicting state or key."},
}
_IDEMPOTENCY_DESCRIPTION = (
    "Unique key for this logical write; retries return its original result."
)

T = TypeVar("T")


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CampaignResponse,
    responses=_WRITE_RESPONSES,
)
def create_campaign(
    payload: CampaignCreate,
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description=_IDEMPOTENCY_DESCRIPTION),
    ] = None,
) -> CampaignResponse | JSONResponse:
    key = _required_key(idempotency_key)
    return _write_response(
        lambda: service.create_campaign(
            session,
            principal,
            workspace.id,
            key,
            payload,
        )
    )


@router.get(
    "",
    response_model=CampaignPageResponse,
    responses={
        **_AUTH_RESPONSES,
        400: {"model": ErrorResponse, "description": "Invalid page cursor."},
    },
)
def list_campaigns(
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> CampaignPageResponse:
    try:
        campaigns, next_cursor = _authorized(
            lambda: service.list_campaigns(
                session,
                principal,
                workspace.id,
                limit=limit,
                cursor=cursor,
            )
        )
    except InvalidCursor:
        raise _invalid_cursor() from None
    return CampaignPageResponse(
        items=[CampaignResponse.model_validate(campaign) for campaign in campaigns],
        next_cursor=next_cursor,
    )


@router.get(
    "/{campaign_id}",
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Campaign not found."},
    },
)
def get_campaign(
    campaign_id: Annotated[UUID, Path()],
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
) -> CampaignResponse:
    try:
        campaign = _authorized(
            lambda: service.get_campaign(
                session, principal, workspace.id, campaign_id
            )
        )
    except service.CampaignNotFound:
        raise _not_found() from None
    return CampaignResponse.model_validate(campaign)


@router.get(
    "/{campaign_id}/audit",
    response_model=AuditEventPageResponse,
    responses={
        **_AUTH_RESPONSES,
        400: {"model": ErrorResponse, "description": "Invalid page cursor."},
        404: {"model": ErrorResponse, "description": "Campaign not found."},
    },
)
def list_campaign_audit(
    campaign_id: Annotated[UUID, Path()],
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> AuditEventPageResponse:
    try:
        events, next_cursor = _authorized(
            lambda: service.list_campaign_audit(
                session,
                principal,
                workspace.id,
                campaign_id,
                limit=limit,
                cursor=cursor,
            )
        )
    except service.CampaignNotFound:
        raise _not_found() from None
    except InvalidCursor:
        raise _invalid_cursor() from None
    return AuditEventPageResponse(
        items=[AuditEventResponse.model_validate(event) for event in events],
        next_cursor=next_cursor,
    )


@router.patch(
    "/{campaign_id}",
    response_model=CampaignResponse,
    responses={
        **_WRITE_RESPONSES,
        404: {"model": ErrorResponse, "description": "Campaign not found."},
    },
)
def update_campaign(
    campaign_id: Annotated[UUID, Path()],
    payload: CampaignUpdate,
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description=_IDEMPOTENCY_DESCRIPTION),
    ] = None,
) -> CampaignResponse | JSONResponse:
    key = _required_key(idempotency_key)
    return _write_response(
        lambda: service.update_campaign(
            session,
            principal,
            workspace.id,
            campaign_id,
            key,
            payload,
        )
    )


def _write_response(
    operation: Callable[[], idempotency.Replay],
) -> CampaignResponse | JSONResponse:
    try:
        result = operation()
    except idempotency.KeyConflictError:
        raise _http_error(
            status.HTTP_409_CONFLICT,
            "idempotency_key_conflict",
            "This key was already used for a different request.",
        ) from None
    except service.WorkspaceAccessDenied:
        raise _forbidden() from None

    if 200 <= result.status_code < 300:
        return CampaignResponse.model_validate(result.body)
    return JSONResponse(status_code=result.status_code, content=result.body)


def _authorized(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except service.WorkspaceAccessDenied:
        raise _forbidden() from None


def _required_key(idempotency_key: str | None) -> str:
    key = (idempotency_key or "").strip()
    if not key:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "idempotency_key_required",
            "Writes require an Idempotency-Key header.",
        )
    if len(key) > 200:
        raise _http_error(
            status.HTTP_400_BAD_REQUEST,
            "idempotency_key_too_long",
            "Idempotency-Key must be at most 200 characters.",
        )
    return key


def _not_found() -> HTTPException:
    return _http_error(
        status.HTTP_404_NOT_FOUND,
        "campaign_not_found",
        "Campaign not found.",
    )


def _forbidden() -> HTTPException:
    return _http_error(
        status.HTTP_403_FORBIDDEN,
        "workspace_forbidden",
        "The authenticated principal cannot access this workspace.",
    )


def _invalid_cursor() -> HTTPException:
    return _http_error(
        status.HTTP_400_BAD_REQUEST,
        "page_cursor_invalid",
        "The page cursor is invalid or belongs to another endpoint.",
    )


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )
