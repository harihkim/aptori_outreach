"""HTTP-layer dependencies: request-scoped session, workspace, write auth."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import DatabaseSessionManager
from app.workspaces.models import DEFAULT_WORKSPACE_ID, Workspace


def get_session(request: Request) -> Iterator[Session]:
    manager: DatabaseSessionManager = request.app.state.database
    yield from manager.session()


SessionDep = Annotated[Session, Depends(get_session)]


def get_default_workspace(session: SessionDep) -> Workspace:
    """Resolve the single operator workspace, bootstrapping it if absent.

    The domain migration seeds this row; the idempotent insert only matters
    for environments that somehow skipped the seed.
    """
    session.execute(
        insert(Workspace)
        .values(id=DEFAULT_WORKSPACE_ID, name="aptori")
        .on_conflict_do_nothing(index_elements=[Workspace.id])
    )
    workspace = session.scalar(
        select(Workspace).where(Workspace.id == DEFAULT_WORKSPACE_ID)
    )
    if workspace is None:
        raise RuntimeError("default workspace could not be resolved")
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(get_default_workspace)]


def require_write_principal(request: Request) -> str:
    """Authenticate mutating requests with the deployment's bearer token.

    Returns the actor label recorded on audit rows. A single internal token
    authenticates a single internal principal for now; the review/approval
    slice replaces this with per-human identity.
    """
    token = request.app.state.api_token
    if token is None:
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
                "message": "A valid bearer token is required for writes.",
            },
        )
    return "operator"


WritePrincipalDep = Annotated[str, Depends(require_write_principal)]
