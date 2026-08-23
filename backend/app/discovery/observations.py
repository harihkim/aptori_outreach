"""Parse frozen Node observation documents into typed domain state.

The retrieval CLI (packages/obscura-retrieval) emits camelCase JSON shaped by
src/discovery.js. Parsing is the boundary where wire data becomes domain data:
unknown schema versions and unknown statuses are rejected rather than coerced,
because unknown evidence must never become valid domain state.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

OBSERVATION_SCHEMA_VERSION = 1

# Wire values emitted by the frozen Node observation document. The database
# enforces the same set via ck_retrieval_observations_status_values.
STATUS_VALUES = (
    "success",
    "no_results",
    "incomplete",
    "blocked",
    "rate_limited",
    "auth_required",
    "forbidden",
    "upstream_unavailable",
    "parse_failed",
    "transport_failed",
    "runtime_verification_failed",
    "failed",
)


class UnknownObservationSchemaVersion(ValueError):
    """The document's schemaVersion is not one this backend understands."""


class UnknownObservationStatus(ValueError):
    """The document's status is not a known native status value."""


class ObservationDocument(BaseModel):
    """Typed mirror of the frozen Node observation JSON."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion")
    observation_id: str = Field(alias="observationId")
    capability: str
    provider_variant: str = Field(alias="providerVariant")
    config_sha256: str = Field(alias="configSha256")
    started_at: str = Field(alias="startedAt")
    completed_at: str = Field(alias="completedAt")
    elapsed_ms: int | None = Field(default=None, alias="elapsedMs")
    status: str
    failure_reason: str | None = Field(default=None, alias="failureReason")
    input: dict[str, Any] | None = None
    source_url: str | None = Field(default=None, alias="sourceUrl")
    final_url: str | None = Field(default=None, alias="finalUrl")
    response: dict[str, Any] | None = None
    raw_artifact: dict[str, Any] | None = Field(default=None, alias="rawArtifact")
    normalized_sha256: str | None = Field(default=None, alias="normalizedSha256")
    candidate_count: int | None = Field(default=None, alias="candidateCount")
    candidates: list[dict[str, Any]] | None = None
    network: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    evidence_directory: str = Field(alias="evidenceDirectory")


def parse_observation(raw: dict[str, Any]) -> ObservationDocument:
    """Validate one raw observation dict, rejecting unknown envelope values.

    Schema version is checked first: a document from an unknown schema cannot
    be trusted to mean anything, status included. Status is checked before
    document construction so classification failures stay distinct from
    shape failures.
    """
    version = raw.get("schemaVersion")
    if version != OBSERVATION_SCHEMA_VERSION:
        raise UnknownObservationSchemaVersion(
            f"observation schemaVersion {version!r} is unsupported "
            f"(expected {OBSERVATION_SCHEMA_VERSION})"
        )

    status = raw.get("status")
    if status not in STATUS_VALUES:
        raise UnknownObservationStatus(
            f"observation status {status!r} is not a known native status"
        )

    return ObservationDocument.model_validate(raw)
