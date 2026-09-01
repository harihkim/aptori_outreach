"""The `analyze_conversation` LLM Task: typed output, prompt, and validators.

Schema validity proves neither truth nor consistency. The model returns
factors in [0, 1]; application code then rejects internally inconsistent
combinations before any score exists.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.llm.runner import DomainValidationError, TaskSpec, sha256_of

TASK_ID = "analyze_conversation"
TASK_VERSION = "1"
PROMPT_VERSION = "2026-09-02.1"
SCHEMA_VERSION = "1"
EVAL_SUITE_ID = "analyze_conversation/frozen-labels-v1"

RecommendedAction = Literal[
    "ignore",
    "monitor",
    "reply_helpfully",
    "reply_with_product",
    "content_opportunity",
]
RECOMMENDED_ACTIONS: tuple[str, ...] = (
    "ignore",
    "monitor",
    "reply_helpfully",
    "reply_with_product",
    "content_opportunity",
)

MAX_SELFTEXT_CHARS = 6_000
MAX_COMMENT_CHARS = 600
MAX_COMMENTS = 20


class ConversationAnalysis(BaseModel):
    """Typed factors, rationale, confidence, and a recommended action."""

    model_config = ConfigDict(extra="forbid")

    relevance: float = Field(ge=0.0, le=1.0)
    pain_intensity: float = Field(ge=0.0, le=1.0)
    buying_intent: float = Field(ge=0.0, le=1.0)
    replyability: float = Field(ge=0.0, le=1.0)
    product_fit: float = Field(ge=0.0, le=1.0)
    promotion_fit: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    persona: str | None = Field(default=None, max_length=200)
    topic: str = Field(min_length=1, max_length=200)
    rationale: str = Field(min_length=1, max_length=2_000)
    recommended_action: RecommendedAction


INSTRUCTIONS = """\
You assess one public Reddit discussion for a B2B outreach Campaign.
Return typed factors in [0, 1] and a short, evidence-backed rationale.

Factor meanings:
- relevance: how directly the discussion concerns the Campaign's problem space.
- pain_intensity: how strongly the author expresses an unmet need or frustration.
- buying_intent: how close the author is to evaluating or purchasing a solution.
- replyability: how welcome and useful a thoughtful expert reply would be now.
- product_fit: how well the Campaign's product and audience fit this author
  and community (include author and community fit here).
- promotion_fit: whether mentioning a product would be appropriate here.
  Keep this independent of the other factors: a high-value thread can still
  forbid promotion.
- confidence: how certain you are about these factors given the evidence.

recommended_action must be consistent with the factors:
- "reply_with_product" only when promotion_fit >= 0.5 and product_fit >= 0.5.
- "ignore" only when relevance <= 0.5.
- otherwise choose "monitor", "reply_helpfully", or "content_opportunity".

Never invent claims about the product. Never quote prohibited claims.
The rationale must cite what in the thread supports the factors.
"""


def domain_validate(analysis: ConversationAnalysis) -> None:
    """Reject schema-valid but internally inconsistent analyses."""
    if analysis.recommended_action == "reply_with_product" and (
        analysis.promotion_fit < 0.5 or analysis.product_fit < 0.5
    ):
        raise DomainValidationError(
            "reply_with_product requires promotion_fit and product_fit >= 0.5"
        )
    if analysis.recommended_action == "ignore" and analysis.relevance > 0.5:
        raise DomainValidationError("ignore is inconsistent with relevance > 0.5")
    if not analysis.topic.strip() or not analysis.rationale.strip():
        raise DomainValidationError("topic and rationale must be non-blank")


TASK_SPEC: TaskSpec[ConversationAnalysis] = TaskSpec(
    task_id=TASK_ID,
    task_version=TASK_VERSION,
    prompt_version=PROMPT_VERSION,
    schema_version=SCHEMA_VERSION,
    eval_suite_id=EVAL_SUITE_ID,
    instructions=INSTRUCTIONS,
    output_type=ConversationAnalysis,
)


def analysis_identity() -> str:
    """The idempotency identity of one analysis under the current versions."""
    return f"{TASK_ID}@{TASK_VERSION}:{PROMPT_VERSION}:{SCHEMA_VERSION}"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _comment_rows(content: dict[str, Any]) -> list[dict[str, Any]]:
    comments = content.get("comments")
    if not isinstance(comments, list):
        return []
    visible = [
        item
        for item in comments
        if isinstance(item, dict) and item.get("visibility") == "visible"
    ]

    def score_of(item: dict[str, Any]) -> float:
        value = item.get("score")
        return float(value) if isinstance(value, (int, float)) else 0.0

    visible.sort(key=score_of, reverse=True)
    return visible[:MAX_COMMENTS]


def build_user_prompt(
    *,
    campaign: dict[str, Any],
    content: dict[str, Any],
    age_hours: float,
) -> str:
    """Render the Campaign constraints and the normalized thread as text."""
    post_raw = content.get("post")
    post: dict[str, Any] = post_raw if isinstance(post_raw, dict) else {}
    lines = [
        "## Campaign",
        f"Name: {campaign.get('name') or ''}",
        f"Product context: {campaign.get('product_context') or '(not provided)'}",
        f"Audience (ICP): {campaign.get('icp') or '(not provided)'}",
        f"Keywords: {', '.join(campaign.get('keywords') or []) or '(none)'}",
        f"Competitors: {', '.join(campaign.get('competitors') or []) or '(none)'}",
        f"Promotion posture: {campaign.get('promotion_posture') or ''}",
        "Approved claims: "
        + ("; ".join(campaign.get("approved_claims") or []) or "(none)"),
        "Prohibited claims: "
        + ("; ".join(campaign.get("prohibited_claims") or []) or "(none)"),
        "",
        "## Thread",
        f"Subreddit: {post.get('subreddit') or '(unknown)'}",
        f"Title: {post.get('title') or ''}",
        f"Age: {age_hours:.1f} hours",
        f"Score: {post.get('score') if post.get('score') is not None else 'unknown'}",
        "Reported comments: "
        + str(
            post.get("totalReportedComments")
            if post.get("totalReportedComments") is not None
            else "unknown"
        ),
        "",
        "### Post body",
        _clip(str(post.get("selftext") or "(no body)"), MAX_SELFTEXT_CHARS),
        "",
        "### Top visible comments",
    ]
    rows = _comment_rows(content)
    if not rows:
        lines.append("(none)")
    for item in rows:
        author = item.get("author") or "[unknown]"
        score = item.get("score")
        body = _clip(str(item.get("body") or ""), MAX_COMMENT_CHARS)
        lines.append(f"- ({score if score is not None else '?'}) {author}: {body}")
    return "\n".join(lines)


def input_digest(
    *,
    campaign_id: str,
    conversation_version_id: str,
    normalized_content_sha256: str,
    campaign: dict[str, Any],
) -> str:
    """Digest of everything that shaped the prompt, without the prompt itself."""
    return sha256_of(
        {
            "task": analysis_identity(),
            "campaign_id": campaign_id,
            "conversation_version_id": conversation_version_id,
            "normalized_content_sha256": normalized_content_sha256,
            "campaign": campaign,
        }
    )
