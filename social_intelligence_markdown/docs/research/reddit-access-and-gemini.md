# Reddit Access, Gemini and CUA Notes

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Captures the current assumptions that affect the MVP. These platform facts are time-sensitive and must be revalidated before production decisions.

## Reddit access and policy risk

Reddit is actively changing developer access and strengthening protections against scraping and spam. Current Reddit help documentation says Data API access requires approval, and Reddit announced in August 2026 that it plans to gradually restrict new public API requests and move third-party apps toward the Developer Platform. The MVP browser path should therefore be treated as a prototype/research retrieval provider, not as a permanent assumption for commercial production.

The platform should not attempt to evade technical restrictions or disguise abusive automation. If Reddit blocks or requires authentication for a page, the system should stop/escalate rather than bypass. For production, evaluate Reddit approval/commercial terms and the Developer Platform in parallel with the MVP.


> **Engagement boundary.** Reddit policy prohibits spam through automated posts/comments/direct messages. Our design does not automatically post anything. Human approval remains required, and the preferred demo leaves the final Reddit submit click to the human.

## Google/Reddit partnership: what it does and does not mean

Reddit announced an expanded Google partnership in February 2024 that gives Google programmatic access to public Reddit posts/comments through the Reddit Data API for Google products and services, including model-related uses. Reddit separately announced an OpenAI Data API partnership in May 2024, so the Google relationship is not exclusive.

There is no public Gemini API promise that developers inherit Google's private Reddit Data API feed. The public Gemini capabilities relevant to this project are Google Search grounding, URL Context, and Computer Use. Therefore, use Gemini-based Reddit discovery as a benchmarked public retrieval method rather than an assumed privileged integration.

## Working conclusion

For the MVP, benchmark a layered public retrieval path: Google Search grounding for discovery, URL Context for cheap retrieval where sufficient, and CUA browser sessions for bounded extraction/fallback. Do not assume Gemini exposes Google's private Reddit Data API access. Pursue official Reddit access as a separate workstream and plug it into the same `RedditProvider` contract when available.
