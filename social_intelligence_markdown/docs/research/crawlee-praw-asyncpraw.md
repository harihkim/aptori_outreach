# Crawlee, PRAW and Async PRAW for Reddit Retrieval

> **Status:** Research note  
> **Researched:** 2026-08-20  
> **Sources:** Official project repositories/documentation, PyPI metadata and Reddit policy/documentation only. Revalidate Reddit access and terms before implementation.

## Conclusion

Add two distinct provider paths to the retrieval spike:

1. Use **Async PRAW**—not synchronous PRAW—for the future approved Reddit Data API provider. It matches the project's async `RedditProvider` contract and FastAPI/worker runtime while exposing essentially the same Reddit feature set as PRAW.
2. Benchmark **Crawlee HTTP/Parsel and Crawlee Playwright as explicit, deterministic known-URL fetch tiers before CUA**. Crawlee can make queueing, retries, throttling, snapshots and browser lifecycle more reliable; it is not a Reddit-native provider and should not replace official API access.

The intended ladder becomes:

```text
Discovery
├── approved Reddit Data API via Async PRAW       preferred when authorized
└── approved search provider                      public URL discovery

Known Reddit URL
├── approved Reddit Data API via Async PRAW       preferred when authorized
├── Crawlee HTTP/Parsel                           cheap deterministic fetch experiment
├── Crawlee Playwright                            deterministic browser escalation
└── CUA                                           semantic/UI fallback only

Every successful path
  -> immutable raw observation
  -> deterministic normalization
  -> source-ID dedupe/upsert
  -> bounded Pydantic AI analysis
```

> **Access boundary:** installing Crawlee, PRAW or Async PRAW grants no Reddit API access, commercial-use permission, scraping permission or exemption from Reddit policy. Reddit says its Data API is for approved developers, requires registered OAuth and a truthful descriptive User-Agent, and commercial use requires prior permission and a contract. A library is an implementation mechanism only. ([Developer Platform and accessing Reddit data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data), [Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [Data API Terms](https://redditinc.com/policies/data-api-terms))

## Project health and fit

| Project | Current stable release | Runtime and license | Best role here | Main limitation |
|---|---|---|---|---|
| [Crawlee for Python](https://github.com/apify/crawlee-python) | 1.9.2, released 2026-08-17; frequent August releases indicate active maintenance | Python 3.10+, asyncio-native, Apache-2.0 | Generic queued HTTP and Playwright retrieval for known URLs; reproducible crawl evidence | No Reddit OAuth, Reddit-native models, stable content identity or policy authorization |
| [PRAW](https://github.com/praw-dev/praw) | 8.0.3, released 2026-08-12 | Python 3.10+, synchronous `requests` runtime, BSD-2-Clause | Synchronous scripts or applications | Blocks an async worker unless isolated; `Reddit` instances are not thread-safe |
| [Async PRAW](https://github.com/praw-dev/asyncpraw) | 8.0.3, released 2026-08-12 | Python 3.10+, asyncio/`aiohttp`, BSD-2-Clause | Approved read-only Reddit API provider | Still depends on Reddit approval, OAuth, API coverage and rate limits |

The version, Python and license data come from the projects' published package metadata and release history. Crawlee is classified Production/Stable; both PRAW packages shipped matching 8.0.3 maintenance releases. ([Crawlee on PyPI](https://pypi.org/project/crawlee/), [PRAW releases](https://github.com/praw-dev/praw/releases), [Async PRAW releases](https://github.com/praw-dev/asyncpraw/releases))

## PRAW and Async PRAW

### Capabilities

PRAW and Async PRAW are object-oriented wrappers over Reddit's API. They cover subreddit search and listings, direct submission lookup by ID/URL, submission/comment metadata, comment forests, subreddit rules, streams and Reddit write operations. The project should expose only the read subset through `RedditProvider`; the existence of reply/submit methods is not a reason to combine retrieval and publishing credentials or interfaces. The PRAW maintainers describe Async PRAW as the official async version with similar usage and the same features. ([PRAW repository](https://github.com/praw-dev/praw), [Async PRAW repository](https://github.com/praw-dev/asyncpraw), [PRAW subreddit search](https://praw.readthedocs.io/en/stable/code_overview/other/subreddit.html#praw.models.Subreddit.search))

Useful official-provider operations are:

- `discover`: subreddit/all search plus `new`, `hot`, `top` or other approved listings.
- `fetch_thread`: load a submission by stable Reddit ID or URL, set comment sort/limit before loading, and deliberately resolve or discard `MoreComments` placeholders.
- `healthcheck`: verify OAuth mode, call a minimal read endpoint, and report current rate-limit headers.

This API path is more semantically stable than HTML parsing: it supplies Reddit IDs and structured objects rather than DOM selectors. It is not complete or unlimited. Most Reddit listings expose at most 1,000 items, streams can miss items on high-volume feeds, and expanding each `MoreComments` placeholder costs another API request. The submission comment count can also differ from retrievable comments because it includes deleted, removed and spam comments. ([ListingGenerator](https://praw.readthedocs.io/en/stable/code_overview/other/listinggenerator.html), [Subreddit streams](https://praw.readthedocs.io/en/stable/code_overview/other/subredditstream.html), [Async PRAW comment extraction](https://asyncpraw.readthedocs.io/en/stable/tutorials/comments.html))

### Authentication and access

Both libraries support Reddit's script, web and installed OAuth application types, including application-only read-only flows and user-authorized flows. The library documentation assumes an already registered Reddit application; that assumption is not authorization for this product. ([PRAW OAuth](https://praw.readthedocs.io/en/stable/getting_started/authentication.html), [Async PRAW OAuth](https://asyncpraw.readthedocs.io/en/stable/getting_started/authentication.html))

For this project, if Reddit approves the use case:

- Prefer the least-privileged approved application-only/read-only flow for research where possible.
- Give the retrieval provider no account password and no write scopes.
- Keep any later publishing OAuth client, refresh token and process separate from retrieval.
- Use a unique truthful User-Agent in Reddit's documented format.
- Treat access approval, commercial permission, allowed data processing/retention and any Developer Platform migration as deployment prerequisites, not library configuration.

Reddit's current technical guidance requires registered OAuth, documents 100 queries per minute per OAuth client ID for eligible free access averaged over a ten-minute window, and warns that unidentified traffic may be throttled or blocked. These are current public defaults, not a capacity promise for an approved commercial contract. ([Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki))

### Rate limiting and worker topology

Both wrappers inspect Reddit's `X-Ratelimit-*` response headers and delay requests. Separate API-level rate-limit messages can cause a bounded sleep controlled by `ratelimit_seconds`; longer waits raise `RedditAPIException`. ([PRAW rate limits](https://praw.readthedocs.io/en/stable/getting_started/ratelimits.html), [Async PRAW rate limits](https://asyncpraw.readthedocs.io/en/stable/getting_started/ratelimits.html))

That handling is local to a client instance. The maintainers warn that running more than roughly a dozen concurrent instances can exceed limits because each instance only estimates what the others are doing. The application therefore still needs credential-scoped admission control and telemetry across workers; it must not create clients or rotate identities to multiply quota. ([PRAW multiple instances](https://praw.readthedocs.io/en/stable/getting_started/multiple_instances.html), [Async PRAW multiple instances](https://asyncpraw.readthedocs.io/en/stable/getting_started/multiple_instances.html))

### Async PRAW versus PRAW

Choose **Async PRAW** for this architecture:

- The provider protocol is already async and retrieval is I/O-bound.
- Async iterators fit bounded concurrent thread fetches without blocking worker event loops.
- Its async context manager closes the underlying `aiohttp` session cleanly.
- PRAW itself recommends Async PRAW in asyncio environments.

PRAW remains a sensible choice for standalone synchronous scripts, but wrapping it in a thread pool adds lifecycle and cancellation complexity. PRAW also documents that `Reddit` instances are not thread-safe because they depend on `requests.Session`. ([PRAW async-environment guidance](https://praw.readthedocs.io/en/stable/getting_started/multiple_instances.html), [Async PRAW 8 migration](https://asyncpraw.readthedocs.io/en/stable/package_info/asyncpraw8_migration.html))

Use one long-lived Async PRAW client per approved credential context, close it during worker shutdown, and put a project adapter around it. Do not allow PRAW/Async PRAW model objects to escape into domain services; map them immediately into the canonical `Candidate` and `RedditThread` schemas with retrieval provenance.

### Data-governance limitation

Reddit requires removal of stored content deleted from Reddit and strongly recommends routinely deleting stored user data/content within 48 hours; retained deleted content remains prohibited even if de-identified. The Data API Terms also restrict use and retention to the approved use case. The official provider therefore needs a refresh/tombstone deletion process and an approved retention policy, not just an ingest job. ([Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [Data API Terms](https://redditinc.com/policies/data-api-terms))

## Crawlee

### What it provides

Crawlee is an asyncio-native crawling framework that embeds as ordinary Python code. Its common crawler runtime supplies request routing, automatic retries, autoscaled concurrency, session/proxy management, statistics and storage. The relevant crawler choices are: ([Crawlee architecture](https://crawlee.dev/python/docs/guides/architecture-overview), [BasicCrawler API](https://crawlee.dev/python/api/class/BasicCrawler))

- `HttpCrawler`: raw body/headers and any content type, with minimal parsing overhead.
- `ParselCrawler`: deterministic CSS/XPath extraction for stable layouts.
- `BeautifulSoupCrawler`: tolerant parsing for malformed server-rendered HTML.
- `PlaywrightCrawler`: real Chromium/Firefox/WebKit browser rendering for client-side pages; slower and more resource-intensive than HTTP.
- `AdaptivePlaywrightCrawler`: learns whether HTTP or browser retrieval is sufficient.

For Gate 0, prefer a fixed `HttpCrawler`/`ParselCrawler` attempt followed by an explicit `PlaywrightCrawler` attempt. Do not use the adaptive crawler in the benchmark's ground-truth path: its learned HTTP/browser choice can change between runs and obscure provider comparisons. ([HTTP crawlers](https://crawlee.dev/python/docs/guides/http-crawlers), [Playwright crawler](https://crawlee.dev/python/docs/guides/playwright-crawler), [Adaptive Playwright crawler](https://crawlee.dev/python/docs/guides/adaptive-playwright-crawler))

### Queue, deduplication, sessions and storage

Crawlee fills several pieces currently missing between URL discovery and CUA:

- `RequestQueue` tracks pending/in-progress/handled requests and deduplicates by `Request.unique_key`; named queues can persist across runs.
- `SessionPool` tracks cookies, custom session data, age/use/error state and optional persistence.
- `ProxyConfiguration` supports rotation, sticky session-to-proxy mapping and tiers.
- `AutoscaledPool` adjusts concurrent async tasks to CPU/memory; `ConcurrencySettings` can cap concurrency and tasks per minute.
- `ThrottlingRequestManager` provides opt-in per-domain throttling, `Retry-After` handling and `robots.txt` crawl-delay support.
- `Dataset`, `KeyValueStore` and `RequestQueue` support memory and filesystem storage. Optional SQL storage supports SQLite/PostgreSQL/MySQL/MariaDB, and Redis supports cross-process access; the current documentation marks both SQL and Redis clients experimental.

([Storages](https://crawlee.dev/python/docs/guides/storages), [Storage clients](https://crawlee.dev/python/docs/guides/storage-clients), [Session](https://crawlee.dev/python/api/class/Session), [Proxy configuration](https://crawlee.dev/python/api/class/ProxyConfiguration), [Scaling](https://crawlee.dev/python/docs/guides/scaling-crawlers), [Request throttling](https://crawlee.dev/python/docs/guides/request-throttling))

These are crawl mechanics, not domain semantics:

- URL `unique_key` is not Reddit conversation identity. Canonical identity remains the Reddit post fullname/ID; use a time-bucketed/custom request key when a later observation is intentional.
- Crawlee storage should hold transient queues and raw Gate-0 evidence, while PostgreSQL remains the system of record for campaigns, conversations, provenance and jobs.
- A retried handler can run more than once. Snapshot writes and application upserts must be idempotent.
- Autoscaling changes completion order; browser state, retries and live pages change observations. Crawlee makes orchestration reproducible, not the web deterministic.

### Policy-safe configuration

Crawlee exposes proxy rotation, fingerprinting and retry-on-blocked features intended for generic web scraping. They must **not** be used to evade Reddit rate limits, blocks, login requirements or CAPTCHAs. For Reddit experiments:

- Set conservative fixed concurrency and per-domain throughput.
- Enable `respect_robots_txt_file=True` for web crawling and record skipped URLs.
- Classify 401/403/429 explicitly; stop/escalate rather than rotate sessions or identities around them.
- Disable proxy/fingerprint rotation as a Reddit access strategy.
- Save the final URL, status, headers, method, timestamp and failure reason.

Crawlee's ability to fetch a page does not establish permission to crawl or use its content. Reddit's Data API Terms prohibit circumventing controls and exceeding limits; use of non-API web retrieval still requires a separate policy review. ([Crawlee robots.txt support](https://crawlee.dev/python/docs/examples/respect-robots-txt-file), [Crawlee error handling](https://crawlee.dev/python/docs/guides/error-handling), [Reddit Data API Terms](https://redditinc.com/policies/data-api-terms))

### Pydantic AI integration

Crawlee also ships an experimental `PydanticAiCrawler`: it fetches over HTTP/Parsel, distills HTML and asks an LLM for validated structured output. A selector extractor can generate and cache reusable CSS selectors. This is useful as a separate exploratory variant, but it should not be the Gate-0 baseline: model calls add cost and nondeterminism, and crawl retries can repeat extraction calls. Keep raw retrieval/snapshotting deterministic, then run the project's versioned Pydantic AI extraction or analysis task downstream. ([Pydantic AI crawler](https://crawlee.dev/python/docs/guides/pydantic-ai-crawler))

## Provider architecture recommendation

Split the current broad `RedditProvider` protocol into capability-specific ports. Search can discover URLs without fetching complete threads, while Crawlee can fetch a known URL without implementing Reddit search. Forcing every adapter to implement both methods would create unsupported methods or hide routing inside providers:

```text
RedditDiscoverySource
├── AsyncPrawDiscoverySource         requires approved Data API access
├── SearchDiscoverySource            returns candidate Reddit URLs
└── CuaDiscoverySource               final bounded discovery fallback

RedditThreadFetcher
├── AsyncPrawThreadFetcher           requires approved Data API access
├── CrawleeHttpThreadFetcher         known URL only
├── CrawleePlaywrightThreadFetcher   known URL only
└── CuaThreadFetcher                 final bounded fetch fallback

RedditPublisher                      remains a separate write-side port
```

The two Async PRAW adapters can share one internal client and credential context, but that SDK object should remain behind the ports. The two Crawlee fetchers may share queues internally, while provider routing and escalation policy remain application code. A fetch result should say `success`, `incomplete`, `blocked`, `auth_required`, `rate_limited`, `not_found` or `failed`. `Incomplete` results and exhausted transient technical failures may escalate; `blocked`, `auth_required`, `rate_limited` and `not_found` must stop or enter an explicit policy/backoff path. Never silently turn an access denial into another evasion attempt.

Persist immutable retrieval observations separately from normalized conversations:

```text
RetrievalObservation
  run_id
  provider + provider_version
  method: reddit_api | crawlee_http | crawlee_playwright | cua
  source_url + final_url + reddit_post_id
  fetched_at
  status + response metadata
  raw_artifact_ref + raw_sha256
  extractor_version
  normalized_sha256
  completeness + failure_reason
```

This preserves evidence when normalization changes and distinguishes repeated observations from duplicate conversations.

## Gate-0 benchmark additions

Use the same frozen query set and pooled labels already proposed by the retrieval evaluation protocol. Add two matched tests.

### Discovery benchmark

Compare:

- Async PRAW subreddit/all search and approved listings, only if approved credentials exist.
- Current Google/Search discovery path.
- CUA bounded Reddit search.

Measure unique and relevant conversations, provider overlap, freshness, Precision@5/10, NDCG@10, request count, rate-limit consumption, median/p95 latency, failure rate and cost/useful opportunity. Record Reddit search/listing caps and stream gaps rather than assuming complete recall.

### Known-thread fetch benchmark

For the same fixed URL corpus compare:

- Async PRAW direct ID/URL fetch with documented comment-sort and `MoreComments` budgets.
- Crawlee `HttpCrawler`/`ParselCrawler`.
- Crawlee `PlaywrightCrawler`.
- Current URL Context path.
- CUA known-URL fetch.

Include ordinary self/link/media posts, high-comment and deep threads, deleted/removed comments, locked threads and pages that return login/block/rate-limit states. Do not try to bypass quarantines, access gates or CAPTCHAs.

Measure:

- Fetch success and explicit failure classification.
- Submission title/body/author/time/score/comment-count completeness.
- Top-N comment recall, depth coverage and selected comment-sort quality.
- Additional requests spent resolving `MoreComments`.
- Repeat-run normalized hash stability and raw-snapshot reproducibility.
- HTTP requests, retries, bytes, CPU/memory, browser minutes and model tokens.
- Median/p95 latency and cost per complete useful thread.
- Maintenance sensitivity across supported Reddit page variants and at multiple dates.
- Policy readiness: approved use case, commercial permission, credential scope, deletion/retention mechanism and audit evidence.

Pin library and browser versions, fix concurrency/throttling, disable adaptive method selection and proxy/session rotation, and retain immutable raw responses/pages for the benchmark. Select defaults by tier: fastest compliant method that meets a stated completeness threshold, with explicit escalation—not one global winner for both discovery and thread extraction.

## Decision

- **Adopt Async PRAW as the implementation choice for the approved official Reddit provider**, but do not make it an MVP dependency while access is unresolved.
- **Add Crawlee HTTP and Playwright adapters to Gate 0 before CUA** for known-URL fetching. Commit to them only if the benchmark shows a meaningful reliability/cost advantage.
- **Do not use Crawlee proxy, fingerprint or session rotation to work around Reddit controls.**
- **Keep CUA last.** It remains valuable for narrow cases that require semantic visual interaction, but deterministic API/HTTP/browser handlers should handle repeatable cases first.
- **Keep discovery, fetching, normalization, semantic analysis and publishing as separate concerns.** None of these libraries changes the approval boundary or authorizes outbound action.
