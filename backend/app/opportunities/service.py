"""Workspace-scoped reads over Opportunities and their explaining records."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.models import Analysis
from app.auth import Principal
from app.conversations.models import Conversation, ConversationVersion
from app.llm.models import ModelRun
from app.opportunities.models import OPPORTUNITY_STATUSES, Opportunity

MAX_PAGE = 200


class OpportunityNotFound(LookupError):
    """No Opportunity with that id exists in the caller's Workspace."""


class WorkspaceAccessDenied(PermissionError):
    """The principal cannot read the requested Workspace."""


@dataclass(frozen=True, slots=True)
class OpportunityRead:
    opportunity: Opportunity
    analysis: Analysis
    model_run: ModelRun
    conversation: Conversation
    version: ConversationVersion

    @property
    def post(self) -> dict[str, Any]:
        post = self.version.normalized_content.get("post")
        return dict(post) if isinstance(post, dict) else {}


def _require_workspace_access(principal: Principal, workspace_id: uuid.UUID) -> None:
    if not principal.can_access(workspace_id):
        raise WorkspaceAccessDenied(str(workspace_id))


def _base_statement(workspace_id: uuid.UUID) -> Any:
    return (
        select(Opportunity, Analysis, ModelRun, Conversation, ConversationVersion)
        .join(
            Analysis,
            (Analysis.workspace_id == Opportunity.workspace_id)
            & (Analysis.id == Opportunity.analysis_id),
        )
        .join(
            ModelRun,
            (ModelRun.workspace_id == Analysis.workspace_id)
            & (ModelRun.id == Analysis.model_run_id),
        )
        .join(
            Conversation,
            (Conversation.workspace_id == Opportunity.workspace_id)
            & (Conversation.id == Opportunity.conversation_id),
        )
        .join(
            ConversationVersion,
            (ConversationVersion.workspace_id == Analysis.workspace_id)
            & (ConversationVersion.id == Analysis.conversation_version_id),
        )
        .where(Opportunity.workspace_id == workspace_id)
    )


def list_opportunities(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    *,
    campaign_id: uuid.UUID | None,
    status: str | None,
    limit: int,
) -> list[OpportunityRead]:
    """Ranked Inbox: highest score first, newest first among equal scores."""
    _require_workspace_access(principal, workspace_id)
    if status is not None and status not in OPPORTUNITY_STATUSES:
        raise ValueError(f"unknown opportunity status: {status!r}")
    statement = _base_statement(workspace_id)
    if campaign_id is not None:
        statement = statement.where(Opportunity.campaign_id == campaign_id)
    if status is not None:
        statement = statement.where(Opportunity.status == status)
    rows = session.execute(
        statement.order_by(
            Opportunity.opportunity_score.desc(), Opportunity.creation_order.desc()
        ).limit(min(max(limit, 1), MAX_PAGE))
    ).all()
    return [OpportunityRead(*row) for row in rows]


def get_opportunity(
    session: Session,
    principal: Principal,
    workspace_id: uuid.UUID,
    opportunity_id: uuid.UUID,
) -> OpportunityRead:
    _require_workspace_access(principal, workspace_id)
    row = session.execute(
        _base_statement(workspace_id).where(Opportunity.id == opportunity_id)
    ).first()
    if row is None:
        raise OpportunityNotFound(str(opportunity_id))
    return OpportunityRead(*row)
