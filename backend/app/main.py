from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.campaigns.router import router as campaigns_router
from app.config import get_settings
from app.db import DatabaseSessionManager
from app.schemas import HealthResponse

DATABASE_UNAVAILABLE_DETAIL = "database unavailable"


def create_app(database_url: str | None = None, api_token: str | None = None) -> FastAPI:
    settings = get_settings()
    manager = DatabaseSessionManager(database_url or settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        await run_in_threadpool(manager.dispose)

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.database = manager
    app.state.api_token = api_token if api_token is not None else settings.api_token
    app.include_router(campaigns_router)

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
