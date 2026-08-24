"""Parse frozen Node observation documents into typed domain state.

The retrieval CLI (packages/obscura-retrieval) emits camelCase JSON shaped by
src/discovery.js. Parsing is the boundary where wire data becomes domain data:
unknown schema versions and unknown statuses are rejected rather than coerced,
because unknown evidence must never become valid domain state.
"""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

OBSERVATION_SCHEMA_VERSION = 1

# Wire values emitted by the frozen Node observation document. The database
# CHECK (ck_retrieval_observations_status_values) enforces exactly this set;
# backend-classified outcomes are failure_class values under status='failed',
# never statuses. Tests assert head-schema/ORM/contract parity.
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
    """Typed mirror of the frozen Node observation JSON.

    Every string field carries an explicit bound so a hostile or broken
    provider cannot balloon a database row: oversized values raise
    ValidationError, which the runner classifies as a contract violation
    instead of persisting unbounded wire data.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: int = Field(alias="schemaVersion")
    observation_id: str = Field(alias="observationId", max_length=200)
    capability: str = Field(max_length=64)
    provider_variant: str = Field(alias="providerVariant", max_length=200)
    config_sha256: str = Field(alias="configSha256", max_length=64)
    started_at: str = Field(alias="startedAt", max_length=64)
    completed_at: str = Field(alias="completedAt", max_length=64)
    elapsed_ms: int | None = Field(default=None, alias="elapsedMs")
    status: str = Field(max_length=64)
    failure_reason: str | None = Field(default=None, alias="failureReason", max_length=2000)
    input: dict[str, Any] | None = None
    source_url: str | None = Field(default=None, alias="sourceUrl", max_length=2048)
    final_url: str | None = Field(default=None, alias="finalUrl", max_length=2048)
    response: dict[str, Any] | None = None
    raw_artifact: dict[str, Any] | None = Field(default=None, alias="rawArtifact")
    normalized_sha256: str | None = Field(default=None, alias="normalizedSha256", max_length=64)
    candidate_count: int | None = Field(default=None, alias="candidateCount")
    candidates: list[dict[str, Any]] | None = None
    network: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    evidence_directory: str = Field(alias="evidenceDirectory", max_length=1024)


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


# Persisted-text hygiene. Mirrors packages/obscura-retrieval/src/status.js
# (reimplemented here in Python on purpose: the Node module is frozen and must
# not become an import dependency of the backend).
SENSITIVE_TEXT_PATTERN = re.compile(
    r"((?:solution|js_challenge|token|jsc_orig_r)=)[^&\s:]*",
    re.IGNORECASE,
)
HOME_PATH_PATTERN = re.compile(r"/home/[^/\s:]+")

# Hard cap for anything this helper persists (failure reasons, stderr tails):
# enough for diagnosis, far below anything that could balloon a row.
REDACTED_TEXT_LIMIT = 500


def redact_sensitive_text(value: str) -> str:
    """Mask secrets and local usernames before text reaches the database.

    Query-string values of sensitive keys are replaced with <redacted> exactly
    like the retrieval CLI does, '/home/<user>' collapses to '~', and the
    result is capped at REDACTED_TEXT_LIMIT characters.
    """
    masked = SENSITIVE_TEXT_PATTERN.sub(r"\1<redacted>", value)
    masked = HOME_PATH_PATTERN.sub("~", masked)
    return masked[:REDACTED_TEXT_LIMIT]
