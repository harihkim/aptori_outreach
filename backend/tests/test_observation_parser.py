"""Observation parsing: frozen Node JSON becomes validated domain state.

Unknown data must never become valid domain state (INV-012 posture): an
unrecognized schemaVersion or status raises instead of being coerced.
"""

import pytest
from pydantic import ValidationError

from app.discovery.observations import (
    OBSERVATION_SCHEMA_VERSION,
    STATUS_VALUES,
    ObservationDocument,
    UnknownObservationSchemaVersion,
    UnknownObservationStatus,
    parse_observation,
)

# The exact wire set enforced by ck_retrieval_observations_status_values.
DB_CHECK_STATUSES = (
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

NATIVE_STATUSES_UNDER_TEST = (
    "success",
    "no_results",
    "blocked",
    "rate_limited",
    "auth_required",
    "forbidden",
    "upstream_unavailable",
    "parse_failed",
    "incomplete",
    "failed",
)


def golden_observation(status: str, **overrides: object) -> dict[str, object]:
    """A success-shaped document matching packages/obscura-retrieval/src/discovery.js."""
    doc: dict[str, object] = {
        "schemaVersion": 1,
        "observationId": "attempt-0001",
        "capability": "discovery",
        "providerVariant": "obscura-duckduckgo-lite",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00.000Z",
        "completedAt": "2026-08-23T00:00:01.250Z",
        "elapsedMs": 1250,
        "status": status,
        "failureReason": None if status == "success" else f"because {status}",
        "input": {
            "id": "q-1",
            "pattern": None,
            "query": "API security",
            "subreddits": ["cybersecurity"],
            "providerQuery": "site:reddit.com/r/cybersecurity/comments API security",
        },
        "sourceUrl": "https://lite.duckduckgo.com/lite/?q=...",
        "finalUrl": "https://lite.duckduckgo.com/lite/?q=...",
        "response": {"navigationStatus": 200},
        "rawArtifact": None,
        "normalizedSha256": "a" * 64,
        "candidateCount": 2,
        "candidates": [
            {"title": "t", "url": "https://reddit.com/r/x", "snippet": "s"}
        ],
        "network": {"requests": 3},
        "runtime": {"node": "20.18.0"},
        "evidenceDirectory": "/evidence-runs/run/attempt-0001",
    }
    doc.update(overrides)
    return doc


def test_schema_version_constant_is_frozen() -> None:
    assert OBSERVATION_SCHEMA_VERSION == 1


def test_status_values_match_the_database_check_exactly() -> None:
    assert STATUS_VALUES == DB_CHECK_STATUSES


@pytest.mark.parametrize("status", NATIVE_STATUSES_UNDER_TEST)
def test_every_native_status_parses(status: str) -> None:
    doc = parse_observation(golden_observation(status))

    assert isinstance(doc, ObservationDocument)
    assert doc.schema_version == OBSERVATION_SCHEMA_VERSION
    assert doc.status == status
    assert doc.observation_id == "attempt-0001"
    assert doc.capability == "discovery"
    assert doc.provider_variant == "obscura-duckduckgo-lite"
    assert doc.config_sha256 == "0" * 64
    assert doc.started_at == "2026-08-23T00:00:00.000Z"
    assert doc.completed_at == "2026-08-23T00:00:01.250Z"
    assert doc.elapsed_ms == 1250
    assert doc.evidence_directory == "/evidence-runs/run/attempt-0001"


def test_success_document_maps_optional_fields() -> None:
    doc = parse_observation(golden_observation("success"))

    assert doc.failure_reason is None
    assert doc.source_url == "https://lite.duckduckgo.com/lite/?q=..."
    assert doc.final_url == "https://lite.duckduckgo.com/lite/?q=..."
    assert doc.response == {"navigationStatus": 200}
    assert doc.normalized_sha256 == "a" * 64
    assert doc.candidate_count == 2
    assert len(doc.candidates or []) == 1
    assert doc.network == {"requests": 3}
    assert doc.runtime == {"node": "20.18.0"}
    assert doc.input is not None
    assert doc.input["id"] == "q-1"


def test_error_shaped_document_without_response_fields_parses() -> None:
    # The Node failure path omits finalUrl/response/rawArtifact/normalized
    # hashes entirely; those stay optional.
    raw = golden_observation("blocked")
    for absent_key in (
        "finalUrl",
        "response",
        "rawArtifact",
        "normalizedSha256",
        "candidateCount",
        "candidates",
    ):
        del raw[absent_key]
    raw["elapsedMs"] = None

    doc = parse_observation(raw)

    assert doc.status == "blocked"
    assert doc.final_url is None
    assert doc.candidate_count is None
    assert doc.elapsed_ms is None
    assert doc.failure_reason == "because blocked"


def test_unknown_fields_are_ignored() -> None:
    raw = golden_observation("success", someFutureField={"nested": True})

    doc = parse_observation(raw)

    assert doc.status == "success"


def test_unknown_schema_version_raises() -> None:
    raw = golden_observation("success", schemaVersion=2)

    with pytest.raises(UnknownObservationSchemaVersion):
        parse_observation(raw)


def test_missing_schema_version_raises() -> None:
    raw = golden_observation("success")
    del raw["schemaVersion"]

    with pytest.raises(UnknownObservationSchemaVersion):
        parse_observation(raw)


def test_unknown_status_raises() -> None:
    raw = golden_observation("kind_of_fine")

    with pytest.raises(UnknownObservationStatus):
        parse_observation(raw)


def test_unknown_status_beats_missing_required_field_ordering() -> None:
    # Status validation happens before document construction, so an unknown
    # status raises UnknownObservationStatus even when other fields are broken.
    raw = golden_observation("kind_of_fine")
    del raw["evidenceDirectory"]

    with pytest.raises(UnknownObservationStatus):
        parse_observation(raw)


def test_missing_evidence_directory_is_a_document_error() -> None:
    raw = golden_observation("success")
    del raw["evidenceDirectory"]

    with pytest.raises(ValidationError):
        parse_observation(raw)


def test_oversized_string_fields_are_document_errors() -> None:
    """Bounded fields keep hostile or broken providers from ballooning rows."""
    oversized_observation_id = golden_observation("success", observationId="x" * 201)
    with pytest.raises(ValidationError):
        parse_observation(oversized_observation_id)

    oversized_url = golden_observation("success", sourceUrl="https://x.test/?q=" + "y" * 3000)
    with pytest.raises(ValidationError):
        parse_observation(oversized_url)

    oversized_reason = golden_observation("blocked", failureReason="f" * 2001)
    with pytest.raises(ValidationError):
        parse_observation(oversized_reason)

    oversized_evidence = golden_observation("success", evidenceDirectory="/e" * 513)
    with pytest.raises(ValidationError):
        parse_observation(oversized_evidence)

    oversized_variant = golden_observation("success", providerVariant="v" * 201)
    with pytest.raises(ValidationError):
        parse_observation(oversized_variant)

    oversized_sha = golden_observation("success", configSha256="a" * 65)
    with pytest.raises(ValidationError):
        parse_observation(oversized_sha)


def test_field_bounds_accept_values_at_the_limit() -> None:
    raw = golden_observation(
        "success",
        observationId="x" * 200,
        sourceUrl="https://x.test/" + "y" * 2033,
        evidenceDirectory="/e" * 512,
        providerVariant="v" * 200,
    )

    doc = parse_observation(raw)

    assert len(doc.observation_id) == 200
    assert len(doc.evidence_directory) == 1024


def test_redact_sensitive_text_masks_secrets_and_home_paths() -> None:
    from app.discovery.observations import REDACTED_TEXT_LIMIT, redact_sensitive_text

    masked = redact_sensitive_text(
        "GET https://x.test/?jsc_orig_r=supersecret&ok=1 from /home/hari/evidence failed"
    )
    assert "supersecret" not in masked
    assert "jsc_orig_r=<redacted>" in masked
    assert "/home/hari" not in masked
    assert "~/evidence" in masked
    assert "ok=1" in masked

    for key in ("solution", "js_challenge", "token", "jsc_orig_r"):
        assert f"{key}=SECRET" not in redact_sensitive_text(f"{key}=SECRET")

    capped = redact_sensitive_text("z" * (REDACTED_TEXT_LIMIT + 500))
    assert len(capped) == REDACTED_TEXT_LIMIT
