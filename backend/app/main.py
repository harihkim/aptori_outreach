from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.db import database_ok


def create_app(database_url: str | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.state.database_url = database_url or settings.database_url

    @app.get("/health")
    def health() -> dict[str, str]:
        if not database_ok(app.state.database_url):
            raise HTTPException(
                status_code=503,
                detail={"status": "degraded", "database": "unavailable"},
            )
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
