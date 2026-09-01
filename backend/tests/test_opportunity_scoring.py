"""Frozen formula v1.0: golden vectors, decay boundaries, clamping, rejection."""

import math

import pytest

from app.analysis.scoring import (
    FORMULA_VERSION,
    HALF_LIFE_HOURS,
    SCORED_FACTORS,
    WEIGHTS,
    ScoringInputError,
    freshness_factor,
    opportunity_score,
)

# The worked example from Opportunity Scoring v0.3.
DOC_EXAMPLE = {
    "relevance": 0.94,
    "pain_intensity": 0.82,
    "buying_intent": 0.71,
    "replyability": 0.91,
    "product_fit": 0.89,
    "promotion_fit": 0.34,
}
DOC_EXAMPLE_LINEAR = 0.876875


def test_formula_is_frozen_at_v1_with_weights_summing_to_one() -> None:
    assert FORMULA_VERSION == "v1.0"
    assert HALF_LIFE_HOURS == 48.0
    assert math.isclose(sum(WEIGHTS.values()), 1.0, abs_tol=1e-12)
    assert "promotion_fit" not in WEIGHTS
    assert SCORED_FACTORS == (
        "relevance",
        "pain_intensity",
        "buying_intent",
        "replyability",
        "product_fit",
    )


def test_golden_vector_at_zero_age_matches_the_documented_example() -> None:
    breakdown = opportunity_score(DOC_EXAMPLE, age_hours=0.0)
    assert math.isclose(breakdown.linear_mean, DOC_EXAMPLE_LINEAR, abs_tol=1e-12)
    assert math.isclose(breakdown.score, DOC_EXAMPLE_LINEAR, abs_tol=1e-12)
    assert breakdown.freshness_factor == 1.0
    assert breakdown.weighted == {
        "relevance": 0.375 * 0.94,
        "pain_intensity": 0.1875 * 0.82,
        "buying_intent": 0.125 * 0.71,
        "replyability": 0.1875 * 0.91,
        "product_fit": 0.125 * 0.89,
    }


@pytest.mark.parametrize(
    ("age_hours", "fraction"),
    [(48.0, 0.5), (96.0, 0.25), (144.0, 0.125), (24.0, 2**-0.5)],
)
def test_half_life_boundaries(age_hours: float, fraction: float) -> None:
    breakdown = opportunity_score(DOC_EXAMPLE, age_hours=age_hours)
    assert math.isclose(breakdown.freshness_factor, fraction, rel_tol=1e-12)
    assert math.isclose(breakdown.score, DOC_EXAMPLE_LINEAR * fraction, rel_tol=1e-12)


def test_future_dated_posts_decay_as_if_brand_new() -> None:
    assert freshness_factor(-5.0) == 1.0
    assert opportunity_score(DOC_EXAMPLE, age_hours=-5.0).age_hours == 0.0


def test_score_is_clamped_to_the_unit_interval() -> None:
    top = dict.fromkeys(SCORED_FACTORS, 1.0)
    assert opportunity_score(top, age_hours=0.0).score == 1.0
    bottom = dict.fromkeys(SCORED_FACTORS, 0.0)
    assert opportunity_score(bottom, age_hours=0.0).score == 0.0


def test_promotion_fit_never_moves_the_score() -> None:
    low = opportunity_score({**DOC_EXAMPLE, "promotion_fit": 0.0}, age_hours=3.0)
    high = opportunity_score({**DOC_EXAMPLE, "promotion_fit": 1.0}, age_hours=3.0)
    assert low.score == high.score


@pytest.mark.parametrize(
    "bad",
    [
        {**DOC_EXAMPLE, "relevance": 1.2},
        {**DOC_EXAMPLE, "buying_intent": -0.01},
        {**DOC_EXAMPLE, "product_fit": float("nan")},
        {**DOC_EXAMPLE, "replyability": "0.9"},
        {**DOC_EXAMPLE, "pain_intensity": True},
        {key: value for key, value in DOC_EXAMPLE.items() if key != "relevance"},
    ],
)
def test_out_of_range_or_missing_factors_are_rejected(bad: dict[str, object]) -> None:
    with pytest.raises(ScoringInputError):
        opportunity_score(bad, age_hours=0.0)


def test_non_finite_age_is_rejected() -> None:
    with pytest.raises(ScoringInputError):
        opportunity_score(DOC_EXAMPLE, age_hours=float("inf"))


def test_components_carry_everything_needed_to_explain_the_score() -> None:
    components = opportunity_score(DOC_EXAMPLE, age_hours=12.0).as_components()
    assert components["formula_version"] == "v1.0"
    assert components["weights"] == WEIGHTS
    assert components["half_life_hours"] == 48.0
    assert components["age_hours"] == 12.0
    weighted = components["weighted"]
    assert isinstance(weighted, dict)
    assert set(weighted) == set(SCORED_FACTORS)
