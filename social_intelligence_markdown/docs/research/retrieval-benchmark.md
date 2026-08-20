# Retrieval Gate R0: Evaluation Protocol

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

R0 is a quantitative go/no-go gate for the Reddit-first product premise. No default provider is selected and no vertical-slice build is funded until a frozen evaluation demonstrates at least one compliant end-to-end route from campaign query to sufficiently complete normalized Conversation.

## Gate outcome

```text
PASS
  -> at least one compliant discovery + known-thread route meets every
     mandatory threshold
  -> build the prototype vertical slice

FAIL
  -> do not compensate with UI/content/media scope
  -> rework provider mix, access posture, query design, thresholds,
     or the Reddit-first product premise
  -> freeze a new evaluation version before rerunning
```

There is no subjective “demo operator likes eight results” override. A failed metric may be investigated, but changing the corpus, labels, thresholds, or scoring after seeing results creates a new evaluation version.

## Frozen artifacts

Create and commit this structure before comparative runs:

```text
retrieval-eval/
├── protocol.json
├── queries-2026-08.json
├── known-threads-2026-08.json
├── labels.jsonl
├── provider-configs/
│   ├── search.json
│   ├── url-context.json
│   ├── crawlee-http.json
│   ├── crawlee-playwright.json
│   ├── cua.json
│   └── asyncpraw.json
├── results/
│   └── <evaluation_id>/<provider_variant>.jsonl
└── report.md
```

`protocol.json` freezes evaluation ID, commit SHA, query/corpus hashes, metric definitions, thresholds, provider/library/browser/model versions, concurrency, throttling, retry budgets, labeling rules, and monetary conversion assumptions.

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
- explicit `not_found`, `auth_required`, `blocked`, or `rate_limited` examples where naturally observed.

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

- Approved Reddit Data API search/listings through Async PRAW, only if approved credentials exist.
- Approved web-search discovery with site-scoped Reddit queries.
- Bounded CUA Reddit search.

### Known-thread fetching

- Approved Async PRAW direct ID/URL fetch with frozen comment sort and `MoreComments` budget.
- Gemini URL Context.
- Crawlee `HttpCrawler`/`ParselCrawler` with fixed configuration.
- Crawlee `PlaywrightCrawler` with fixed browser/runtime configuration.
- Bounded CUA known-URL extraction.
- Optional experimental Crawlee `PydanticAiCrawler` as a separately reported extraction variant, never merged with the deterministic HTTP baseline.

Do not enable Crawlee adaptive method selection, proxy/fingerprint rotation, or identity/session rotation in R0.

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
request count and retries
rate-limit consumption
bytes and CPU/memory
browser minutes
model tokens and calls
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
- Pin library/model/browser versions and include the evaluated Git commit SHA.
- Keep immutable raw response/page artifacts under the approved retention policy so extraction can be replayed independently of live web changes.

## Gate authority

The engineering/product owner signs the frozen protocol before the first run and signs the R0 result. A passing score authorizes only the prototype vertical slice and the measured provider/configuration; it does not authorize production scale, new data uses, automatic posting, or unmeasured fallback behavior.

See [Reddit Retrieval Architecture](../architecture/retrieval.md), [Implementation Roadmap](../roadmap/roadmap.md), and the [Crawlee/PRAW research note](crawlee-praw-asyncpraw.md).
