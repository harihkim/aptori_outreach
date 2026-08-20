# ADR-005: Use bounded AI agents inside deterministic workflows

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

A “super agent” controlling discovery, scoring, publishing and retries would be difficult to audit and test. The platform needs strict approval rules, idempotent jobs, reproducible state transitions and cost control.

## Decision

Application code owns state transitions, provider routing, retries, authorization, deduplication, audit and approvals. AI/model calls are bounded nodes for semantic tasks such as classification, synthesis, drafting and media briefs, returning typed outputs.

## Consequences

### Positive

- Predictable retries and recovery.
- Easier evaluation of scoring versus generation.
- Lower model cost through targeted routing.
- Safer tool permissions and clearer audit trails.

### Negative / trade-offs

- More explicit workflow code.
- Less flexibility than unconstrained agent loops for unforeseen tasks.

## Revisit when

- A future workflow genuinely benefits from open-ended planning and can be sandboxed without weakening approval/audit guarantees.

## Related documentation

- [AI and agent design](../architecture/agents.md)
- [Workers, observability and testing](../architecture/workers-observability-testing.md)
