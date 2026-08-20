# ADR-004: Separate Reddit discovery and thread-fetch provider ports

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

Search providers discover URLs, while known-URL HTTP/browser adapters fetch threads; forcing both capabilities into one `RedditProvider` produces unsupported methods or hidden routing. Reddit access and provider behavior are also unstable enough to require independent benchmarking and provenance.

## Decision

Define `RedditDiscoverySource` and `RedditThreadFetcher` ports, with routing/escalation in application code. Keep `RedditPublisher` separate in interface, credentials, and worker capability. If official access is approved, implement the async provider with Async PRAW and map SDK objects immediately into canonical schemas. Benchmark each concrete Search API/plan, URL Context, Crawlee HTTP/Playwright, optional pinned managed/session-backed variants, and CUA independently before selecting defaults. A token, Actor, CLI or browser session is adapter configuration, not a provider contract by itself.

## Consequences

- Discovery quality and thread completeness can be measured separately.
- Adapters implement only capabilities they genuinely provide.
- Every attempt needs explicit provenance and failure semantics.
- More routing composition is visible in application code, where policy belongs.

## Related documentation

- [Reddit Retrieval Architecture](../architecture/retrieval.md)
- [Crawlee/PRAW research note](../research/crawlee-praw-asyncpraw.md)
- [ADR-011](011-isolate-session-backed-retrieval-experiments.md)
