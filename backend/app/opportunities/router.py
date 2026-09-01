from typing import Annotated, Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import AnyHttpUrl, ValidationError

from app.campaigns.schemas import ErrorResponse
from app.deps import PrincipalDep, SessionDep, WorkspaceDep
from app.opportunities import service
from app.opportunities.schemas import (
    AnalysisFactors,
    AnalysisSummary,
    ModelRunSummary,
    OpportunityConversationSummary,
    OpportunityListResponse,
    OpportunityResponse,
    OpportunityStatus,
    RecommendedAction,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])

_AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid bearer token."},
    403: {"model": ErrorResponse, "description": "Workspace access denied."},
    503: {
        "model": ErrorResponse,
        "description": "API token or workspace unconfigured.",
    },
}

OpportunityStatusQuery = Literal["open", "saved", "dismissed", "acted_on"]


def _http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


def _not_found() -> HTTPException:
    return _http_error(
        status.HTTP_404_NOT_FOUND, "opportunity_not_found", "Opportunity not found."
    )


def _forbidden() -> HTTPException:
    return _http_error(
        status.HTTP_403_FORBIDDEN,
        "workspace_forbidden",
        "The authenticated principal cannot access this workspace.",
    )


def _reddit_url(post: dict[str, Any]) -> AnyHttpUrl | None:
    permalink = post.get("permalink")
    if not isinstance(permalink, str) or not permalink.startswith("/"):
        return None
    try:
        return AnyHttpUrl(f"https://www.reddit.com{permalink}")
    except ValidationError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _response(item: service.OpportunityRead) -> OpportunityResponse:
    post = item.post
    opportunity = item.opportunity
    analysis = item.analysis
    title = post.get("title")
    subreddit = post.get("subreddit")
    return OpportunityResponse(
        id=opportunity.id,
        campaign_id=opportunity.campaign_id,
        conversation_id=opportunity.conversation_id,
        analysis_id=opportunity.analysis_id,
        opportunity_score=opportunity.opportunity_score,
        formula_version=opportunity.formula_version,
        score_components=dict(opportunity.score_components),
        status=cast(OpportunityStatus, opportunity.status),
        post_created_at=opportunity.post_created_at,
        scored_at=opportunity.scored_at,
        saved_at=opportunity.saved_at,
        dismissed_at=opportunity.dismissed_at,
        dismissal_reason=opportunity.dismissal_reason,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
        conversation=OpportunityConversationSummary(
            id=item.conversation.id,
            source_platform=item.conversation.source_platform,
            canonical_external_discussion_id=(
                item.conversation.canonical_external_discussion_id
            ),
            conversation_version_id=item.version.id,
            normalizer_version=item.version.normalizer_version,
            title=title if isinstance(title, str) else "",
            subreddit=subreddit if isinstance(subreddit, str) else None,
            url=_reddit_url(post),
            post_score=_number(post.get("score")),
            reported_comment_count=_integer(post.get("totalReportedComments")),
        ),
        analysis=AnalysisSummary(
            id=analysis.id,
            analysis_identity=analysis.analysis_identity,
            factors=AnalysisFactors(**analysis.factors()),
            topic=analysis.topic,
            persona=analysis.persona,
            recommended_action=cast(RecommendedAction, analysis.recommended_action),
            rationale=analysis.rationale,
            created_at=analysis.created_at,
        ),
        model_run=ModelRunSummary.model_validate(item.model_run),
    )


@router.get(
    "",
    response_model=OpportunityListResponse,
    responses=_AUTH_RESPONSES,
)
def list_opportunities(
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
    campaign_id: Annotated[UUID | None, Query()] = None,
    opportunity_status: Annotated[
        OpportunityStatusQuery | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=service.MAX_PAGE)] = 50,
) -> OpportunityListResponse:
    try:
        items = service.list_opportunities(
            session,
            principal,
            workspace.id,
            campaign_id=campaign_id,
            status=opportunity_status,
            limit=limit,
        )
    except service.WorkspaceAccessDenied:
        raise _forbidden() from None
    return OpportunityListResponse(items=[_response(item) for item in items])


@router.get(
    "/{opportunity_id}",
    response_model=OpportunityResponse,
    responses={
        **_AUTH_RESPONSES,
        404: {"model": ErrorResponse, "description": "Opportunity not found."},
    },
)
def get_opportunity(
    opportunity_id: Annotated[UUID, Path()],
    session: SessionDep,
    workspace: WorkspaceDep,
    principal: PrincipalDep,
) -> OpportunityResponse:
    try:
        item = service.get_opportunity(session, principal, workspace.id, opportunity_id)
    except service.WorkspaceAccessDenied:
        raise _forbidden() from None
    except service.OpportunityNotFound:
        raise _not_found() from None
    return _response(item)
