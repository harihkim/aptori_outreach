from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.campaigns.router import router as campaigns_router
from app.config import get_settings
from app.db import DatabaseSessionManager
from app.discovery.router import router as discovery_router
from app.opportunities.router import router as opportunities_router
from app.schemas import HealthResponse

DATABASE_UNAVAILABLE_DETAIL = "database unavailable"


class _UnsetApiToken:
    """Sentinel that distinguishes omitted configuration from explicit None."""


_UNSET_API_TOKEN = _UnsetApiToken()


def create_app(
    database_url: str | None = None,
    api_token: str | None | _UnsetApiToken = _UNSET_API_TOKEN,
) -> FastAPI:
    settings = get_settings()
    manager = DatabaseSessionManager(
        database_url or settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await run_in_threadpool(manager.dispose)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.database = manager
    app.state.api_token = (
        settings.api_token if isinstance(api_token, _UnsetApiToken) else api_token
    )
    app.include_router(campaigns_router)
    app.include_router(discovery_router)
    app.include_router(opportunities_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={
            503: {
                "model": HealthResponse,
                "description": "Degraded: the API answered but the database is unavailable.",
            }
        },
    )
    def health() -> HealthResponse | JSONResponse:
        healthy, _diagnostic = manager.probe()
        if not healthy:
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="degraded",
                    database="unavailable",
                    detail=DATABASE_UNAVAILABLE_DETAIL,
                ).model_dump(),
            )
        return HealthResponse(status="ok", database="ok")

    return app


app = create_app()
