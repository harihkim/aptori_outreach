# ADR-003: Require human approval for the exact outbound artifact

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The system generates marketing/community content and controls browser workflows. Prompt-level instructions such as “ask before posting” are not a sufficient authorization boundary. The user requirement is explicit: nothing is posted automatically without human approval.

## Decision

Every outbound artifact must be versioned. Approval stores the human approver, timestamp, exact draft/media version and cryptographic checksum. Any content/media edit creates a new version and invalidates publish eligibility. Publishing workers accept an approved artifact ID/approval ID, not arbitrary text. Research workers have no posting tools.

## Consequences

### Positive

- Hard technical enforcement of user intent.
- Auditable approval history.
- Prevents agents/MCP clients from bypassing the review UI.
- Exact-content checksum catches silent rewrites after approval.

### Negative / trade-offs

- More workflow/state complexity.
- Regeneration or tiny edits require re-approval.

## Revisit when

- The product supports collaborative/multi-step approval requiring a richer approval policy.
- A new platform requires additional confirmation semantics.

## Related documentation

- [Approval and security](../architecture/approval-security.md)
- [Product specification](../product/product-spec.md)
