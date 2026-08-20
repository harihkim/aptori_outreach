# ADR-004: Use a pluggable Reddit retrieval-provider abstraction

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

Reddit developer/API approval is a separate process, while the MVP must demonstrate Reddit now. Browser/search behavior and platform access can also change. Coupling the opportunity engine to one retrieval technique would make the product brittle.

## Decision

Define read-oriented `RedditProvider` capabilities for discovery, thread fetch and health checks. Keep publishing in a separate interface. Implement browser/search providers for the MVP and reserve a provider for approved official API access later.

## Consequences

### Positive

- Retrieval methods can be benchmarked/swapped.
- Official API access can be added without rewriting intelligence/UI layers.
- Provider-specific failures and provenance are explicit.

### Negative / trade-offs

- Requires normalization and consistent provider contracts.
- Some providers will expose different metadata/coverage.

## Revisit when

- Reddit offers a stable approved interface that fully covers requirements and is the clear long-term default.

## Related documentation

- [Reddit retrieval architecture](../architecture/retrieval.md)
- [Retrieval benchmark](../research/retrieval-benchmark.md)
