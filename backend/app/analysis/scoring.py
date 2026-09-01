"""Frozen Opportunity Score formula v1.0 (Opportunity Scoring v0.3, 2026-08-22).

A pure function: the same typed factors and age always produce the same
score. Weights change only by freezing a new formula version and re-running
the frozen labeled evaluation; nothing here reads configuration.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

FORMULA_VERSION = "v1.0"
HALF_LIFE_HOURS = 48.0

# Linear weights over the typed factors. `promotion_fit` is deliberately
# absent: a valuable thread may still warrant a product-free expert reply.
WEIGHTS: dict[str, float] = {
    "relevance": 0.375,
    "pain_intensity": 0.1875,
    "buying_intent": 0.125,
    "replyability": 0.1875,
    "product_fit": 0.125,
}
SCORED_FACTORS: tuple[str, ...] = tuple(WEIGHTS)


class ScoringInputError(ValueError):
    """A factor is missing, non-numeric, non-finite, or outside [0, 1]."""


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """The aggregate plus every component needed to explain it later."""

    formula_version: str
    score: float
    linear_mean: float
    freshness_factor: float
    age_hours: float
    weighted: dict[str, float]

    def as_components(self) -> dict[str, object]:
        return {
            "formula_version": self.formula_version,
            "weights": dict(WEIGHTS),
            "weighted": dict(self.weighted),
            "linear_mean": self.linear_mean,
            "freshness_factor": self.freshness_factor,
            "age_hours": self.age_hours,
            "half_life_hours": HALF_LIFE_HOURS,
        }


def _factor(factors: Mapping[str, object], name: str) -> float:
    value = factors.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScoringInputError(f"factor {name!r} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ScoringInputError(f"factor {name!r} must lie within [0, 1]")
    return number


def freshness_factor(age_hours: float) -> float:
    """Exponential decay with a 48-hour half-life; age below zero counts as zero."""
    if not math.isfinite(age_hours):
        raise ScoringInputError("age_hours must be finite")
    clamped_age = max(age_hours, 0.0)
    return math.exp(-math.log(2.0) * clamped_age / HALF_LIFE_HOURS)


def opportunity_score(
    factors: Mapping[str, object], age_hours: float
) -> ScoreBreakdown:
    """Weighted linear mean × freshness decay, clamped to [0, 1]."""
    weighted = {name: WEIGHTS[name] * _factor(factors, name) for name in SCORED_FACTORS}
    linear_mean = sum(weighted.values())
    decay = freshness_factor(age_hours)
    raw = linear_mean * decay
    return ScoreBreakdown(
        formula_version=FORMULA_VERSION,
        score=min(max(raw, 0.0), 1.0),
        linear_mean=linear_mean,
        freshness_factor=decay,
        age_hours=max(age_hours, 0.0),
        weighted=weighted,
    )
