# ADR-016: Establish Workspace and Deployment boundaries with portable evidence bundles

- **Status:** Accepted
- **Date:** 2026-08-30

## Context

The product needs one ownership and evidence contract before customer-facing aggregates and retrieval history expand. A Deployment must be able to host multiple isolated Workspaces, while the first customer topology can remain isolated per customer. Retrieval must preserve what was observed before normalization so that canonical Conversation Versions can be reproduced without changing the original evidence.

## Decision

- A Deployment is one installed instance and may host multiple Workspaces. A Workspace is the smallest isolation boundary. The first operational topology is one isolated Deployment per customer; shared multi-Workspace Deployments remain a supported future shape.
- Composite foreign keys and database constraints enforce same-Workspace relational ownership now. Application and domain authorization checks constrain access; PostgreSQL row-level security is not required for this stage.
- An Evidence Bundle consists of immutable raw evidence and its canonical manifest. EvidenceStore bundles are portable across storage locations and Deployments. Existing evidence references transition additively: readers support the legacy form while new writes emit bundles, and no historical evidence is rewritten or discarded as part of the transition.
- Raw evidence is captured before normalization. Normalization produces immutable Conversation Versions identified by normalizer version; a Conversation remains the stable Workspace-scoped source identity and is not a content hash.

## Consequences

### Positive

- Customer isolation is explicit at the domain boundary while leaving room for later shared Deployments.
- Database constraints make same-Workspace ownership explicit, while application authorization checks constrain access without coupling the current stage to row-level security.
- Portable bundles preserve retrieval provenance and permit normalization to be replayed with a known normalizer version.
- Additive evidence migration avoids breaking historical observations or requiring a destructive cutover.

### Negative / trade-offs

- Composite ownership must be carried through every cross-aggregate relationship and checked consistently by application services.
- The first isolated-per-customer topology costs more operationally than immediate shared hosting.
- Supporting legacy and bundle evidence references temporarily increases read and test surface.
- Without row-level security, an authorization defect in application code remains a direct isolation risk.

## Revisit when

- Shared hosting becomes a concrete operational need and its isolation, cost, and authorization evidence justify changing the first topology.
- Database-enforced row-level security can be introduced without weakening the application authorization contract.
- All historical references have been migrated and replay-verified against portable EvidenceStore bundles.
