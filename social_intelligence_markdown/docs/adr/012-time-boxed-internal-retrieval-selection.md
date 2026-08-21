# ADR-012: Time-box Obscura and DuckDuckGo Lite for the internal product

- **Status:** Accepted
- **Date:** 2026-08-21
- **Review date:** 2026-09-20
- **Creates an exception to:** [ADR-009](009-retrieval-viability-gate-and-escalation.md)

## Context

Retrieval Gate R0 remains the right comparative evidence gate, but completing it before any product work would miss the current delivery window. The Obscura experiment at commit `8290823` demonstrated two successful WSL runs against one Reddit thread using anonymous standard navigation followed by an in-origin structured hierarchy fetch. It retrieved the full root post and the complete available comment tree for that fixture. This is promising implementation evidence, not a representative R0 result.

The current product has no external users. The project team wants a complete Internal Product: implemented, deployable, scheduled, and polished like a commercial offering, while accepting a reversible retrieval choice so the vertical slice can advance. We therefore need a controlled exception that enables delivery without relabeling one experiment as provider viability.

## Decision

Until the review date, authorize the complete Internal Product vertical slice using these provisional variants:

- `ObscuraDuckDuckGoLiteDiscoverySource` for campaign-query discovery;
- `ObscuraRedditThreadFetcher` for retrieval of known Reddit thread URLs.

The variants remain separate capability-specific adapters and emit separate immutable Retrieval Observations. They run through a project-owned narrow wrapper with pinned binary/version/configuration and retained raw evidence. The current reference execution environment is WSL; moving to another environment is material drift until re-evaluated. The authorized access class is anonymous standard Obscura only. Accounts, authenticated sessions, CAPTCHA or challenge continuation, stealth settings, residential proxies, proxy rotation, and identity rotation are outside this decision.

Dated product work and retrieval validation proceed together:

1. Domain, persistence, API, worker, and UI scaffolding may start immediately.
2. The retrieval increment is not complete until the prototype smoke gate below passes.
3. Product-level implementation and polish are permitted for the Internal Product; deferred expansion capabilities do not become critical-path scope.
4. This decision does not claim R0 passed and does not authorize future external use.

There is no hidden provider hopping. A discovery or fetch attempt persists its own outcome. An operator may explicitly rerun a separately configured Google, Brave Search API, Bing/Edge-index, or other provider variant, producing a new observation with its own provenance. Supported APIs are preferred when credentials become available.

### Prototype smoke gate

Freeze the fixtures and exact runtime configuration before scoring.

**Discovery smoke:**

- Run 10 representative campaign queries.
- At least 8 of 10 queries yield one or more canonical Reddit thread candidates.
- Every emitted candidate is a valid canonical Reddit thread URL.
- Empty results, blocks, parse failures, and transport failures are explicit outcomes rather than silent fallbacks.

**Thread-fetch smoke:**

- Run 10 varied frozen Reddit threads twice.
- At least 8 of 10 threads succeed in each run.
- Successful normalized trees contain zero duplicate comments and zero missing parent references.
- Any unresolved Reddit `more` node makes the observation `INCOMPLETE`, never `COMPLETE`.
- Replaying retained raw evidence produces the identical normalized-content hash.

### Automatic suspension and review

Suspend the provisional selection before the review date if any of these occurs:

- three consecutive frozen smoke batches fall below 80% successful, sufficiently complete thread retrieval;
- operation requires an account/session, CAPTCHA continuation, stealth, a residential proxy, proxy rotation, or identity rotation;
- material binary, browser, configuration, endpoint, or execution-environment drift means the recorded evidence no longer represents the runtime;
- an external user or external pilot is proposed.

The 2026-09-20 review is a mandatory reassessment, not an automatic shutdown. The team must then renew the exception with new evidence, graduate a route through full R0, change the retrieval architecture, or revise the product premise.

## Consequences

### Positive

- The complete internal vertical slice can advance under schedule pressure.
- The working Obscura technique becomes a narrow, observable adapter rather than an informal script dependency.
- Smoke evidence can expose immediate fragility while the broader R0 comparison continues.
- Product polish is not confused with external-user or provider-readiness evidence.

### Negative / trade-offs

- The internal product temporarily depends on browser and search surfaces that may drift.
- Smoke success is deliberately weaker than R0 and cannot establish comparative quality, cost, long-run reliability, or policy viability.
- Separate provider variants and retained evidence add implementation work during the time-box.

## Related documentation

- [Retrieval Architecture](../architecture/retrieval.md)
- [Retrieval Gate R0](../research/retrieval-benchmark.md)
- [Implementation Roadmap](../roadmap/roadmap.md)
- [Obscura Reddit Retrieval Experiment](../../../experiments/2026-08-20-obscura-reddit-retrieval-experiment.md)
- [ADR-011](011-isolate-session-backed-retrieval-experiments.md)
