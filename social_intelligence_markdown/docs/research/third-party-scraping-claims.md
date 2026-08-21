# Assessment of Third-Party Scraping Architecture Claims

> **Status:** Research note
> **Last updated:** 2026-08-21
> **Scope:** Fact-check of a quoted architecture description; the referenced third-party repository and runtime evidence were not provided
> **Incorporated:** Canonical retrieval controls, ADR-012's internal exception, R0 accounting, and production-readiness gates in documentation v0.4.

## Verdict

**The architecture contains useful operational ideas, but its exact volumes and several safety claims are not established by the supplied description. Do not copy its numbers or guarantees into this project's contracts.**

The defensible ideas are bounded discovery, deduplication, explicit provider failures, measured pacing, and policy-aware fallback between independently authorized providers for capability or availability gaps. An explicit block, CAPTCHA, authentication gate, or policy denial must stop that route rather than trigger evasion through another identity or proxy. The claims that a fixed 2.2-second delay prevents blocking, throttles recover in 30–60 minutes, one `APIFY_TOKEN` unlocks hundreds or thousands of posts through residential proxies, those proxies completely bypass blocks, or using no logged-in social account creates zero ban risk are not supported as general platform facts.

## Evidence boundary

The following are implementation claims about code we have not inspected and cannot verify from external documentation:

- the paths and behavior of `apps/api/src/services/ingest.ts`, `apps/api/src/services/social.ts`, and `packages/core/src/channels/base.ts`;
- one homepage plus five to eight sub-pages per company ingest;
- six to ten HTTP requests, a 20,000-character cap, or exactly one screenshot;
- a 50-item social limit, typical yield of 10–30 posts, workspace deduplication, recurring schedules, or honest `FAILED` persistence;
- an implemented 2.2-second global gap, exact fallback order, block-response regexes, and the absence of fabricated results;
- which Apify Actor, Actor version, input, pricing model, or proxy configuration the product invokes.

Those claims require the source revision, configuration, dependency lock, and run evidence. A browser page navigation can also generate many subresource requests, so counting “pages read” or screenshots is not the same as measuring actual outbound HTTP requests. Request totals must come from transport instrumentation, not an architecture sketch.

There is also an ambiguity in the quote itself: the prose describes `primary endpoint -> DuckDuckGo -> DuckDuckGo Lite -> Brave`, which is four possible attempts, while another section describes only three search engines. The claimed “one to three requests” needs a precise definition of the primary endpoint and attempt-counting rules.

## Claim-by-claim assessment

| Claim | Assessment | Reason |
|---|---|---|
| Brave is part of a keyless fallback | **Misleading unless this means unsupported HTML-page access** | Every request to the supported Brave Search API requires a subscription token in the `X-Subscription-Token` header. A keyless Brave route would be a different mechanism and needs its own implementation and policy evidence. |
| A fixed 2.2-second gap is anti-blocking protection | **A local pacing choice, not a guarantee** | Provider limits differ by service and plan. Brave exposes per-subscription limit, remaining, policy, and reset headers; clients should use those values. Target sites can also classify traffic by IP, cookies, TLS/browser fingerprint, and behavior rather than request rate alone. |
| `202`, `403`, and `429` all identify CAPTCHA/rate limiting | **Provider-specific heuristic, not HTTP semantics** | HTTP `202` means a request was accepted for processing, not “CAPTCHA.” `403` means the server refuses the request and should not be blindly repeated with the same credentials. `429` means too many requests and may carry `Retry-After`. Body inspection can be a provider adapter heuristic, but the raw status must be retained. |
| Blocks normally clear in 30–60 minutes | **Unsupported as a general rule** | HTTP defines no universal recovery interval. A `429` response may provide `Retry-After`; Brave provides reset headers. A target may key a restriction by IP, credentials, cookie, resource, fingerprint, or a combination, and a `403` can be effectively terminal for the current route. |
| Residential IP means low block risk | **Directionally plausible, still unquantified** | Apify calls residential addresses the least likely proxy type to be blocked, but its own guidance says there is no single solution and that fingerprint, headers, cookies, behavior, and target configuration matter. “Low” must be established per provider, environment, and workload in R0. |
| Setting `APIFY_TOKEN` unlocks hundreds or thousands of posts | **Unsupported and underspecified** | An Apify token authenticates API access. The caller must still select an Actor and version, supply that Actor's structured input, wait for the run, and read its dataset. Maximum results, completeness, cost, and supported sources are Actor-specific. |
| `APIFY_TOKEN` routes scraping through residential proxies | **False as a platform-level statement** | Proxy selection is an Actor/crawler configuration choice. External Apify Proxy access uses proxy connection settings and a proxy password; an Actor can use built-in proxy configuration, but an API token alone does not enable or select the residential group. |
| Apify residential proxies completely bypass datacenter bans and Cloudflare | **False guarantee** | Apify documents residential proxies as less likely to be blocked, not unblockable. Its anti-scraping guide explicitly says there is no silver bullet; some protections also evaluate browser fingerprints, headers, cookies, and behavior. Proxy IPs can already be suspicious or blocked. |
| Apify is a simple commercial volume switch | **Incomplete** | Actor runs can incur compute, storage, data-transfer, and proxy usage, plus Actor-specific pay-per-event, pay-per-usage, or rental charges. Apify recommends measuring a limited run because some costs are difficult to predict beforehand. |
| No logged-in social account means zero account-ban risk | **Overstated** | Avoiding personal credentials materially reduces the risk of a credential-linked social-account sanction. It does not establish zero enforcement or policy risk: services can block traffic, and Reddit's current User Agreement prohibits scraping without prior written consent except permitted crawling. Apify and Brave credentials are accounts too and may be limited or suspended. |
| Failed providers never produce hallucinated posts | **Good invariant, implementation unverified** | The product should persist a typed failure and never ask an LLM to invent missing retrieval results. That behavior must be proven with code/tests and raw evidence, not accepted from the description. |

## Brave Search API facts

Brave's supported Search API requires an API subscription and a confidential token on every request. It is therefore suitable as an explicit authenticated search adapter, not as part of a “keyless public endpoint” category. ([Brave authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication), [web-search API reference](https://api-dashboard.search.brave.com/api-reference/web/search/get))

Brave rate limiting is subscription-specific and enforced with a sliding window. Responses expose `X-RateLimit-Limit`, `X-RateLimit-Policy`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`; exceeding a limit produces `429`. The implementation should follow these headers and use bounded backoff rather than treating 2.2 seconds as a universal contract. ([Brave rate-limiting guide](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting))

Brave's current standard terms also prohibit bypassing service/rate limits and, absent different order-form rights, restrict persistent storage/caching of Search Results. They place third-party content compliance on the customer and permit Brave to suspend access in specified circumstances. These constraints matter because this project's evidence model normally retains provider observations; retention rights must be confirmed for the selected plan before storing full Brave results. ([Brave Search API terms](https://api-dashboard.search.brave.com/documentation/resources/terms-of-service), [Brave Search API product and storage note](https://brave.com/search/api/))

## Apify facts

An Apify Actor is a serverless program with its own structured input, output, documentation, version, and runtime behavior. Programmatic execution requires selecting an Actor, passing its input, and reading its resulting dataset or other storage. The run is billed to the account associated with the supplied token. No platform documentation supports a generic “hundreds to thousands of social posts” result from possession of a token alone. ([Actor overview](https://docs.apify.com/actors), [running Actors](https://docs.apify.com/actors/running), [Actor input and output](https://docs.apify.com/actors/running/input-and-output))

The API token is an authentication and authorization credential. Apify supports scoped tokens and recommends least-privilege, separate tokens for services. Proxy use is configured independently. In an Actor this is commonly done through its proxy configuration; external proxy access uses Apify Proxy credentials and requires a paid plan. ([Apify API authentication](https://docs.apify.com/api/v2), [scoped-token guidance](https://docs.apify.com/integrations/api), [Apify Proxy](https://docs.apify.com/proxy))

Residential proxies reduce IP-reputation risk but do not eliminate blocking. Apify states that datacenter addresses can already be blocked and residential addresses are least likely to be blocked. Its own anti-scraping material says protections can also inspect headers, TLS/browser fingerprints, cookies, requested endpoints, and behavior, and explicitly rejects a universal solution. ([Apify Proxy types and rotation](https://docs.apify.com/proxy), [anti-scraping protections](https://docs.apify.com/academy/anti-scraping), [proxy limitations](https://docs.apify.com/academy/anti-scraping/mitigation/proxies))

Cost is multidimensional. Actor runs can consume compute units, external/internal transfer, proxy traffic, and storage operations. Store Actors can additionally use creator-defined pay-per-event, pay-per-usage, or rental pricing; Apify says limited test runs are the best way to estimate some Actor costs. A production decision therefore needs `cost/query`, `cost/thread`, and `cost/useful opportunity`, not an “Apify enabled” boolean. ([Actor usage and resources](https://docs.apify.com/actors/running/usage-and-resources), [Store Actor pricing models](https://docs.apify.com/actors/running/actors-in-store))

## Retry and failure semantics

HTTP `429 Too Many Requests` can include a `Retry-After` value, but the standard does not prescribe how the server identifies a caller or counts requests. A caller may be identified by credentials, cookies, resource, server-wide activity, or other state. `Retry-After` can be either an HTTP date or a delay in seconds. ([RFC 6585 section 4](https://www.rfc-editor.org/rfc/rfc6585.html#section-4), [RFC 9110 section 10.2.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3))

The adapter contract should therefore distinguish at least:

```text
SUCCESS
NO_RESULTS
RATE_LIMITED(retry_at?)
BLOCKED(challenge_kind?)
AUTH_REQUIRED
FORBIDDEN
UPSTREAM_UNAVAILABLE(retry_at?)
PARSE_FAILED
POLICY_DISALLOWED
```

Retry only cases classified as retryable, honor provider reset/`Retry-After` signals, add bounded exponential backoff with jitter, and cap attempts and spend. Do not turn a `403`, CAPTCHA, or policy denial into an automatic proxy-escalation loop.

## Platform permission remains a separate gate

Technical reachability through a search index, proxy, or browser does not grant permission to collect or retain the target content. Reddit's current User Agreement says automated or other collection is allowed only as provided in its terms or a separate agreement, conditionally permits crawling within `robots.txt`, and prohibits scraping without prior written consent. Reddit also states that it rate-limits or blocks unknown crawlers. ([Reddit User Agreement](https://redditinc.com/policies/user-agreement), [Reddit robots and crawler statement](https://redditinc.com/news/robot-txt-update))

Consequently, an Apify Actor returning data is evidence of technical success only. It cannot satisfy this project's policy gate by itself.

## Recommended treatment in this project

Keep the other platform as a benchmark inspiration, not an authority. For Gate R0:

1. Model `DuckDuckGo HTML`, `DuckDuckGo Lite`, `Brave Search API`, any Brave HTML route, and each Apify Actor as distinct provider variants.
2. Record the exact provider/Actor identifier, immutable version or build, input, proxy group, token scope, request/attempt count, returned count, deduplicated count, raw evidence hash, latency, and complete cost.
3. Measure actual network requests separately from logical pages or search attempts.
4. Use adaptive provider-aware throttling and typed failure policy; retain 2.2 seconds only as a tested configuration value, not an invariant.
5. Pin and review the Apify Actor, set maximum run spend, configure the intended proxy explicitly, and never give a third-party Actor an unscoped account token.
6. Keep a policy/commercial-use gate independent from retrieval success.
7. Replace absolute language with measured language: “reduced risk,” “observed recovery distribution,” and “benchmark-dependent yield.”

## Bottom line

- **Adopt:** bounded workloads, deduplication, truthful typed failures, scheduled low-burst execution, and policy-aware fallback only for separately authorized capability or availability gaps.
- **Benchmark:** residential versus datacenter execution, provider-specific pacing, recovery distributions, and exact cost per useful opportunity.
- **Reject as contracts:** universal 2.2-second safety, 30–60-minute recovery, keyless Brave API access, token-only Apify scaling, complete block bypass, and zero ban risk.
- **Require before any adoption:** repository/source revision, executable tests, provider policy review, and raw run evidence. Full R0 remains required for provider graduation or external use; ADR-012's smaller smoke gate applies only to its named provisional internal variants.
