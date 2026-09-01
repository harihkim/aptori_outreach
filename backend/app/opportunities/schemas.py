"""Wire contracts for the Opportunity Inbox; path-free and provenance-bearing."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

OpportunityStatus = Literal["open", "saved", "dismissed", "acted_on"]
RecommendedAction = Literal[
    "ignore",
    "monitor",
    "reply_helpfully",
    "reply_with_product",
    "content_opportunity",
]


class OpportunityConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_platform: str
    canonical_external_discussion_id: str
    conversation_version_id: UUID
    normalizer_version: str
    title: str
    subreddit: str | None
    url: AnyHttpUrl | None
    post_score: float | None
    reported_comment_count: int | None


class AnalysisFactors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: float = Field(ge=0, le=1)
    pain_intensity: float = Field(ge=0, le=1)
    buying_intent: float = Field(ge=0, le=1)
    replyability: float = Field(ge=0, le=1)
    product_fit: float = Field(ge=0, le=1)
    promotion_fit: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    analysis_identity: str
    factors: AnalysisFactors
    topic: str
    persona: str | None
    recommended_action: RecommendedAction
    rationale: str
    created_at: datetime


class ModelRunSummary(BaseModel):
    """Provider provenance without prompts, completions, or credentials."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    task_id: str
    task_version: str
    prompt_version: str
    schema_version: str
    model_tier: str
    served_tier: str
    requested_model: str | None
    actual_model: str | None
    endpoint_label: str | None
    input_tokens: int | None
    output_tokens: int | None
    request_count: int
    output_retry_count: int
    cost_status: str
    status: str
    created_at: datetime


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    campaign_id: UUID
    conversation_id: UUID
    analysis_id: UUID
    opportunity_score: float = Field(ge=0, le=1)
    formula_version: str
    score_components: dict[str, object]
    status: OpportunityStatus
    post_created_at: datetime
    scored_at: datetime
    saved_at: datetime | None
    dismissed_at: datetime | None
    dismissal_reason: str | None
    created_at: datetime
    updated_at: datetime
    conversation: OpportunityConversationSummary
    analysis: AnalysisSummary
    model_run: ModelRunSummary


class OpportunityListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OpportunityResponse]
