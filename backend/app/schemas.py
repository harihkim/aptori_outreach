from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Single health contract for 200 and 503 responses.

    `api` reports whether this service answered; `database` reports the
    canonical state store's reachability. They are independent facts.
    """

    status: Literal["ok", "degraded"]
    api: Literal["reachable"] = "reachable"
    database: Literal["ok", "unavailable"]
    detail: str | None = None
