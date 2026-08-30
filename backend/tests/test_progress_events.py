"""Progress-event contract and FastAPI SSE boundary tests."""

import json
import uuid

from app.discovery.events import EVENT_TYPES, ProgressEvent


def event(
    run_id: uuid.UUID, event_type: str, payload: dict[str, object]
) -> ProgressEvent:
    return ProgressEvent.create(
        event_type=event_type,
        run_id=run_id,
        workspace_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        correlation_id="corr-event-test",
        payload=payload,
    )


def test_progress_event_json_is_a_correlated_sse_envelope() -> None:
    run_id = uuid.uuid4()
    progress = event(run_id, "discovery.candidate_found", {"query_id": "q-a"})

    encoded = json.loads(progress.model_dump_json())

    assert encoded["type"] == "discovery.candidate_found"
    assert encoded["run_id"] == str(run_id)
    assert encoded["workspace_id"] == "00000000-0000-0000-0000-000000000001"
    assert encoded["correlation_id"] == "corr-event-test"
    assert encoded["payload"] == {"query_id": "q-a"}


def test_event_type_catalog_includes_the_discovery_vertical_slice() -> None:
    assert EVENT_TYPES[:4] == (
        "discovery.started",
        "discovery.candidate_found",
        "retrieval.observed",
        "discovery.completed",
    )
