# ADR-001: Use a headless core with first-party UI and MCP adapters

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The platform must serve two distinct interaction styles: a high-density operational UI for triage/review and agent-driven workflows for research and content preparation. Making MCP the product would make bulk review and approval awkward; making the UI own business logic would make external-agent behavior inconsistent.

## Decision

Build a headless domain/application core backed by PostgreSQL. Expose it through FastAPI REST/SSE for the SvelteKit application and through MCP for agent hosts. Both adapters invoke the same services and authorization checks.

## Consequences

### Positive

- One canonical state and rule set.
- First-party UX can optimize high-volume review.
- Agents can use the platform without duplicating intelligence logic.
- Future APIs/clients are additive.

### Negative / trade-offs

- More interface surface to maintain.
- Requires discipline to keep business rules out of route/tool adapters.

## Revisit when

- A single interface demonstrably covers all user workflows without compromise.
- MCP or REST evolves in a way that makes the duplicate adapter unnecessary.

## Related documentation

- [System design](../architecture/system-design.md)
- [API and MCP architecture](../architecture/api-and-mcp.md)
