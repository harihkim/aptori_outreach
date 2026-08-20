# ADR-008: Use Higgsfield as the initial media-generation provider

- **Status:** Accepted for MVP
- **Date:** 2026-08-20

## Context

The product benefits from a visual “trend to content” workflow but building image/video generation infrastructure is outside the core differentiation. Higgsfield offers async media generation suitable for a worker/webhook model.

## Decision

Integrate Higgsfield behind an internal media provider/service. Persist job provenance and copy completed assets to company-controlled object storage. Media selection is versioned and covered by the same human approval mechanism as text.

## Consequences

### Positive

- Fast path to image/video generation.
- Keeps focus on social intelligence and workflow.
- Provider can be abstracted later if needed.

### Negative / trade-offs

- External dependency, latency and cost.
- Provider model/API changes can affect output and integration.

## Revisit when

- Media quality/cost is insufficient.
- Multiple providers become necessary.
- The product develops proprietary media-generation requirements.

## Related documentation

- [Higgsfield media integration](../architecture/media.md)
- [Product user flows](../product/user-flows.md)
