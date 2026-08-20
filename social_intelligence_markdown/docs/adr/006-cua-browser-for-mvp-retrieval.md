# ADR-006: Use CUA/browser automation for Reddit MVP retrieval

- **Status:** Accepted for MVP
- **Date:** 2026-08-20

## Context

The required demonstration is Reddit-first, but official developer access is a separate workstream. Search/URL retrieval may be incomplete and direct scraping parsers are brittle. CUA provides isolated computer-use/browser infrastructure that can execute narrow read-only tasks.

## Decision

Use a retrieval escalation ladder: Google Search grounding for discovery, Gemini URL Context where sufficient, then CUA browser extraction for incomplete cases or direct bounded Reddit search. Treat CUA as an MVP provider, not a permanent assumption for production.

## Consequences

### Positive

- Enables the demo without blocking on developer approval.
- Handles dynamic page behavior better than a static parser in some cases.
- Sandbox boundary is useful for browser credentials/sessions.

### Negative / trade-offs

- Slower and costlier than deterministic APIs/fetches.
- UI changes can break automation.
- Platform access/policy constraints must be monitored.

## Revisit when

- Official Reddit access becomes available and is superior.
- Benchmark shows another public retrieval approach is more reliable/cost-effective.
- Browser failure/cost makes the approach unsuitable.

## Related documentation

- [Reddit retrieval architecture](../architecture/retrieval.md)
- [Reddit access, Gemini and CUA notes](../research/reddit-access-and-gemini.md)
