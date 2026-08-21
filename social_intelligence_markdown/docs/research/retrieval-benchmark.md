# Retrieval Gate R0: Evaluation Protocol

> **Status:** Draft v0.4
> **Canonical:** Yes - this Markdown documentation is the source of truth.

R0 is the quantitative go/no-go gate for graduating a Reddit retrieval route beyond a dated exception and for any future external use. [ADR-012](../adr/012-time-boxed-internal-retrieval-selection.md) separately authorizes exact provisional variants for the project-team-operated Internal Product after a smaller frozen smoke gate. That exception does not select an R0 winner, modify these thresholds, or count as an R0 pass.

## Gate outcome

```text
PASS
  -> at least one compliant discovery + known-thread route meets every
     mandatory threshold
  -> graduate the measured provider route beyond the time-box
  -> make it eligible for future external-use review

FAIL
  -> do not claim provider graduation or external readiness
  -> rework provider mix, access posture, query design, thresholds,
     or the Reddit-first product premise
  -> freeze a new evaluation version before rerunning
```

There is no subjective “demo operator likes eight results” override. A failed metric may be investigated, but changing the corpus, labels, thresholds, or scoring after seeing results creates a new evaluation version.

## ADR-012 prototype smoke protocol

This smoke gate is deliberately smaller than R0. It permits progress on the Internal Product only and must be frozen before scoring.

**Discovery:** run 10 representative campaign queries through `ObscuraDuckDuckGoLiteDiscoverySource`. At least 8 of 10 must return one or more canonical Reddit thread candidates; every emitted candidate must be a valid canonical Reddit thread URL; empty, blocked, parse, and transport outcomes must be explicit.

**Known-thread fetching:** run 10 varied frozen threads through `ObscuraRedditThreadFetcher` twice. At least 8 of 10 must succeed in each run. Successful normalized trees must have zero duplicate comments and zero missing parent references. Any unresolved Reddit `more` node is `INCOMPLETE`. Replaying retained raw evidence must reproduce the identical normalized-content hash.

The authorized access class is anonymous standard Obscura only. Any account/session requirement, CAPTCHA continuation, stealth setting, residential proxy, proxy rotation, or identity rotation fails the smoke boundary. There is no hidden fallback; an operator may explicitly rerun another configured variant and persist it as a separate observation.

## Frozen artifacts

Create and commit this structure before comparative runs:

```text
retrieval-eval/
├── protocol.json
├── queries-2026-08.json
├── known-threads-2026-08.json
├── labels.jsonl
├── provider-configs/
│   ├── gemini-google-search.json
│   ├── openai-web-search.json
│   ├── brave-search-api.json
│   ├── obscura-duckduckgo-lite.json
│   ├── duckduckgo-html.json
│   ├── url-context.json
│   ├── crawlee-http.json
│   ├── crawlee-playwright.json
│   ├── apify-<actor>-<build>.json
│   ├── opencli-browser-json.json
│   ├── rdt-cli-cookie-json.json
│   ├── obscura-reddit-thread.json
│   ├── cua.json
│   └── asyncpraw.json
├── results/
│   └── <evaluation_id>/<provider_variant>.jsonl
└── report.md
```

Only create configuration files for variants actually admitted to that evaluation; the tree above is a catalog, not mandatory scope. `protocol.json` freezes evaluation ID, commit SHA, query/corpus hashes, metric definitions, thresholds, provider/Actor/library/browser/model versions, access-identity class, egress environment, credential scope, proxy policy, concurrency, throttling, retry and spend budgets, labeling rules, and monetary conversion assumptions.

## Evaluation sets

### Discovery queries

Freeze at least 35 queries: five examples from each campaign pattern.

```text
broad/high-noise keyword
narrow pain point
solution-seeking query
competitor comparison
technical question
subreddit-specific query
recent/trending topic
```

Queries must span at least three realistic product/campaign contexts and include negative controls expected to produce few or no useful opportunities.

### Known-thread corpus

Freeze at least 60 real URLs, stratified across:

- self, link, and media submissions;
- ordinary, high-comment, and deep threads;
- deleted/removed comments and locked threads;
- different supported Reddit page variants;
- explicit `not_found`, `auth_required`, `forbidden`, `blocked`, `rate_limited`, `parse_failed`, `upstream_unavailable`, or `policy_disallowed` examples where naturally observed.

Do not bypass quarantines, CAPTCHAs, authentication gates, blocks, or other access controls to populate the corpus.

## Labeling protocol

1. Pool and deduplicate candidate URLs from all discovery methods.
2. Hide provider identity and ranking from labelers.
3. Two humans independently assign relevance grade `0..3`, useful-opportunity `yes/no`, freshness validity, and exclusion reason.
4. Reconcile disagreements before the label file is frozen.
5. For known threads, record expected submission fields and the top ten ordinarily visible comments under the frozen sort/collection rule.
6. Hash and commit `labels.jsonl` before comparing scoring or provider-ranking variants.

Relevance grade:

| Grade | Meaning |
|---|---|
| 0 | irrelevant or prohibited/sensitive |
| 1 | topically related but no useful action |
| 2 | credible monitoring or content signal |
| 3 | credible opportunity for a helpful response or high-value content |

Grades 2-3 count as relevant. Grade 3 with a permitted recommended action counts as a useful opportunity.

## Provider variants

### Discovery

- Provisional `ObscuraDuckDuckGoLiteDiscoverySource`, evaluated as its exact pinned browser/runtime and DuckDuckGo Lite page-surface configuration; ADR-012 grants no automatic R0 credit.
- Approved Reddit Data API search/listings through Async PRAW, only if approved credentials exist.
- Approved web-search discovery with site-scoped Reddit queries; each concrete API and plan is a separate variant.
- Brave Search API only as an authenticated subscription-token variant with captured rate-limit headers.
- DuckDuckGo HTML or Lite only as separately reviewed experimental page-surface variants, not as a supported keyless API.
- An exact pinned Apify Actor/build only when its input, output, proxy configuration, permissions, pricing and maximum spend are frozen.
- Optional OpenCLI logged-in-browser JSON discovery in an isolated read-only adapter.
- Optional `rdt-cli` cookie HTTP as a quarantined high-policy-risk diagnostic whose results cannot satisfy the policy threshold without explicit approval.
- Bounded CUA Reddit search.

### Known-thread fetching

- Provisional `ObscuraRedditThreadFetcher`, evaluated using anonymous standard navigation and the exact pinned in-origin structured-fetch extractor; ADR-012 grants no automatic R0 credit.
- Approved Async PRAW direct ID/URL fetch with frozen comment sort and `MoreComments` budget.
- Gemini URL Context.
- Crawlee `HttpCrawler`/`ParselCrawler` with fixed configuration.
- Crawlee `PlaywrightCrawler` with fixed browser/runtime configuration.
- An exact pinned Apify Actor/build when admitted under the same configuration and policy rules as discovery.
- Optional OpenCLI logged-in-browser JSON fetch in an isolated read-only adapter.
- Optional `rdt-cli` cookie HTTP diagnostic under the same policy restriction as discovery.
- Bounded CUA known-URL extraction.
- Optional experimental Crawlee `PydanticAiCrawler` as a separately reported extraction variant, never merged with the deterministic HTTP baseline.

Agent Reach itself is not a provider variant: it installs/routes to upstream tools but does not implement the project's typed provider, evidence or persistence contracts. Do not expose Agent Reach, OpenCLI, or `rdt-cli` as an unrestricted shell capability. Do not enable Crawlee adaptive method selection, proxy/fingerprint rotation, or identity/session rotation in R0.

## Metrics

### Discovery quality

```text
Precision@5
Precision@10
NDCG@10
unique relevant conversations
unique useful opportunities
provider overlap
freshness distribution
negative-control false-positive rate
```

### Thread completeness

```text
known-thread extraction success
submission title/body/metadata completeness
top-10 comment recall
comment-depth coverage
deleted/removed-content handling
explicit terminal failure classification
same-snapshot normalization hash stability
```

### Operations

```text
domain jobs and queries
provider attempts and retries
top-level API calls and browser navigations
browser/network subrequests and transferred bytes
returned, normalized and deduplicated item counts
rate-limit consumption
bytes and CPU/memory
browser minutes
model tokens and calls
Actor compute/storage/events, proxy traffic and other billable units
median and p95 latency
failure and block rate
cost/query
cost/complete thread
cost/useful opportunity surfaced
```

`cost/useful opportunity surfaced` is the primary economic metric because retrieval exists to buy actionable signal rather than raw URLs.

## Mandatory R0 thresholds

At least one compliant composed route must satisfy all of these over three dated runs:

| Dimension | Pass threshold |
|---|---|
| Policy/access | Documented permission posture for every provider in the route; zero bypass behavior or unapproved credentials |
| Discovery quality | Aggregate `Precision@5 >= 0.70`, `Precision@10 >= 0.60`, and `NDCG@10 >= 0.70` |
| Query-family floor | No query family has `Precision@10 < 0.40` |
| Useful yield | Median of at least three unique useful opportunities per query family across the frozen set |
| Known-thread success | At least 90% of eligible, ordinarily accessible corpus URLs produce a normalized Conversation |
| Submission completeness | At least 95% of successful fetches contain required submission body/metadata fields |
| Comment completeness | At least 80% recall over the frozen top-ten ordinarily visible comments |
| Failure semantics | At least 95% of all terminal cases receive the correct explicit failure class; zero silent access-control fallthrough |
| Rate and budget enforcement | Zero quota multiplication by identity/provider rotation; reset/`Retry-After` honored; every variant remains within frozen request, concurrency and spend caps |
| Deterministic replay | 100% identical normalized hashes when replaying the same immutable raw artifact and extractor version |
| Reliability | At least 90% route completion across the three repeated runs |
| Latency | End-to-end p95 no more than 120 seconds per query and 60 seconds per known-thread fetch for the selected default tiers |
| Economic ceiling | Total retrieval cost no more than USD 1.00 per useful opportunity surfaced, using frozen cost assumptions |
| Evidence | 100% of attempts, including failures, produce a Retrieval Observation with configuration and provenance |

The USD 1.00 ceiling is a prototype funding threshold, not a permanent unit-economics claim. Changing it requires a new protocol version before running providers.

## Reporting rules

- Report every provider variant, including failures; do not publish only the selected route.
- Separate discovery and known-thread results so a strong search method is not credited with another fetcher's completeness.
- Show aggregate and per-query-family metrics with confidence intervals where sample size permits.
- Report provider overlap and incremental unique useful opportunities.
- Distinguish technical failure, policy stop, access denial, and irrelevant result.
- Report logical jobs, provider attempts, network activity, returned items and billable operations separately; never infer HTTP-request volume from page or screenshot counts.
- Pin library/model/browser versions and include the evaluated Git commit SHA.
- For managed Actors and session-backed tools, record exact source/build revisions, input/output schema, credential class, proxy setting, permissions and dependency image digest.
- Keep immutable raw response/page artifacts under the approved retention policy so extraction can be replayed independently of live web changes.

## Gate authority

The engineering/product owner signs the frozen protocol before the first run and signs the R0 result. A passing score graduates only the measured provider/configuration for the evaluated use; it does not authorize production scale, new data uses, automatic posting, or unmeasured fallback behavior. ADR-012 is a separate dated internal-only authority and expires into mandatory reassessment on 2026-09-20.

See [Reddit Retrieval Architecture](../architecture/retrieval.md), [Implementation Roadmap](../roadmap/roadmap.md), [ADR-012](../adr/012-time-boxed-internal-retrieval-selection.md), the [Crawlee/PRAW research note](crawlee-praw-asyncpraw.md), [Agent Reach assessment](agent-reach.md), and [third-party scraping-claims assessment](third-party-scraping-claims.md).
