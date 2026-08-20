# ADR-010: Separate the Approval decision from the Approved Artifact

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

A human decision and an executable authorization snapshot have different audit and lifecycle semantics. Combining them into one mutable approval row obscures what the human did, what the system derived, and which exact fields publishing may consume.

## Decision

Record `Approval` as the immutable human decision referencing one Draft Version. In the same authorized transaction, derive an immutable `ApprovedArtifact` that snapshots and hashes text, ordered media, Actor Account, action, Destination, expiry, and single-use limit. Publish Preparation consumes only the artifact through its Approval identifier and cannot override its scope.

## Consequences

- Human decisions remain auditable independently of execution format.
- Artifact schema/digests can evolve for future platforms without rewriting decision history.
- Creation and consumption require transactional constraints and a stable canonical digest algorithm.

## Related documentation

- [Human Approval and Security](../architecture/approval-security.md)
- [PostgreSQL Data Model](../architecture/data-model.md)
