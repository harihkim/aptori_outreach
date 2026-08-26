"""HTTP boundary for discovery runs and their observations."""

from collections.abc import Callable
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Query, status
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.deps import PrincipalDep, SessionDep, WorkspaceDep
from app.discovery import queue, service
from app.discovery.schemas import (
    DiscoveryRunCreate,
    DiscoveryRunResponse,
    ErrorResponse,
    ObservationPageResponse,
    RetrievalObservationResponse,
)
from app.idempotency import service as idempotency
from app.pagination import InvalidCursor

router = APIRouter(tags=["discovery"])

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    403: {"model": ErrorResponse, "description": "Workspace access denied."},
    503: {"model": ErrorResponse, "description": "API token or workspace unconfigured."},
}
_WRITE_RESPONSES: dict[int | str, dict[str, Any]] = {
    **_AUTH_RESPONSES,
    400: {"model": ErrorResponse, "description": "Invalid idempotency key."},
    409: {"model": ErrorResponse, "description": "Conflicting state or key."},
    503: {
        **_AUTH_RESPONSES[503],
        "description": "Worker queue or retrieval inputs unavailable.",
    },
}
_IDEMPOTENCY_DESCRIPTION = (
    "Unique key for this logical write; retries return its original result."
)

# Overridable defaults so tests can inject fakes without Redis or frozen files.
DEFAULT_PLAN_LOADER: service.PlanLoader = (
    lambda: service.load_frozen_plan(
        get_settings().discovery_query_document_path,
        get_settings().discovery_provider_config_path,
    )
)
DEFAULT_ENQUEUE: service.Enqueue = queue.enqueue_discovery_queries

T = TypeVar("T")


@router.post(
    "/campaigns/{campaign_id}/discovery-runs",
    status_code=status.HTTP_201_CREATED,
    response_model=DiscoveryRunResponse,
    responses=_WRITE_RESPONSES,
)
def start_discovery_run(
    campaign_id: Annotated[UUID, Path()],
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    payload: DiscoveryRunCreate | None = None,
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key", description=_IDEMPOTENCY_DESCRIPTION),
    ] = None,
) -> DiscoveryRunResponse | JSONResponse:
    del payload  # Starting a run carries no options today.
    key = _required_key(idempotency_key)
    return _write_response(
        lambda: service.start_discovery_run(
            session,
            principal,
            workspace.id,
            campaign_id,
            key,
            plan_loader=DEFAULT_PLAN_LOADER,
            enqueue=DEFAULT_ENQUEUE,
        )
    )


@router.get(
    "/discovery-runs/{run_id}",
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Discovery run not found."},
    },
)
def get_discovery_run(
    run_id: Annotated[UUID, Path()],
    session: SessionDep,
    principal: PrincipalDep,
) -> DiscoveryRunResponse:
    try:
        run = service.get_discovery_run(session, principal, run_id)
    except service.DiscoveryRunNotFound:
        raise _run_not_found() from None
    return DiscoveryRunResponse.model_validate(run)


@router.get(
    "/discovery-runs/{run_id}/observations",
    response_model=ObservationPageResponse,
    responses={
        **_AUTH_RESPONSES,
        400: {"model": ErrorResponse, "description": "Invalid page cursor."},
        404: {"model": ErrorResponse, "description": "Discovery run not found."},
    },
)
def list_run_observations(
    run_id: Annotated[UUID, Path()],
    session: SessionDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> ObservationPageResponse:
    try:
        observations, next_cursor = service.list_run_observations(
            session, principal, run_id, limit=limit, cursor=cursor
        )
    except service.DiscoveryRunNotFound:
        raise _run_not_found() from None
    except InvalidCursor:
        raise _invalid_cursor() from None
    return ObservationPageResponse(
        items=[
            RetrievalObservationResponse.model_validate(observation)
            for observation in observations
        ],
        next_cursor=next_cursor,
    )


def _write_response(
    operation: Callable[[], idempotency.Replay],
) -> DiscoveryRunResponse | JSONResponse:
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
    except service.RetrievalInputsInvalid as error:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "retrieval_inputs_unavailable",
            f"Frozen retrieval inputs are unavailable: {error}",
        ) from None
    except service.WorkerQueueUnavailable as error:
        raise _http_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "worker_queue_unavailable",
            str(error),
        ) from None

    if 200 <= result.status_code < 300:
        return DiscoveryRunResponse.model_validate(result.body)
    return JSONResponse(status_code=result.status_code, content=result.body)


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


def _run_not_found() -> HTTPException:
    return _http_error(
        status.HTTP_404_NOT_FOUND,
        "discovery_run_not_found",
        "Discovery run not found.",
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
