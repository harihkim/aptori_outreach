"""arq job: analyze one Conversation Version for one Campaign, then score it.

Ordering is the contract:

1. cheap deterministic pre-checks (ownership, replay, a usable post time)
   run before any model spend;
2. the LLM Task runs and its Model Run is committed whether or not it
   succeeded, so spend and failure classes are auditable;
3. only a schema-valid, domain-valid output creates an Analysis and scores
   an Opportunity, in one transaction, under a unique identity that makes
   whole-job replay a no-op.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic_ai.models import Model
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.analysis import task as analysis_task
from app.analysis.models import Analysis
from app.analysis.scoring import ScoringInputError, opportunity_score
from app.campaigns.models import Campaign
from app.config import get_settings
from app.conversations.models import Conversation, ConversationVersion
from app.db import DatabaseSessionManager
from app.discovery import events as progress_events
from app.discovery.events import ProgressEvent
from app.llm.runner import LLMTaskRunner
from app.opportunities.models import Opportunity

logger = logging.getLogger(__name__)

# Test seam: a TestModel/FunctionModel installed here replaces configuration
# routing for every run in-process. Production never sets it.
MODEL_OVERRIDE: Model | None = None


@dataclass(frozen=True, slots=True)
class _Subject:
    campaign: Campaign
    conversation: Conversation
    version: ConversationVersion


@dataclass(frozen=True, slots=True)
class _Scored:
    analysis_id: uuid.UUID
    opportunity_id: uuid.UUID
    score: float
    recommended_action: str
    created: bool


def _campaign_context(campaign: Campaign) -> dict[str, Any]:
    return {
        "name": campaign.name,
        "product_context": campaign.product_context,
        "icp": campaign.icp,
        "keywords": list(campaign.keywords),
        "competitors": list(campaign.competitors),
        "promotion_posture": campaign.promotion_posture,
        "approved_claims": list(campaign.approved_claims),
        "prohibited_claims": list(campaign.prohibited_claims),
    }


def post_created_at(content: dict[str, Any]) -> datetime | None:
    """The Deterministic Signal freshness decays from; None when unusable."""
    post = content.get("post")
    if not isinstance(post, dict):
        return None
    value = post.get("createdUtc")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _load_subject(
    manager: DatabaseSessionManager,
    workspace_id: uuid.UUID,
    campaign_id: uuid.UUID,
    conversation_id: uuid.UUID,
    version_id: uuid.UUID,
) -> tuple[str, _Subject | None]:
    with manager.session_factory() as session:
        campaign = session.scalar(
            select(Campaign).where(
                Campaign.workspace_id == workspace_id, Campaign.id == campaign_id
            )
        )
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.workspace_id == workspace_id,
                Conversation.id == conversation_id,
            )
        )
        version = session.scalar(
            select(ConversationVersion).where(
                ConversationVersion.workspace_id == workspace_id,
                ConversationVersion.id == version_id,
                ConversationVersion.conversation_id == conversation_id,
            )
        )
        if campaign is None or conversation is None or version is None:
            return "missing", None
        existing = session.scalar(
            select(Analysis.id).where(
                Analysis.workspace_id == workspace_id,
                Analysis.campaign_id == campaign_id,
                Analysis.conversation_version_id == version_id,
                Analysis.analysis_identity == analysis_task.analysis_identity(),
            )
        )
        if existing is not None:
            return "already_done", None
        session.expunge_all()
        return "claimed", _Subject(campaign, conversation, version)


def _persist_scored(
    manager: DatabaseSessionManager,
    subject: _Subject,
    *,
    model_run_id: uuid.UUID,
    output: analysis_task.ConversationAnalysis,
    created_at: datetime,
    scored_at: datetime,
) -> _Scored:
    """Create the Analysis and create-or-rescore the Opportunity atomically."""
    age_hours = (scored_at - created_at).total_seconds() / 3600.0
    breakdown = opportunity_score(output.model_dump(), age_hours)
    with manager.session_factory() as session, session.begin():
        analysis = Analysis(
            workspace_id=subject.campaign.workspace_id,
            campaign_id=subject.campaign.id,
            conversation_id=subject.conversation.id,
            conversation_version_id=subject.version.id,
            model_run_id=model_run_id,
            analysis_identity=analysis_task.analysis_identity(),
            relevance=output.relevance,
            pain_intensity=output.pain_intensity,
            buying_intent=output.buying_intent,
            replyability=output.replyability,
            product_fit=output.product_fit,
            promotion_fit=output.promotion_fit,
            confidence=output.confidence,
            topic=output.topic,
            persona=output.persona,
            recommended_action=output.recommended_action,
            rationale=output.rationale,
        )
        session.add(analysis)
        session.flush()
        opportunity = session.scalar(
            select(Opportunity)
            .where(
                Opportunity.workspace_id == subject.campaign.workspace_id,
                Opportunity.campaign_id == subject.campaign.id,
                Opportunity.conversation_id == subject.conversation.id,
            )
            .with_for_update()
        )
        created = opportunity is None
        if opportunity is None:
            opportunity = Opportunity(
                workspace_id=subject.campaign.workspace_id,
                campaign_id=subject.campaign.id,
                conversation_id=subject.conversation.id,
                analysis_id=analysis.id,
                opportunity_score=breakdown.score,
                score_components=breakdown.as_components(),
                formula_version=breakdown.formula_version,
                post_created_at=created_at,
                scored_at=scored_at,
            )
            session.add(opportunity)
        else:
            # Re-scoring never touches the operator's disposition.
            opportunity.analysis_id = analysis.id
            opportunity.opportunity_score = breakdown.score
            opportunity.score_components = breakdown.as_components()
            opportunity.formula_version = breakdown.formula_version
            opportunity.post_created_at = created_at
            opportunity.scored_at = scored_at
        session.flush()
        return _Scored(
            analysis_id=analysis.id,
            opportunity_id=opportunity.id,
            score=breakdown.score,
            recommended_action=output.recommended_action,
            created=created,
        )


async def _publish(
    workspace_id: uuid.UUID,
    scope_id: uuid.UUID,
    correlation_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Publish on the run-scoped bus.

    ``scope_id`` is the Discovery Run whose Candidate became this Conversation
    when the enqueuer knew it, so a still-open run stream sees the analysis;
    otherwise the Campaign id scopes the event.
    """
    await progress_events.publish_progress_event(
        ProgressEvent.create(
            event_type=event_type,
            run_id=scope_id,
            workspace_id=workspace_id,
            correlation_id=correlation_id,
            payload=payload,
        )
    )


async def run_conversation_analysis(
    ctx: object,
    *,
    workspace_id: str,
    campaign_id: str,
    conversation_id: str,
    conversation_version_id: str,
    correlation_id: str,
    discovery_run_id: str | None = None,
) -> str:
    """Direct arq callable; returns a marker naming how the job settled."""
    del ctx
    settings = get_settings()
    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        workspace_uuid = uuid.UUID(workspace_id)
        campaign_uuid = uuid.UUID(campaign_id)
        scope_uuid = uuid.UUID(discovery_run_id) if discovery_run_id else campaign_uuid
        marker, subject = _load_subject(
            manager,
            workspace_uuid,
            campaign_uuid,
            uuid.UUID(conversation_id),
            uuid.UUID(conversation_version_id),
        )
        if subject is None:
            return marker

        content = dict(subject.version.normalized_content)
        created_at = post_created_at(content)
        if created_at is None:
            await _publish(
                workspace_uuid,
                scope_uuid,
                correlation_id,
                "job.failed",
                {
                    "job": "conversation_analysis",
                    "conversation_version_id": conversation_version_id,
                    "error_class": "unscorable",
                },
            )
            return "unscorable"

        scored_at = datetime.now(UTC)
        age_hours = max((scored_at - created_at).total_seconds() / 3600.0, 0.0)
        campaign_context = _campaign_context(subject.campaign)
        runner = LLMTaskRunner(settings=settings, model_override=MODEL_OVERRIDE)
        result = await runner.run(
            analysis_task.TASK_SPEC,
            workspace_id=workspace_uuid,
            correlation_id=correlation_id,
            user_prompt=analysis_task.build_user_prompt(
                campaign=campaign_context, content=content, age_hours=age_hours
            ),
            input_sha256=analysis_task.input_digest(
                campaign_id=campaign_id,
                conversation_version_id=conversation_version_id,
                normalized_content_sha256=subject.version.normalized_content_sha256,
                campaign=campaign_context,
            ),
            domain_validator=analysis_task.domain_validate,
        )
        # The Model Run is evidence of spend and outcome; it commits first
        # and on its own so a later failure cannot erase it.
        with manager.session_factory() as session, session.begin():
            session.add(result.model_run)
            session.flush()
            model_run_id = result.model_run.id
            failure_class = result.model_run.failure_class

        if result.output is None:
            await _publish(
                workspace_uuid,
                scope_uuid,
                correlation_id,
                "job.failed",
                {
                    "job": "conversation_analysis",
                    "conversation_version_id": conversation_version_id,
                    "model_run_id": str(model_run_id),
                    "error_class": failure_class,
                },
            )
            return "analysis_failed"

        try:
            scored = _persist_scored(
                manager,
                subject,
                model_run_id=model_run_id,
                output=result.output,
                created_at=created_at,
                scored_at=scored_at,
            )
        except IntegrityError:
            # A concurrent replay won the identity race; its row is canonical.
            return "already_done"
        except ScoringInputError as error:
            logger.warning("analysis output could not be scored: %s", error)
            return "analysis_failed"

        await _publish(
            workspace_uuid,
            scope_uuid,
            correlation_id,
            "analysis.completed",
            {
                "conversation_id": conversation_id,
                "conversation_version_id": conversation_version_id,
                "analysis_id": str(scored.analysis_id),
                "opportunity_id": str(scored.opportunity_id),
                "opportunity_score": scored.score,
                "recommended_action": scored.recommended_action,
                "opportunity_created": scored.created,
            },
        )
        return "scored"
    finally:
        manager.dispose()
