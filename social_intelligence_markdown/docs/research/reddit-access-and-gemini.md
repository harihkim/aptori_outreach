# Reddit Access, Gemini and CUA Notes

> **Status:** Draft v0.4
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Captures the current assumptions that affect the MVP. These platform facts are time-sensitive and must be revalidated before production decisions.

## Reddit access and policy risk

Reddit is actively changing developer access and strengthening protections against scraping and spam. Current Reddit help documentation says Data API access requires approval, and Reddit announced in August 2026 that it plans to gradually restrict new public API requests and move third-party apps toward the Developer Platform. The MVP browser path should therefore be treated as a prototype/research retrieval provider, not as a permanent assumption for commercial production.

The platform should not attempt to evade technical restrictions or disguise abusive automation. If Reddit blocks or requires authentication for a page, the system should stop/escalate rather than bypass. For production, evaluate Reddit approval/commercial terms and the Developer Platform in parallel with the MVP.


> **Engagement boundary.** Reddit policy prohibits spam through automated posts/comments/direct messages. Our design does not automatically post anything. Human approval remains required, and the preferred demo leaves the final Reddit submit click to the human.

## Google/Reddit partnership: what it does and does not mean

Reddit announced an expanded Google partnership in February 2024 that gives Google programmatic access to public Reddit posts/comments through the Reddit Data API for Google products and services, including model-related uses. Reddit separately announced an OpenAI Data API partnership in May 2024, so the Google relationship is not exclusive.

There is no public Gemini API promise that developers inherit Google's private Reddit Data API feed. The public Gemini capabilities relevant to this project are Google Search grounding, URL Context, and Computer Use. Therefore, use Gemini-based Reddit discovery as a benchmarked public retrieval method rather than an assumed privileged integration.

## Exploratory observations before R0

The 2026-08-20 AI Studio experiments are useful for designing the benchmark but are not gate evidence. The raw result file is not a frozen corpus, contains model-authored malformed or non-canonical Reddit URLs, and lacks the blinded labels and repeated runs required by R0.

The observations worth carrying forward are:

- Google Search grounding returned semantically relevant Reddit candidates and, in some cases, substantial post text plus partial comments.
- Freshness varied: sub-hour discovery occurred in informal tests, while a newer post was missed and another query set skewed much older. This is not an indexing SLA.
- Model-authored URL fields were unreliable. Candidate identity must come from provider grounding/citation metadata followed by locator validation, never model confidence.
- In one controlled known-URL comparison, URL Context reported a Reddit bot challenge while Google Search grounding surfaced the core post content. URL Context remains a benchmark variant, not a mandatory stage.
- Direct retrieval observed inside ChatGPT does not prove identical access from the public OpenAI Responses API or from this project's network. OpenAI web search must be benchmarked as its own public-API variant.

R0 therefore needs age-bucket freshness metrics, exact-permalink recovery, grounding-source validation, post/comment completeness, and provider-specific failure evidence. Search-grounded partial content may support cheap screening, but high-value opportunities require a sufficiently complete deep read before drafting or review: the smoke-passed ADR-012 Obscura fetcher for the Internal Product, or an R0-graduated fetcher beyond that time-box.

## Working conclusion

For Gate R0, compare the ADR-012 Obscura variants, Gemini Google Search, the public OpenAI web-search API, and other approved search APIs independently from known-thread fetching through URL Context, Crawlee HTTP/Playwright, isolated browser-JSON experiments, and bounded CUA. ADR-012 provisionally selects Obscura + DuckDuckGo Lite discovery and Obscura known-thread fetching for the Internal Product; it gives them no automatic R0 credit. Keep CUA last rather than assuming it is the MVP default. Do not assume Gemini or OpenAI API customers inherit either company's private Reddit partnership access. Pursue official Reddit access as a separate workstream and implement it through the capability-specific `RedditDiscoverySource` and `RedditThreadFetcher` ports when available.
