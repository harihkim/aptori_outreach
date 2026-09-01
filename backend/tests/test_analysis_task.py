"""`analyze_conversation`: typed output, domain validators, prompt rendering."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.analysis import task
from app.llm.runner import DomainValidationError

VALID: dict[str, Any] = {
    "relevance": 0.94,
    "pain_intensity": 0.82,
    "buying_intent": 0.71,
    "replyability": 0.91,
    "product_fit": 0.89,
    "promotion_fit": 0.34,
    "confidence": 0.8,
    "persona": "security engineer",
    "topic": "API auth failures",
    "rationale": "The author describes broken token rotation and asks for help.",
    "recommended_action": "reply_helpfully",
}


def test_documented_example_is_schema_and_domain_valid() -> None:
    analysis = task.ConversationAnalysis.model_validate(VALID)
    task.domain_validate(analysis)


@pytest.mark.parametrize(
    "override",
    [
        {"relevance": 1.01},
        {"confidence": -0.1},
        {"topic": ""},
        {"recommended_action": "buy_now"},
        {"extra_field": 1},
    ],
)
def test_schema_rejects_out_of_range_or_unknown_fields(
    override: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        task.ConversationAnalysis.model_validate({**VALID, **override})


def test_reply_with_product_requires_promotion_and_product_fit() -> None:
    inconsistent = task.ConversationAnalysis.model_validate(
        {**VALID, "recommended_action": "reply_with_product", "promotion_fit": 0.2}
    )
    with pytest.raises(DomainValidationError, match="reply_with_product"):
        task.domain_validate(inconsistent)
    consistent = task.ConversationAnalysis.model_validate(
        {**VALID, "recommended_action": "reply_with_product", "promotion_fit": 0.6}
    )
    task.domain_validate(consistent)


def test_ignore_is_inconsistent_with_high_relevance() -> None:
    inconsistent = task.ConversationAnalysis.model_validate(
        {**VALID, "recommended_action": "ignore", "relevance": 0.9}
    )
    with pytest.raises(DomainValidationError, match="ignore"):
        task.domain_validate(inconsistent)
    task.domain_validate(
        task.ConversationAnalysis.model_validate(
            {**VALID, "recommended_action": "ignore", "relevance": 0.2}
        )
    )


def test_blank_rationale_is_rejected_even_when_schema_valid() -> None:
    blank = task.ConversationAnalysis.model_validate({**VALID, "rationale": "   "})
    with pytest.raises(DomainValidationError, match="rationale"):
        task.domain_validate(blank)


def _content() -> dict[str, Any]:
    return {
        "post": {
            "title": "Token rotation keeps failing",
            "selftext": "Our API gateway drops rotated tokens. " * 3,
            "subreddit": "r/netsec",
            "score": 42,
            "totalReportedComments": 3,
            "createdUtc": 1_700_000_000,
        },
        "comments": [
            {"author": "low", "score": 1, "body": "same here", "visibility": "visible"},
            {
                "author": "top",
                "score": 30,
                "body": "check your JWKS cache",
                "visibility": "visible",
            },
            {
                "author": "[deleted]",
                "score": 99,
                "body": "[deleted]",
                "visibility": "deleted",
            },
        ],
    }


def _campaign() -> dict[str, Any]:
    return {
        "name": "API security",
        "product_context": "Runtime API protection",
        "icp": "Security engineers",
        "keywords": ["api security", "token rotation"],
        "competitors": ["Competitor X"],
        "promotion_posture": "expertise_first",
        "approved_claims": ["Detects broken auth"],
        "prohibited_claims": ["Guarantees compliance"],
    }


def test_prompt_renders_campaign_constraints_and_ranked_visible_comments() -> None:
    prompt = task.build_user_prompt(
        campaign=_campaign(), content=_content(), age_hours=12.25
    )
    assert "Product context: Runtime API protection" in prompt
    assert "Keywords: api security, token rotation" in prompt
    assert "Prohibited claims: Guarantees compliance" in prompt
    assert "Subreddit: r/netsec" in prompt
    assert "Title: Token rotation keeps failing" in prompt
    assert "Age: 12.2 hours" in prompt or "Age: 12.3 hours" in prompt
    top_index = prompt.index("(30) top:")
    low_index = prompt.index("(1) low:")
    assert top_index < low_index
    assert "[deleted]" not in prompt


def test_prompt_clips_long_bodies_and_survives_missing_fields() -> None:
    content = _content()
    post = content["post"]
    assert isinstance(post, dict)
    post["selftext"] = "x" * (task.MAX_SELFTEXT_CHARS + 100)
    prompt = task.build_user_prompt(campaign=_campaign(), content=content, age_hours=0)
    assert "x" * (task.MAX_SELFTEXT_CHARS + 1) not in prompt
    bare = task.build_user_prompt(campaign={}, content={}, age_hours=0)
    assert "Subreddit: (unknown)" in bare
    assert "(no body)" in bare
    assert "(none)" in bare


def test_input_digest_changes_with_context_but_never_embeds_the_prompt() -> None:
    first = task.input_digest(
        campaign_id="c",
        conversation_version_id="v",
        normalized_content_sha256="a" * 64,
        campaign=_campaign(),
    )
    assert first == task.input_digest(
        campaign_id="c",
        conversation_version_id="v",
        normalized_content_sha256="a" * 64,
        campaign=_campaign(),
    )
    assert first != task.input_digest(
        campaign_id="c",
        conversation_version_id="v",
        normalized_content_sha256="a" * 64,
        campaign={**_campaign(), "icp": "Platform teams"},
    )
    assert len(first) == 64


def test_analysis_identity_pins_every_version() -> None:
    assert task.analysis_identity() == "analyze_conversation@1:2026-09-02.1:1"
    assert task.TASK_SPEC.output_type is task.ConversationAnalysis
