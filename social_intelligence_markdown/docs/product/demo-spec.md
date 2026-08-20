# Reddit-First Prototype Demo

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The required demo proves the R0-approved Reddit acquisition path, opportunity intelligence, immutable drafting, complete human authorization, and browser handoff. Other networks, trend-to-content, and Higgsfield are optional expansion moments.

## Prerequisite

The demo configuration must be one that passed [Retrieval Gate R0](../research/retrieval-benchmark.md). A saved evidence corpus may make rehearsal repeatable, but it cannot be presented as live retrieval.

## Demo script

1. Open a Campaign with product context, audience, queries, communities, claims, and promotion posture.
2. Start a Discovery Run and show the configured discovery/fetch tiers plus live provenance and failures.
3. Show Candidates becoming immutable Retrieval Observations and normalized Conversations.
4. Open the Opportunity Inbox and compare raw Candidate count with the small ranked result set.
5. Select an Opportunity; show the source Conversation, evidence, factor scores, deterministic overall score, rationale, and recommended action.
6. Generate a response candidate and create Draft Version 1.
7. Edit one phrase to create Draft Version 2; show the immutable version diff.
8. Select the Actor Account, exact Reddit Destination, action type, and any finalized media.
9. Approve Version 2 with an explicit expiry; show the Approval and Approved Artifact digest.
10. Start Publish Preparation using only `approval_id`.
11. CUA opens the exact Reddit composer and fills the exact approved artifact.
12. Stop at `READY_FOR_HUMAN`; the human owns final submit.
13. From an MCP client, run `list_campaigns`, `search_opportunities`, and `get_opportunity` to prove the same headless read services.

## Safety proof moments

- Attempting to prepare Draft Version 1 after Version 2 was approved fails.
- Changing text, media, Actor Account, action, or Destination is unavailable in the preparation request.
- Replaying a consumed Approval fails.
- The browser automation surface contains no final-submit capability.

## Fallback strategy

| Failure | Allowed fallback |
|---|---|
| Live discovery provider outage | Use an R0-recorded real URL set and clearly label discovery as replayed evidence |
| One fetch tier is technically incomplete | Use only the explicit R0-approved escalation policy and display both observations |
| Access block/authentication/CAPTCHA/rate limit | Stop and show the classified failure; do not rotate around it |
| Browser preparation session fails | Show the failed preparation evidence; do not bypass authorization or silently consume again |
| Model output is weak | Use the saved labeled Conversation and demonstrate regenerate/edit/version/review openly |

## Success statement

One Campaign produces noisy real Reddit Candidates; the product preserves retrieval evidence, reduces the set to credible explainable Opportunities, creates immutable Draft Versions, captures human authorization for the complete outbound action, and prepares the exact Reddit composer without submitting it.

## Optional expansion moment

If already built and stable, demonstrate a repeated theme becoming an original content Draft and Higgsfield media brief/asset. This is not part of prototype acceptance and must use the same immutable version and scoped approval model.
