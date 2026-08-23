"""Wire contracts for the discovery-run REST boundary."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

RunStatus = Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]


class DiscoveryRunCreate(BaseModel):
    """Starting a run carries no options today; the body stays closed."""

    model_config = ConfigDict(extra="forbid")


class DiscoveryPlanQuery(BaseModel):
    id: str
    pattern: str | None = None
    query: str
    subreddits: list[str] = []


class DiscoveryMethodPlan(BaseModel):
    """The frozen retrieval contract a run executes against."""

    source: str
    provider_variant: str
    config_sha256: str
    document_sha256: str
    queries: list[DiscoveryPlanQuery]


class DiscoveryRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    campaign_id: UUID
    workspace_id: UUID
    status: RunStatus
    method_plan: DiscoveryMethodPlan
    correlation_id: str
    metrics: dict[str, Any] | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RetrievalObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_id: str
    capability: str
    status: str
    failure_class: str | None
    failure_reason: str | None
    provider_variant: str
    config_sha256: str
    schema_version: int
    candidate_count: int
    candidates: list[Any]
    normalized_sha256: str | None
    elapsed_ms: int | None
    evidence_directory: str
    correlation_id: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ObservationPageResponse(BaseModel):
    items: list[RetrievalObservationResponse]
    next_cursor: str | None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorBody
