# ADR-009: Gate the product on retrieval viability and prefer deterministic escalation

- **Status:** Accepted
- **Date:** 2026-08-20
- **Supersedes:** [ADR-006](006-cua-browser-for-mvp-retrieval.md)

## Context

The Reddit-first premise depends on acquiring fresh relevant conversations with sufficient thread context at acceptable reliability, latency, cost, and policy risk. Search, URL Context, Crawlee HTTP/browser, CUA, and a future official API have different discovery and extraction characteristics; a curated demo cannot establish viability.

## Decision

Make Retrieval Gate R0 a prerequisite to the prototype vertical slice. Freeze queries, known-thread corpus, labels, exact provider/Actor/browser configurations, access-identity classes, rate/spend budgets, metrics, and pass thresholds before comparative runs. Select defaults independently for discovery and thread fetching. Prefer an approved official API or deterministic HTTP method when it meets completeness, then explicit Playwright, with CUA last for semantic/UI cases. Automatic escalation is allowed only for incomplete or exhausted transient failures; explicit blocks, CAPTCHAs, authentication gates and policy denials stop the route. A failed R0 returns the project to retrieval architecture or product-premise work rather than allowing compensating feature scope.

## Consequences

- UI/content/media investment waits for evidence from the acquisition layer.
- Evaluation artifacts and failed provider variants become versioned product evidence.
- There may be no viable route; that is an intended gate outcome.
- Browser access-control failures stop rather than triggering evasion behavior.

## Related documentation

- [Retrieval Gate R0](../research/retrieval-benchmark.md)
- [Implementation Roadmap](../roadmap/roadmap.md)
- [ADR-011](011-isolate-session-backed-retrieval-experiments.md)
