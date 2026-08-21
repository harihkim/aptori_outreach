# User Flows and UX

> **Status:** Draft v0.3
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The prototype operating flow runs from Campaign definition to an exact, human-authorized Reddit composer preparation. Content/media workflows are expansion.

## Prototype flow

### Create a Campaign

1. Describe the product/company and target audience.
2. Add keywords, pain points, competitor names, product capabilities, and optional subreddits.
3. Set promotion posture: expertise-first, balanced, or high-intent-only product mentions.
4. Provide approved facts/claims and prohibited claims.
5. Choose lookback/cadence within the exact ADR-012 provisional configuration or a later R0-graduated configuration.

### Discover and triage

6. Start a Discovery Run and show the exact discovery/fetch methods being used.
7. Persist Candidates and immutable Retrieval Observations, including failures and completeness.
8. Normalize and deduplicate source items deterministically.
9. Apply cheap deterministic filters before versioned Pydantic AI analysis.
10. Compute the overall Opportunity score in application code.
11. Show a ranked Opportunity Inbox with source evidence, provider provenance, factor scores, rationale, age, and recommended action.

### Draft and version

12. Open an Opportunity and inspect the source Conversation and relevant comments.
13. Generate one or more typed response candidates.
14. Select a candidate, creating Draft Version 1.
15. Edit or regenerate; each operation creates a new immutable Draft Version and preserves history/diff.

### Review and prepare

16. Select the exact Draft Version, any finalized media assets, Actor Account, action type, and Destination.
17. Review the complete action summary and expiration.
18. Approve, producing an Approval and immutable Approved Artifact.
19. Request Publish Preparation by `approval_id` only.
20. The system revalidates and atomically consumes the single-use artifact.
21. CUA fills the correct Reddit composer with the exact approved content and returns `READY_FOR_HUMAN`.
22. The human owns the final submit action outside the prototype's callable capabilities.

If the human edits content, changes media/account/destination/action, or the Approval expires/is revoked, the preparation path closes until a new Approval is created.

## Prototype screens

| Screen | Purpose | Key elements |
|---|---|---|
| Campaigns | Configure research and brand constraints | source/query settings, ICP, keywords, communities, competitors, claim policy |
| Discovery Run | Make retrieval evidence visible | method plan, progress, Candidates, observations, explicit failure classes, cost/latency |
| Opportunities | Rank and triage Conversations | score, age, topic, rationale, action, source and provider provenance, filters |
| Conversation | Understand source context | normalized thread, selected comments, raw observation references, analysis, draft actions |
| Draft | Create immutable revisions | version timeline, diff, model/human provenance, safety flags, regenerate/edit |
| Approval | Human authorization point | exact text/media, Actor Account, action, Destination, expiry, artifact digest preview |
| Preparation | Human handoff | validation state, destination, browser progress, `READY_FOR_HUMAN`, no submit control |

## UX rules

- The primary action is Review, never Auto-post.
- Every Draft Version displays the source Conversation, claims/uncertainties, and version provenance.
- Approval shows the full action scope, not only text.
- Destination and Actor Account changes are visible as authorization-significant diffs.
- Expired, revoked, consumed, or superseded-by-context approvals are clearly non-runnable.
- The product can recommend `ignore` or `monitor`; it does not force a response.
- Uncertain factual claims are omitted or explicitly flagged for human review.
- Retrieval access/policy failures are surfaced honestly rather than hidden behind another browser attempt.
- Streamed LLM text is visually provisional until a final validated Draft Version exists.
- External agents receive canonical data or a review requirement, never approval authority.

## Expansion flow

After the vertical slice is validated, repeated Conversations may be clustered into themes, turned into original content packages, paired with Higgsfield media, and queued for the same Draft Version and action-scoped review model. Expansion does not create a weaker approval path.

See [Product Specification](product-spec.md), [Human Approval and Security](../architecture/approval-security.md), and [REST and SSE API](../api/rest-api.md).
