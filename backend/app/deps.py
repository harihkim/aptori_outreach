"""HTTP-layer dependencies: request-scoped session and the default workspace."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
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
