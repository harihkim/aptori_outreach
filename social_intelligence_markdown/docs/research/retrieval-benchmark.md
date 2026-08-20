# Reddit Retrieval Benchmark

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

An empirical benchmark is required before choosing the default retrieval provider. Coverage, freshness, extraction completeness, cost and failure modes matter more than architectural elegance.

## Retrieval benchmark plan

The retrieval strategy is the main technical uncertainty. Run a reproducible benchmark instead of selecting a provider based on assumptions.

| **Dimension**       | **Metric**                                                                             |
|---------------------|----------------------------------------------------------------------------------------|
| Coverage            | Unique conversations found; unique relevant conversations; overlap among methods.      |
| Freshness           | Share of results from \<24h, \<7d, \<30d.                                              |
| Thread completeness | Submission body found; comments captured; top-comment coverage; deleted/blocked cases. |
| Quality             | Manual relevance rate before/after AI filter.                                          |
| Reliability         | Success rate, timeouts, blocks, navigation failures, malformed extraction.             |
| Cost                | Gemini search/context/computer-use calls, model tokens, browser runtime.               |
| Latency             | Median and p95 per query and per fetched thread.                                       |
| Operational risk    | Need for login/session, brittleness to DOM changes, maintenance burden.                |

### Benchmark queries

- A broad product keyword with high noise.

- A narrow pain-point phrase with clear solution-seeking intent.

- A competitor comparison query.

- A recent/trending technical topic.

- A subreddit-scoped query.

### Methods to compare

- Gemini Google Search grounding with site:reddit.com queries.

- Gemini Search to URL discovery followed by URL Context.

- CUA direct Reddit search/navigation.

- CUA fetch of known Reddit URLs found by another method.

- Later: approved Reddit Data API/Developer Platform provider as a production comparison.

## Output artifact

Commit benchmark results as dated data (CSV/JSON plus a short Markdown report) so changes in Google indexing, Reddit UI behavior or browser-agent performance can be detected over time.
