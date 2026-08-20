# ADR-003: Require human approval for the complete outbound action

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

Exact-text hashing prevents content substitution but does not prevent the same text from being sent with different media, from a different account, for another action, or to another destination. Prompt preferences and client-side agent history are not authorization boundaries.

## Decision

Human Approval binds one immutable Draft Version, ordered finalized media/checksums, Actor Account, action type, and exact Destination. The resulting authorization is expiring, revocable, and single-use by default. Any change to a bound value requires a new Approval. The Publish Preparation API accepts only an existing `approval_id`, resolves the Approved Artifact internally, and accepts no outbound overrides; research and LLM workers have no publishing capability.

## Consequences

- The system can audit the exact action the human authorized, not merely unchanged text.
- Tiny edits and operational substitutions require fresh review.
- Database constraints, atomic consumption, and capability-separated workers are required.

## Related documentation

- [Human Approval and Security](../architecture/approval-security.md)
- [Domain Model and State Machines](../architecture/domain-model.md)
- [ADR-010](010-separate-approval-from-approved-artifact.md)
