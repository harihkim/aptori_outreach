"""HTTP-layer dependencies: request-scoped session, principal, and workspace."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.db import DatabaseSessionManager
from app.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace


def get_session(request: Request) -> Iterator[Session]:
    manager: DatabaseSessionManager = request.app.state.database
    yield from manager.session()


SessionDep = Annotated[Session, Depends(get_session)]


_bearer = HTTPBearer(auto_error=False)


def require_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ],
) -> Principal:
    """Authenticate a request as the deployment's internal operator."""
    token = request.app.state.api_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "api_token_unconfigured",
                "message": "An API token (APTORI_API_TOKEN) must be configured.",
            },
        )
    if credentials is None or not hmac.compare_digest(credentials.credentials, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "unauthorized",
                "message": "A valid bearer token is required.",
            },
        )
    return Principal(actor="operator", workspace_ids=frozenset({DEFAULT_WORKSPACE_ID}))


PrincipalDep = Annotated[Principal, Depends(require_principal)]


def get_default_workspace(session: SessionDep, principal: PrincipalDep) -> Workspace:
    """Resolve the migration-seeded operator workspace; read-only.

    The domain migration owns seeding this row. A missing row is a broken
    environment, reported as a fail-closed 503 rather than self-healed by a
    write on every read (which rolled back anyway after GET requests).
    """
    if not principal.can_access(DEFAULT_WORKSPACE_ID):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "workspace_forbidden",
                "message": "The authenticated principal cannot access this workspace.",
            },
        )

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
