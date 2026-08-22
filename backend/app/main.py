import logging
from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DatabaseSessionManager
from app.schemas import HealthResponse

logger = logging.getLogger(__name__)


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.state.database = DatabaseSessionManager(database_url or settings.database_url)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse | JSONResponse:
        healthy, failure = app.state.database.probe()
        if not healthy:
            logger.warning("Health probe failed: %s", failure)
            return JSONResponse(
                status_code=503,
                content=HealthResponse(
                    status="degraded",
                    database="unavailable",
                    detail=failure,
                ).model_dump(),
            )
        return HealthResponse(status="ok", database="ok")

    return app


app = create_app()


def get_session(request: Request) -> Iterator[Session]:
    manager: DatabaseSessionManager = request.app.state.database
    yield from manager.session()
