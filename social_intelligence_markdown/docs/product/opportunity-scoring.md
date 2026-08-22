# Opportunity Scoring

> **Status:** Draft v0.3
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines the scoring model and the important separation between opportunity value and permission/appropriateness to promote.

## Opportunity model and scoring

The versioned Pydantic AI Analysis task produces validated semantic factors, rationale, confidence, and a recommended action. Application code computes the aggregate Opportunity Score from the frozen formula; the model does not directly set ranking state.

### Frozen formula v1.0 (2026-08-22)

A weighted linear mean over the typed analysis factors, multiplied by an exponential freshness decay:

```text
opportunity_score =
  (0.375  * relevance
 + 0.1875 * pain_intensity
 + 0.125  * buying_intent
 + 0.1875 * replyability
 + 0.125  * product_fit)
  * exp(-ln(2) * age_hours / 48)
```

- Weights sum to 1.0; the result is clamped to [0, 1].
- `promotion_fit` is excluded from the formula (see the distinction below).
- **Freshness** enters as the decay factor: a 48-hour half-life, so a thread loses half its score potential every two days of age.
- **Engagement velocity** is a Deterministic Signal stored and displayed on the Conversation, but deliberately unscored in v1.0 — raw engagement is confounded by subreddit size.
- **Author/community fit** is assessed inside `product_fit` and its rationale rather than as a separate scored factor.

Weight derivation, traceable to the earlier example table: relevance 0.30, pain/buying 0.25 (split 0.1875/0.125 after renormalization), replyability 0.15, author/community fit 0.10 folded into `product_fit`; freshness (0.10) became the decay factor and engagement velocity (0.10) became display-only, so the remaining linear weights were renormalized from 0.80 to 1.0.

| Factor | Source | Weight |
|---|---|---|
| `relevance` | LLM Task | 0.375 |
| `pain_intensity` | LLM Task | 0.1875 |
| `buying_intent` | LLM Task | 0.125 |
| `replyability` | LLM Task | 0.1875 |
| `product_fit` | LLM Task (carries author/community fit) | 0.125 |
| freshness | Deterministic Signal — decay multiplier | 48h half-life |
| engagement velocity | Deterministic Signal — displayed, unscored | — |

> **Important distinction.** Keep promotion_fit separate from opportunity_score. A post can be a 95/100 opportunity and still have promotion_fit = 20, meaning: answer helpfully, do not mention the product.

Example analysis:

```json
{
  "relevance": 0.94,
  "pain_intensity": 0.82,
  "buying_intent": 0.71,
  "replyability": 0.91,
  "product_fit": 0.89,
  "promotion_fit": 0.34,
  "recommended_action": "reply_helpfully",
  "reason": "Direct problem fit, but the user did not ask for vendor recommendations."
}
```

### Calibration against the frozen labeled set

- The dataset is LLM-drafted and human-verified: a drafting model proposes labels with a one-line rationale, a human validates or edits each one, and the verified set freezes. Provenance (drafter, verifier, edits) is recorded in the dataset, and the drafting model must differ from the model under evaluation so labels are not self-graded.
- Score agreement is measured with rank correlation (Kendall tau, NDCG@k) rather than threshold accuracy alone; weight stability is checked with leave-one-out over the labeled set.
- Numeric acceptance thresholds are recorded with the dataset when it freezes, not improvised per demo.

## Recommended implementation notes

- Store component scores and rationale, not only the aggregate score.
- Version the scoring formula and model schema so historical results remain explainable.
- Persist the Model Run separately from the deterministic scoring-formula version.
- Reject out-of-range or internally inconsistent typed factors before calculating the score.
- Keep `promotion_fit` outside the overall opportunity score. A valuable conversation may warrant a product-free expert response.
- Add explicit uncertainty/confidence and allow an operator to override the recommended action.
- Change weights only by freezing a new formula version and re-running the frozen labeled evaluation.
