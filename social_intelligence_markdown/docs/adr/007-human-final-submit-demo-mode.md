# ADR-007: Leave the final Reddit submit click to the human in the preferred demo

- **Status:** Accepted for demo
- **Date:** 2026-08-20

## Context

Even with an approval gate, the demonstration should make the human-control boundary visually obvious. The primary goal is to prove research, scoring, drafting and browser preparation, not unattended publishing.

## Decision

After a human approves the complete outbound action and the server creates an immutable Approved Artifact, CUA may navigate to the bound Reddit Destination from the bound Actor Account and fill the composer with the exact approved content. The preferred prototype stops before clicking final submit. A later production-approved publishing path may be evaluated separately.

## Consequences

### Positive

- Very clear demonstration of human control.
- Reduces risk during an early browser-automation demo.
- Still proves the complete preparation workflow.

### Negative / trade-offs

- One manual click remains.
- Does not demonstrate full post-approval execution automation.

## Revisit when

- A production-approved publishing integration is ready and the team wants to demonstrate it.

## Related documentation

- [Demo specification](../product/demo-spec.md)
- [Approval and security](../architecture/approval-security.md)
