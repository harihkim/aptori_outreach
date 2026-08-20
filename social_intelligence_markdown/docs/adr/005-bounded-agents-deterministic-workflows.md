# ADR-005: Use bounded LLM Tasks inside deterministic workflows

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

A super-agent controlling discovery, scoring, retries, approval, and publishing would be difficult to test, recover, cost-bound, and authorize. Many useful model operations require no planning or tools at all.

## Decision

Application code owns state transitions, provider routing, whole-job retries, idempotency, deterministic scoring, persistence, authorization, audit, and Approval. Pydantic AI executes named bounded LLM Tasks for semantic work and returns typed outputs. Optional tools and open-ended planning are added only for tasks that demonstrate a need and cannot weaken application permissions.

## Consequences

- Scoring, analysis, and generation can be evaluated independently.
- Retry/cost ownership and recovery remain explicit.
- More workflow code exists outside the model, but it is testable and auditable.

## Related documentation

- [Typed LLM and Agent Design](../architecture/agents.md)
- [Workers, Observability, and Testing](../architecture/workers-observability-testing.md)
