# ADR-002: Use Pydantic AI as the primary AI orchestration layer

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The backend is Python/FastAPI and the product relies heavily on typed structured outputs: conversation analysis, recommended action, drafts, media briefs and deferred/human-reviewed tool actions. LangChain has a broad ecosystem, but adopting its full abstraction stack is not required for this problem.

## Decision

Use Pydantic AI as the default framework for model/tool orchestration and typed outputs. Integrate isolated LangChain tools only when a specific connector materially benefits from them.

## Consequences

### Positive

- Strong fit with Pydantic/FastAPI models.
- Validated typed model outputs.
- Good fit for MCP and human-in-the-loop/deferred tools.
- Keeps application/domain types central.

### Negative / trade-offs

- Smaller ecosystem than the full LangChain/LangGraph universe in some integration areas.
- May require custom adapters for niche tools.

## Revisit when

- A required workflow is significantly easier or more reliable in another framework.
- The team standardizes on a different orchestration platform.

## Related documentation

- [AI and agent design](../architecture/agents.md)
- [System design](../architecture/system-design.md)
