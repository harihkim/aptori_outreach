# Opportunity Scoring

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines the first scoring model and the important separation between opportunity value and permission/appropriateness to promote.

## Opportunity model and scoring

The versioned Pydantic AI Analysis task produces validated semantic factors, rationale, confidence, and a recommended action. Application code computes the aggregate Opportunity score from the frozen formula; the model does not directly set ranking state.

| **Signal**           | **Meaning**                                                              | **Example weight** |
|----------------------|--------------------------------------------------------------------------|--------------------|
| Relevance            | Semantic fit with configured problem/product space.                      | 0.30               |
| Pain / buying intent | Evidence of an active problem, evaluation, or solution-seeking behavior. | 0.25               |
| Replyability         | Can the company contribute something useful without forcing promotion?   | 0.15               |
| Author/community fit | Persona/community relevance and discussion norms.                        | 0.10               |
| Engagement velocity  | Conversation is active enough to justify timely participation.           | 0.10               |
| Freshness            | Newer discussions are usually more actionable.                           | 0.10               |


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

## Recommended implementation notes

- Store component scores and rationale, not only the aggregate score.
- Version the scoring formula and model schema so historical results remain explainable.
- Persist the Model Run separately from the deterministic scoring-formula version.
- Reject out-of-range or internally inconsistent typed factors before calculating the score.
- Keep `promotion_fit` outside the overall opportunity score. A valuable conversation may warrant a product-free expert response.
- Add explicit uncertainty/confidence and allow an operator to override the recommended action.
- Calibrate weights against a frozen labeled evaluation rather than changing them after inspecting one demo result set.
