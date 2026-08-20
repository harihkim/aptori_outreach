# Opportunity Scoring

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines the first scoring model and the important separation between opportunity value and permission/appropriateness to promote.

## Opportunity model and scoring

The platform should retain component scores rather than only one opaque number. A single overall score is useful for sorting, but operators need to see the reasons behind it.

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
  "recommended_action": "helpful_reply_no_product",
  "reason": "Direct problem fit, but the user did not ask for vendor recommendations."
}
```

## Recommended implementation notes

- Store component scores and rationale, not only the aggregate score.
- Version the scoring formula and model schema so historical results remain explainable.
- Keep `promotion_fit` outside the overall opportunity score. A valuable conversation may warrant a product-free expert response.
- Add explicit uncertainty/confidence and allow an operator to override the recommended action.
- Use operator labels to calibrate weights after the MVP rather than treating the initial formula as permanent.
