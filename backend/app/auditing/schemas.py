from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor: str
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    correlation_id: str | None
    occurred_at: datetime


class AuditEventPageResponse(BaseModel):
    items: list[AuditEventResponse]
    next_cursor: str | None
