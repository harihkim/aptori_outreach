# User Flows and UX

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines the operator workflow from campaign creation through opportunity triage, drafting, content creation and review.

## Core user journeys

### Create a campaign

1. Describe the product/company and target audience.

2. Add keywords, pain points, competitor names, product capabilities, and optional subreddits.

3. Set promotion posture: expertise-first, balanced, or high-intent-only product mentions.

4. Provide approved facts/claims and prohibited claims.

5. Choose discovery cadence and lookback window.

### Discover and triage opportunities

6. Run discovery using the configured Reddit retrieval providers.

7. Normalize submissions/comments/threads and deduplicate URLs/conversations.

8. Apply cheap filters before expensive model calls.

9. Analyze relevant items for intent, pain, persona, product fit, replyability, freshness, and promotion fit.

10. Show high-value items in the Opportunity Inbox with a short explanation of why each matters.

### Draft, review, and publish

11. Open an opportunity and inspect the source thread/context.

12. Ask for one or more response approaches and a draft.

13. Edit or regenerate the draft.

14. Approve the exact text. The platform stores approver, timestamp, draft ID, and content hash.

15. For the safest demo mode, browser automation fills the Reddit composer and stops before the final click. A future approved publish mode may click only after a valid approval record is verified.

### Turn conversations into original content

16. Cluster repeated questions and pains across conversations.

17. Select a theme or allow the system to recommend rising themes.

18. Generate original platform-specific content from approved company knowledge and aggregated market signals.

19. Generate a media brief, then image/video assets via Higgsfield where appropriate.

20. Queue the package for review; do not publish automatically.

## Information architecture and screens

| **Screen**     | **Purpose**                               | **Key elements**                                                                                               |
|----------------|-------------------------------------------|----------------------------------------------------------------------------------------------------------------|
| Overview       | Daily operating summary                   | High-intent opportunities, conversations worth joining, emerging themes, drafts awaiting approval, media jobs. |
| Campaigns      | Define targeting and brand context        | Keywords, subreddits, ICP, competitors, positioning, approved/prohibited claims, cadence.                      |
| Opportunities  | Rank and triage conversations             | Score, source, age, intent, topic, author/community, rationale, suggested action, filters.                     |
| Conversation   | Understand source context                 | Post body, selected comments, thread summary, source link, retrieval provenance, analysis, draft actions.      |
| Content Studio | Create original posts from market insight | Theme clusters, content angles, platform variants, citations/provenance, drafts.                               |
| Media Studio   | Create or manage media assets             | Higgsfield prompts/jobs, image/video previews, aspect ratios, asset history.                                   |
| Approvals      | Human control point                       | Pending drafts, diffs, approver, exact text hash, approve/reject/edit/open-in-Reddit.                          |
| Analytics      | Learn from feedback                       | Relevant/not relevant, draft accepted, posted, responses, topic trends, precision metrics.                     |

## UX rules for safe, useful engagement

- Every draft screen displays the original source and a concise rationale.

- The primary action is Review, not Auto-post.

- The system should recommend "do not respond" when a conversation is a poor fit, old, sensitive, hostile, or overly promotional.

- Subreddit/community rules should be visible when known; manual rules can be added to campaign configuration.

- Draft generation should favor answering the user first and mentioning the product only when justified by context.

- When the model is uncertain about a factual claim, it should omit the claim or flag it for review.

- For external-agent usage, sensitive actions return a review/approval requirement rather than executing.
