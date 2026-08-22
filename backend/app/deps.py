"""HTTP-layer dependencies: request-scoped session, workspace, write auth."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import DatabaseSessionManager
from app.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace


def get_session(request: Request) -> Iterator[Session]:
    manager: DatabaseSessionManager = request.app.state.database
    yield from manager.session()


SessionDep = Annotated[Session, Depends(get_session)]


def get_default_workspace(session: SessionDep) -> Workspace:
    """Resolve the migration-seeded operator workspace; read-only.

    The domain migration owns seeding this row. A missing row is a broken
    environment, reported as a fail-closed 503 rather than self-healed by a
    write on every read (which rolled back anyway after GET requests).
    """
    workspace = session.scalar(
        select(Workspace).where(Workspace.id == DEFAULT_WORKSPACE_ID)
    )
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "workspace_unconfigured",
                "message": "The default workspace is missing; run database migrations.",
            },
        )
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_default_workspace)]


def require_principal(request: Request) -> str:
    """Authenticate every request with the deployment's bearer token.

    Returns the actor label recorded on audit rows. A single internal token
    authenticates a single internal principal for now; the review/approval
    slice replaces this with per-human identity.
    """
    token = request.app.state.api_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "api_token_unconfigured",
                "message": "Writes require an API token (APTORI_API_TOKEN) to be configured.",
            },
        )
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthorized",
                "message": "A valid bearer token is required.",
            },
        )
    return "operator"


PrincipalDep = Annotated[str, Depends(require_principal)]
