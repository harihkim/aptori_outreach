"""Analysis worker seam: pre-checks, Model Run evidence, scoring, replay."""

import asyncio
import math
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.analysis import runner as analysis_runner
from app.analysis.models import Analysis
from app.analysis.scoring import opportunity_score
from app.campaigns.models import Campaign
from app.conversations.models import Conversation, ConversationVersion
from app.discovery import events as progress_events
from app.llm.models import ModelRun
from app.opportunities.models import Opportunity
from app.workspaces import DEFAULT_WORKSPACE_ID
from tests.test_analysis_task import VALID
from tests.test_worker_runner import (  # noqa: F401
    RecordingEventBus,
    worker_database_url,
    worker_db,
)


def _content(
    created_utc: float | None, *, title: str = "Rotation fails"
) -> dict[str, Any]:
    post: dict[str, Any] = {
        "id": "t3_x",
        "title": title,
        "selftext": "Our gateway rejects rotated tokens.",
        "subreddit": "r/netsec",
        "score": 12,
        "totalReportedComments": 2,
        "permalink": "/r/netsec/comments/x/rotation_fails/",
    }
    if created_utc is not None:
        post["createdUtc"] = created_utc
    return {
        "post": post,
        "comments": [
            {"author": "a", "score": 3, "body": "check JWKS", "visibility": "visible"}
        ],
    }


def seed(
    database_url: str,
    *,
    created_utc: float | None,
    status: str = "active",
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One active Campaign, one Conversation, one Version; returns their ids."""
    engine = create_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            campaign = Campaign(
                workspace_id=DEFAULT_WORKSPACE_ID,
                name=f"analysis-{uuid.uuid4().hex}",
                product_context="Runtime API protection",
                icp="Security engineers",
                keywords=["api security"],
                promotion_posture="expertise_first",
                status=status,
            )
            session.add(campaign)
            session.flush()
            conversation = Conversation(
                workspace_id=DEFAULT_WORKSPACE_ID,
                source_platform="reddit",
                canonical_external_discussion_id=f"t3_{uuid.uuid4().hex[:8]}",
            )
            session.add(conversation)
            session.flush()
            version = ConversationVersion(
                workspace_id=DEFAULT_WORKSPACE_ID,
                conversation_id=conversation.id,
                normalizer_version="reddit-thread/v1",
                normalized_sha256=uuid.uuid4().hex * 2,
                normalized_content_sha256=uuid.uuid4().hex * 2,
                normalized_content=_content(created_utc),
                source_tree_exhausted=True,
            )
            session.add(version)
            session.flush()
            return campaign.id, conversation.id, version.id
    finally:
        engine.dispose()


def add_version(
    database_url: str, conversation_id: uuid.UUID, *, created_utc: float
) -> uuid.UUID:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            version = ConversationVersion(
                workspace_id=DEFAULT_WORKSPACE_ID,
                conversation_id=conversation_id,
                normalizer_version="reddit-thread/v1",
                normalized_sha256=uuid.uuid4().hex * 2,
                normalized_content_sha256=uuid.uuid4().hex * 2,
                normalized_content=_content(created_utc, title="Rotation fails (edit)"),
                source_tree_exhausted=True,
            )
            session.add(version)
            session.flush()
            return version.id
    finally:
        engine.dispose()


def model_returning(args_per_call: list[dict[str, Any]]) -> FunctionModel:
    calls = list(args_per_call)

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        args = calls.pop(0) if calls else args_per_call[-1]
        return ModelResponse(
            parts=[ToolCallPart(tool_name=info.output_tools[0].name, args=args)],
            model_name="analysis-fn",
        )

    return FunctionModel(respond, model_name="analysis-fn")


def invoke(
    campaign_id: uuid.UUID,
    conversation_id: uuid.UUID,
    version_id: uuid.UUID,
) -> str:
    return asyncio.run(
        analysis_runner.run_conversation_analysis(
            None,
            workspace_id=str(DEFAULT_WORKSPACE_ID),
            campaign_id=str(campaign_id),
            conversation_id=str(conversation_id),
            conversation_version_id=str(version_id),
            correlation_id=correlation_for(campaign_id),
        )
    )


def correlation_for(campaign_id: uuid.UUID) -> str:
    """Model Runs carry no Campaign id; the correlation id scopes them per test."""
    return f"corr-{campaign_id}"


def counts(database_url: str, campaign_id: uuid.UUID) -> tuple[int, int, int]:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            analyses = session.scalar(
                select(func.count())
                .select_from(Analysis)
                .where(Analysis.campaign_id == campaign_id)
            )
            opportunities = session.scalar(
                select(func.count())
                .select_from(Opportunity)
                .where(Opportunity.campaign_id == campaign_id)
            )
            runs = session.scalar(
                select(func.count())
                .select_from(ModelRun)
                .where(ModelRun.correlation_id == correlation_for(campaign_id))
            )
            return int(analyses or 0), int(opportunities or 0), int(runs or 0)
    finally:
        engine.dispose()


def load_opportunity(database_url: str, campaign_id: uuid.UUID) -> Opportunity:
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            row = session.scalar(
                select(Opportunity).where(Opportunity.campaign_id == campaign_id)
            )
            assert row is not None
            session.expunge(row)
            return row
    finally:
        engine.dispose()


def analysis_output(**overrides: Any) -> dict[str, Any]:
    return {**VALID, **overrides}


def test_valid_analysis_scores_an_opportunity_and_is_idempotent(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = datetime.now(UTC) - timedelta(hours=24)
    campaign_id, conversation_id, version_id = seed(
        worker_db, created_utc=created.timestamp()
    )
    monkeypatch.setattr(
        analysis_runner, "MODEL_OVERRIDE", model_returning([analysis_output()])
    )
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)

    assert invoke(campaign_id, conversation_id, version_id) == "scored"

    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            analysis = session.scalar(
                select(Analysis).where(Analysis.campaign_id == campaign_id)
            )
            assert analysis is not None
            assert analysis.conversation_version_id == version_id
            assert analysis.analysis_identity == "analyze_conversation@1:2026-09-02.1:1"
            assert analysis.recommended_action == "reply_helpfully"
            assert analysis.factors()["relevance"] == 0.94
            model_run = session.get(ModelRun, analysis.model_run_id)
            assert model_run is not None
            assert model_run.status == "succeeded"
            assert model_run.task_id == "analyze_conversation"
            assert model_run.actual_model == "analysis-fn"
            assert model_run.endpoint_label == "override"
            assert model_run.correlation_id == correlation_for(campaign_id)
            opportunity = session.scalar(
                select(Opportunity).where(Opportunity.campaign_id == campaign_id)
            )
            assert opportunity is not None
            assert opportunity.analysis_id == analysis.id
            assert opportunity.status == "open"
            assert opportunity.formula_version == "v1.0"
            components = opportunity.score_components
            age_hours = components["age_hours"]
            assert isinstance(age_hours, float)
            assert 23.9 < age_hours < 24.2
            expected = opportunity_score(analysis.factors(), age_hours).score
            assert math.isclose(opportunity.opportunity_score, expected, rel_tol=1e-9)
            assert opportunity.post_created_at == created.replace(
                microsecond=created.microsecond
            )
    finally:
        engine.dispose()

    assert [event.type for event in bus.events] == ["analysis.completed"]
    # Without a Discovery Run in hand the Campaign scopes the event.
    assert bus.events[0].run_id == campaign_id
    payload = bus.events[0].payload
    assert payload["conversation_id"] == str(conversation_id)
    assert payload["recommended_action"] == "reply_helpfully"
    assert payload["opportunity_created"] is True
    assert bus.events[0].workspace_id == DEFAULT_WORKSPACE_ID

    # Whole-job replay: no second Analysis, Opportunity, or Model Run.
    assert invoke(campaign_id, conversation_id, version_id) == "already_done"
    assert counts(worker_db, campaign_id) == (1, 1, 1)
    assert len(bus.events) == 1


def test_invalid_model_output_never_creates_authoritative_state(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, conversation_id, version_id = seed(
        worker_db, created_utc=datetime.now(UTC).timestamp()
    )
    monkeypatch.setattr(
        analysis_runner,
        "MODEL_OVERRIDE",
        model_returning([analysis_output(relevance=4.0)]),
    )
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)

    assert invoke(campaign_id, conversation_id, version_id) == "analysis_failed"

    analyses, opportunities, _runs = counts(worker_db, campaign_id)
    assert (analyses, opportunities) == (0, 0)
    engine = create_engine(worker_db)
    try:
        with Session(engine) as session:
            run = session.scalar(
                select(ModelRun)
                .where(ModelRun.correlation_id == correlation_for(campaign_id))
                .order_by(ModelRun.creation_order.desc())
            )
            assert run is not None
            assert run.status == "failed"
            assert run.failure_class == "output_invalid"
    finally:
        engine.dispose()
    assert [event.type for event in bus.events] == ["job.failed"]
    assert bus.events[0].payload["error_class"] == "output_invalid"
    assert bus.events[0].payload["job"] == "conversation_analysis"


def test_inconsistent_factors_are_rejected_before_any_score_exists(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, conversation_id, version_id = seed(
        worker_db, created_utc=datetime.now(UTC).timestamp()
    )
    monkeypatch.setattr(
        analysis_runner,
        "MODEL_OVERRIDE",
        model_returning(
            [
                analysis_output(
                    recommended_action="reply_with_product", promotion_fit=0.1
                )
            ]
        ),
    )
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)

    assert invoke(campaign_id, conversation_id, version_id) == "analysis_failed"

    assert counts(worker_db, campaign_id)[:2] == (0, 0)
    assert bus.events[0].payload["error_class"] == "domain_validation_failed"


def test_missing_post_timestamp_is_unscorable_without_model_spend(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign_id, conversation_id, version_id = seed(worker_db, created_utc=None)
    calls: list[int] = []

    def never(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        calls.append(1)
        raise AssertionError("model must not be called")

    monkeypatch.setattr(analysis_runner, "MODEL_OVERRIDE", FunctionModel(never))
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)

    assert invoke(campaign_id, conversation_id, version_id) == "unscorable"

    assert calls == []
    assert counts(worker_db, campaign_id) == (0, 0, 0)
    assert [event.type for event in bus.events] == ["job.failed"]
    assert bus.events[0].payload["error_class"] == "unscorable"


def test_missing_subject_settles_without_side_effects(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = RecordingEventBus()
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", bus)
    assert invoke(uuid.uuid4(), uuid.uuid4(), uuid.uuid4()) == "missing"
    assert bus.events == []


def test_new_version_rescores_in_place_and_keeps_the_disposition(
    worker_db: str,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = datetime.now(UTC) - timedelta(hours=2)
    campaign_id, conversation_id, version_id = seed(
        worker_db, created_utc=created.timestamp()
    )
    monkeypatch.setattr(
        analysis_runner, "MODEL_OVERRIDE", model_returning([analysis_output()])
    )
    monkeypatch.setattr(progress_events, "DEFAULT_EVENT_BUS", RecordingEventBus())
    assert invoke(campaign_id, conversation_id, version_id) == "scored"
    first = load_opportunity(worker_db, campaign_id)

    engine = create_engine(worker_db)
    try:
        with Session(engine) as session, session.begin():
            row = session.get(Opportunity, first.id)
            assert row is not None
            row.status = "saved"
            row.saved_at = datetime.now(UTC)
    finally:
        engine.dispose()

    second_version = add_version(
        worker_db, conversation_id, created_utc=created.timestamp()
    )
    monkeypatch.setattr(
        analysis_runner,
        "MODEL_OVERRIDE",
        model_returning([analysis_output(relevance=0.2, recommended_action="monitor")]),
    )
    assert invoke(campaign_id, conversation_id, second_version) == "scored"

    second = load_opportunity(worker_db, campaign_id)
    assert second.id == first.id
    assert second.analysis_id != first.analysis_id
    assert second.opportunity_score < first.opportunity_score
    assert second.status == "saved"
    assert counts(worker_db, campaign_id)[:2] == (2, 1)
