# ADR-008: Use Higgsfield as the initial media-generation provider

- **Status:** Accepted for expansion
- **Date:** 2026-08-20

## Context

The product may benefit from a visual “trend to content” workflow, but retrieval viability and the response-review vertical slice are the core proof. Building image/video generation infrastructure is outside the differentiation. Higgsfield offers async media generation suitable for a later worker/webhook integration.

## Decision

After the prototype vertical slice is validated, integrate Higgsfield behind an internal media provider/service. Persist job provenance and copy completed assets to company-controlled object storage. Finalized media checksums are included in the same complete Approved Artifact scope as text, Actor Account, action, and Destination.

## Consequences

### Positive

- Fast expansion path to image/video generation without putting it on the prototype critical path.
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
