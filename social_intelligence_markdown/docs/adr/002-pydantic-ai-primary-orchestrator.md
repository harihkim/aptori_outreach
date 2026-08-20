# ADR-002: Use Pydantic AI as the primary typed LLM execution layer

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

The product needs typed model work across extraction, classification, synthesis, analysis, drafting, risk assessment, media briefs, evaluations, and occasional tool-using flows. Describing Pydantic AI only as “agent orchestration” would encourage separate vendor-SDK paths for ordinary single-turn LLM calls and fragment validation, retries, limits, and telemetry.

## Decision

Use a pinned Pydantic AI v2-compatible range as the default execution layer for all product LLM Tasks, including non-agentic single-turn structured calls. Prefer the high-level `Agent` API for its typed outputs, validation, dependencies, limits, streaming, and instrumentation. Application/domain code continues to own workflow state, deterministic scoring, whole-job retries, persistence, provider policy, authorization, Approval, and publishing.

## Consequences

- Model-facing behavior and provenance use one typed boundary.
- Each semantic task requires a named/versioned contract, budgets, and evaluation suite.
- Provider portability remains tested rather than assumed because model capabilities differ.
- Pydantic AI deferred-tool approval cannot authorize publishing.
- Another framework may be integrated only behind a specific LLM Task when evidence justifies the additional path.

## Related documentation

- [Typed LLM and Agent Design](../architecture/agents.md)
- [Pydantic AI research note](../research/pydantic-ai-capabilities.md)
