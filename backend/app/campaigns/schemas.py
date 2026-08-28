from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

PromotionPosture = Literal["expertise_first", "balanced", "high_intent_only"]
CampaignStatus = Literal["draft", "active", "paused", "archived"]

NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

OptionalText = (
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)] | None
)

TagItem = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


def _clean_tag_list(items: list[str]) -> list[str]:
    """Blank items drop; duplicates collapse preserving first occurrence."""
    cleaned: list[str] = []
    for item in items:
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


TagList = Annotated[
    list[TagItem], Field(max_length=100), AfterValidator(_clean_tag_list)
]

# product_context and icp are nullable columns: an explicit null clears them.
NULLABLE_ON_UPDATE = frozenset({"product_context", "icp"})


class CampaignCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyText
    product_context: OptionalText = None
    icp: OptionalText = None
    keywords: TagList = []
    subreddits: TagList = []
    competitors: TagList = []
    approved_claims: TagList = []
    prohibited_claims: TagList = []
    promotion_posture: PromotionPosture


class CampaignUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyText | None = None
    product_context: OptionalText = None
    icp: OptionalText = None
    keywords: TagList | None = None
    subreddits: TagList | None = None
    competitors: TagList | None = None
    approved_claims: TagList | None = None
    prohibited_claims: TagList | None = None
    promotion_posture: PromotionPosture | None = None
    status: CampaignStatus | None = None

    @model_validator(mode="after")
    def _reject_null_on_non_nullable_fields(self) -> "CampaignUpdate":
        nulls = sorted(
            field
            for field in self.model_fields_set
            if getattr(self, field) is None and field not in NULLABLE_ON_UPDATE
        )
        if nulls:
            raise ValueError(f"Fields may not be null: {', '.join(nulls)}")
        return self


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    product_context: str | None
    icp: str | None
    keywords: list[str]
    subreddits: list[str]
    competitors: list[str]
    approved_claims: list[str]
    prohibited_claims: list[str]
    promotion_posture: PromotionPosture
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CampaignPageResponse(BaseModel):
    items: list[CampaignResponse]
    next_cursor: str | None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorBody
