"""Opportunity Inbox API over Analyses produced by the worker seam."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analysis import runner as analysis_runner
from app.conversations.models import Conversation
from app.discovery import events as progress_events
from app.main import create_app
from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.test_analysis_runner import (
    add_version,
    analysis_output,
    invoke,
    model_returning,
    seed,
)
from tests.test_analysis_task import VALID
from tests.test_worker_runner import (  # noqa: F401
    RecordingEventBus,
    worker_database_url,
    worker_db,
)

API_TOKEN = "analysis-token"


@pytest.fixture()
def api(worker_db: str) -> Iterator[TestClient]:  # noqa: F811
    app = create_app(database_url=worker_db, api_token=API_TOKEN)
    with TestClient(app, headers={"Authorization": f"Bearer {API_TOKEN}"}) as client:
        yield client


def test_inbox_api_ranks_explains_and_scopes_opportunities(
    worker_db: str,  # noqa: F811
    api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    campaign_id, conversation_a, version_a = seed(
        worker_db, created_utc=(now - timedelta(hours=1)).timestamp()
    )
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", RecordingEventBus())
    monkeypatch.setattr(
        analysis_runner, "MODEL_OVERRIDE", model_returning([analysis_output()])
    )
    assert invoke(campaign_id, conversation_a, version_a) == "scored"

    # A weaker, older thread in the same Campaign ranks below.
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session, session.begin():
            conversation = Conversation(
                workspace_id=DEFAULT_WORKSPACE_ID,
                source_platform="reddit",
                canonical_external_discussion_id=f"t3_{uuid.uuid4().hex[:8]}",
            )
            session.add(conversation)
            session.flush()
            conversation_b = conversation.id
    finally:
        engine.dispose()
    version_b = add_version(
        worker_db, conversation_b, created_utc=(now - timedelta(hours=100)).timestamp()
    )
    monkeypatch.setattr(
        analysis_runner,
        "MODEL_OVERRIDE",
        model_returning([analysis_output(relevance=0.3, recommended_action="monitor")]),
    )
    assert invoke(campaign_id, conversation_b, version_b) == "scored"

    listing = api.get(f"/opportunities?campaign_id={campaign_id}")
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert [item["conversation_id"] for item in items] == [
        str(conversation_a),
        str(conversation_b),
    ]
    assert items[0]["opportunity_score"] > items[1]["opportunity_score"]
    top = items[0]
    assert top["status"] == "open"
    assert top["formula_version"] == "v1.0"
    assert set(top["analysis"]["factors"]) == {
        "relevance",
        "pain_intensity",
        "buying_intent",
        "replyability",
        "product_fit",
        "promotion_fit",
        "confidence",
    }
    assert top["analysis"]["recommended_action"] == "reply_helpfully"
    assert top["analysis"]["rationale"] == VALID["rationale"]
    assert top["conversation"]["title"] == "Rotation fails"
    assert top["conversation"]["subreddit"] == "r/netsec"
    assert top["conversation"]["url"] == (
        "https://www.reddit.com/r/netsec/comments/x/rotation_fails/"
    )
    assert top["model_run"]["task_id"] == "analyze_conversation"
    assert top["model_run"]["actual_model"] == "analysis-fn"
    assert top["model_run"]["cost_status"] == "unpriced"
    assert "api_key" not in listing.text
    assert "selftext" not in listing.text
    assert top["score_components"]["weights"]["relevance"] == 0.375

    detail = api.get(f"/opportunities/{top['id']}")
    assert detail.status_code == 200
    assert detail.json() == top

    assert api.get(f"/opportunities/{uuid.uuid4()}").status_code == 404
    assert api.get(f"/opportunities?campaign_id={campaign_id}&status=saved").json() == {
        "items": []
    }
    assert api.get("/opportunities?status=bogus").status_code == 422
    assert (
        api.get("/opportunities", headers={"Authorization": "Bearer nope"}).status_code
        == 401
    )
