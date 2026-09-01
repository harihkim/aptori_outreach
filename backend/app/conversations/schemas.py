"""Path-free REST contracts for Candidate-to-Conversation transitions."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class ConversationVersionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    normalizer_version: str
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_tree_exhausted: bool
    created_at: datetime


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_platform: str
    canonical_external_discussion_id: str
    current_version: ConversationVersionSummary


class CandidateConversationTransitionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_source_id: str
    url: AnyHttpUrl
    title: str
    rank: int | None
    state: Literal["candidate", "conversation"]
    retrieval_status: str | None
    conversation: ConversationSummary | None


class RunConversationTransitionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CandidateConversationTransitionResponse]
    expected_count: int = Field(ge=0)
    fetched_count: int = Field(ge=0)
    normalized_count: int = Field(ge=0)
    processing_complete: bool
