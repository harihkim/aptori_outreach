"""HTTP boundary for discovery runs, observations, and live progress."""

import logging
from collections.abc import AsyncIterator, Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Path, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent

from app.auth import Principal
from app.config import get_settings
from app.deps import PrincipalDep, SessionDep, WorkspaceDep
from app.discovery import events as progress_events
from app.discovery import queue, service
from app.discovery.events import ProgressEvent
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.discovery.schemas import (
    BundleEvidenceResponse,
    DiscoveryMethodPlan,
    DiscoveryRunCreate,
    DiscoveryRunResponse,
    ErrorResponse,
    EvidenceResponse,
    LegacyEvidenceResponse,
    NoEvidenceResponse,
    ObservationPageResponse,
    RetrievalObservationResponse,
)
from app.evidence.models import EvidenceBundle
from app.idempotency import service as idempotency
from app.pagination import InvalidCursor

TERMINAL_RUN_STATUSES = frozenset({"succeeded", "partial", "failed", "cancelled"})
logger = logging.getLogger(__name__)

router = APIRouter(tags=["discovery"])


@dataclass(frozen=True)
class _DiscoveryRunSnapshot:
    """Detached run identity used after the request session is released."""

    id: UUID
    workspace_id: UUID
    correlation_id: str
    status: str
    metrics: dict[str, object] | None


_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    403: {"model": ErrorResponse, "description": "Workspace access denied."},
    503: {
        "model": ErrorResponse,
        "description": "API token or workspace unconfigured.",
    },
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
def _load_default_plan() -> DiscoveryMethodPlan:
    return service.load_frozen_plan(
        get_settings().discovery_query_document_path,
        get_settings().discovery_provider_config_path,
    )


DEFAULT_PLAN_LOADER: service.PlanLoader = _load_default_plan
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
    workspace: WorkspaceDep,
    principal: PrincipalDep,
) -> DiscoveryRunResponse:
    try:
        run = service.get_discovery_run(session, principal, workspace.id, run_id)
    except service.DiscoveryRunNotFound:
        raise _run_not_found() from None
    return DiscoveryRunResponse.model_validate(run)


def _snapshot_run(run: DiscoveryRun) -> _DiscoveryRunSnapshot:
    """Copy only the run fields needed by the long-lived event stream."""
    return _DiscoveryRunSnapshot(
        id=run.id,
        workspace_id=run.workspace_id,
        correlation_id=run.correlation_id,
        status=run.status,
        metrics=deepcopy(run.metrics),
    )


def _load_run_snapshot(
    request: Request, principal: Principal, workspace_id: UUID, run_id: UUID
) -> _DiscoveryRunSnapshot:
    """Read one detached snapshot in an owned, short-lived session."""
    with request.app.state.database.session_factory() as session:
        return _snapshot_run(
            service.get_discovery_run(session, principal, workspace_id, run_id)
        )


def _authenticated_workspace_id(principal: Principal) -> UUID:
    """Return the sole authenticated Workspace without holding a DB session."""
    if len(principal.workspace_ids) != 1:
        # The current bearer-token contract authenticates one default
        # Workspace. A future multi-Workspace token must add an explicit route
        # selector rather than making an SSE URL ambiguous.
        raise _forbidden()
    return next(iter(principal.workspace_ids))


@router.get(
    "/discovery-runs/{run_id}/events",
    response_class=EventSourceResponse,
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Discovery run not found."},
    },
)
async def stream_discovery_events(
    request: Request,
    run_id: Annotated[UUID, Path()],
    principal: PrincipalDep,
) -> AsyncIterator[ServerSentEvent]:
    """Stream authenticated, run-scoped progress until discovery completes.

    Each database snapshot runs in a thread-owned, short-lived session before
    the response waits on the bus. An unknown or foreign run therefore
    receives the same policy-safe 404 as the REST read. Redis is only a
    notification transport: every event is filtered against the authorized
    run and the stream ends on the durable completion event.
    """
    workspace_id = _authenticated_workspace_id(principal)
    try:
        run = await run_in_threadpool(
            _load_run_snapshot, request, principal, workspace_id, run_id
        )
    except service.DiscoveryRunNotFound:
        raise _run_not_found() from None

    if run.status in TERMINAL_RUN_STATUSES:
        # A viewer that connects after completion still gets a finite,
        # self-describing stream rather than waiting forever for pub/sub.
        yield ProgressEvent.create(
            event_type="discovery.completed",
            run_id=run.id,
            workspace_id=run.workspace_id,
            correlation_id=run.correlation_id,
            payload={"status": run.status, "metrics": run.metrics},
        ).as_sse()
        return

    try:
        async for event in progress_events.get_event_bus().subscribe(
            workspace_id, run.id
        ):
            if await request.is_disconnected():
                break
            if event is None:
                # If publication was interrupted after the durable state
                # changed, do not leave a connected viewer stale forever.
                latest = await run_in_threadpool(
                    _load_run_snapshot, request, principal, workspace_id, run.id
                )
                if latest.status in TERMINAL_RUN_STATUSES:
                    yield ProgressEvent.create(
                        event_type="discovery.completed",
                        run_id=latest.id,
                        workspace_id=latest.workspace_id,
                        correlation_id=latest.correlation_id,
                        payload={"status": latest.status, "metrics": latest.metrics},
                    ).as_sse()
                    break
                yield ServerSentEvent(comment="keepalive")
                continue
            # Redis channels are already run-scoped; these checks keep an
            # injected/test bus from becoming an accidental cross-run data path.
            if (
                event.run_id != run.id
                or event.workspace_id != run.workspace_id
                or event.correlation_id != run.correlation_id
            ):
                continue
            yield event.as_sse()
            if event.type == "discovery.completed":
                break
    except Exception:  # noqa: BLE001 - stream failure activates frontend fallback
        logger.warning("discovery progress stream unavailable", exc_info=True)


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
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query()] = None,
) -> ObservationPageResponse:
    try:
        observations, next_cursor = service.list_run_observations(
            session,
            principal,
            workspace.id,
            run_id,
            limit=limit,
            cursor=cursor,
        )
    except service.DiscoveryRunNotFound:
        raise _run_not_found() from None
    except InvalidCursor:
        raise _invalid_cursor() from None
    return ObservationPageResponse(
        items=[
            _observation_response(record.observation, record.bundle)
            for record in observations
        ],
        next_cursor=next_cursor,
    )


def _observation_response(
    observation: RetrievalObservation,
    bundle: EvidenceBundle | None,
) -> RetrievalObservationResponse:
    """Assemble a path-free observation response from workspace-scoped data."""
    if observation.evidence_state == "bundle":
        if bundle is None:
            raise RuntimeError("bundle evidence reference has no matching bundle")
        artifacts = bundle.artifact_manifest.get("artifacts")
        if not isinstance(artifacts, list):
            raise RuntimeError("bundle evidence manifest has no artifact list")
        evidence: EvidenceResponse = BundleEvidenceResponse(
            state="bundle",
            bundle_id=bundle.id,
            bundle_sha256=bundle.bundle_sha256,
            artifact_count=len(artifacts),
        )
    elif observation.evidence_state == "legacy":
        evidence = LegacyEvidenceResponse(state="legacy")
    elif observation.evidence_state == "none":
        evidence = NoEvidenceResponse(state="none")
    else:
        raise RuntimeError("observation carries an unknown evidence state")

    values = {
        field_name: getattr(observation, field_name)
        for field_name in RetrievalObservationResponse.model_fields
        if field_name != "evidence"
    }
    values["evidence"] = evidence
    return RetrievalObservationResponse.model_validate(values)


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
