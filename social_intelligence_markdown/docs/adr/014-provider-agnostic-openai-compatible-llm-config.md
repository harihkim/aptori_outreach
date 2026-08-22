# ADR-014: Configure LLM Tasks against any OpenAI-compatible endpoint

- **Status:** Accepted
- **Date:** 2026-08-22
- **Builds on:** [ADR-002](002-pydantic-ai-primary-orchestrator.md)

## Context

ADR-002 fixes Pydantic AI as the typed LLM execution layer and the task catalog names its tasks, but no document commits to a provider or model IDs, and no provider key exists in the environment today. Committing the prototype to one vendor now would couple the vertical slice to a procurement decision that has not been made. Pydantic AI already accepts any OpenAI-compatible chat-completions endpoint via a custom base URL, model name, and API key — every major provider and aggregators expose that surface.

## Decision

LLM Task model selection is fully configuration-driven and provider-agnostic: every task resolves its endpoint from environment configuration — an OpenAI-compatible base URL, a model name, and an API key — never from code. No provider name appears in application code.

Two model tiers implement the routing policy from [Typed LLM and Agent Design](../architecture/agents.md):

- an **ordinary** tier for routine analysis and generation;
- a **strong** tier for explicitly classified borderline/high-value cases, which falls back to the ordinary tier's endpoint and model when unset.

Swapping providers is an environment change. Because each LLM Task is evaluated against a frozen labeled dataset, the effect of a swap is measurable by re-running the evaluation, and quality escalation stays separate from availability fallback.

## Consequences

### Positive

- The vertical slice is not blocked on a vendor decision; any OpenAI-compatible key unblocks it.
- Provider, model, and tier changes are operations, not code changes, and are auditable through the versioned task configuration.
- The frozen eval datasets make provider changes a measured claim rather than an impression.

### Negative / trade-offs

- Provider-native capabilities (provider-specific tool schemas, prompt caching APIs, native structured-output modes beyond the OpenAI-compatible surface) are unavailable; the contract is the common denominator.
- Per-provider latency/cost characteristics differ while the configuration treats them uniformly; budgets are tracked per Model Run to keep this visible.

## Revisit when

- A task demonstrably needs a provider-native capability the OpenAI-compatible surface cannot express.
- Cost or latency findings justify committing to (and negotiating with) a specific provider.

## Related documentation

- [ADR-002: Pydantic AI as primary typed LLM layer](002-pydantic-ai-primary-orchestrator.md)
- [Typed LLM and Agent Design](../architecture/agents.md)
- [Opportunity Scoring](../product/opportunity-scoring.md)
