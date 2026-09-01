"""Wire contracts for the discovery-run REST boundary."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

RunStatus = Literal["queued", "running", "succeeded", "partial", "failed", "cancelled"]

# Canonical backend-classified failure taxonomy; mirrors models.FAILURE_CLASSES
# and contracts/discovery-run-statuses.json 'failureClasses' (parity-tested).
FailureClass = Literal[
    "transport_error",
    "transport_timeout",
    "evidence_unreadable",
    "evidence_unlocated",
    "unknown_observation_schema",
    "unknown_observation_status",
    "contract_violation",
    "runtime_verification_failed",
    "wrapper_error",
]


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


class BundleEvidenceResponse(BaseModel):
    """Public, path-free summary of a portable evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["bundle"]
    bundle_id: UUID
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_count: int = Field(ge=1)


class LegacyEvidenceResponse(BaseModel):
    """Compatibility marker for observations written before bundling."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["legacy"]


class NoEvidenceResponse(BaseModel):
    """Explicit marker for a failed observation with no retained evidence."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["none"]


EvidenceResponse = Annotated[
    BundleEvidenceResponse | LegacyEvidenceResponse | NoEvidenceResponse,
    Field(discriminator="state"),
]


class RetrievalObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    query_id: str
    capability: str
    status: str
    # No bare str passthrough: the wire only carries canonical classes.
    failure_class: FailureClass | None
    failure_reason: str | None
    provider_variant: str
    config_sha256: str
    schema_version: int
    candidate_count: int
    candidates: list[Any]
    normalized_sha256: str | None
    elapsed_ms: int | None
    evidence: EvidenceResponse
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
