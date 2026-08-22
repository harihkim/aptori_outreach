# Architecture Decision Records

ADRs capture important architectural choices and their consequences. They complement the specs: the spec says what the system should do; an ADR records why a significant design choice was selected.

| ADR | Decision | Status |
|---|---|---|
| [001](001-headless-core-plus-ui-and-mcp.md) | Headless core with first-party UI and MCP adapters | Accepted |
| [002](002-pydantic-ai-primary-orchestrator.md) | Pydantic AI as primary typed LLM execution layer | Accepted |
| [003](003-human-approval-exact-content-gate.md) | Human approval for the complete outbound action | Accepted |
| [004](004-reddit-provider-abstraction.md) | Separate Reddit discovery and thread-fetch ports | Accepted |
| [005](005-bounded-agents-deterministic-workflows.md) | Bounded LLM Tasks inside deterministic workflows | Accepted |
| [006](006-cua-browser-for-mvp-retrieval.md) | CUA/browser retrieval as the assumed MVP path | Superseded by ADR-009 |
| [007](007-human-final-submit-demo-mode.md) | Preferred demo stops before final Reddit submit | Accepted for demo |
| [008](008-higgsfield-as-media-provider.md) | Higgsfield as external media-generation provider | Accepted for expansion |
| [009](009-retrieval-viability-gate-and-escalation.md) | Retrieval Gate R0 and deterministic escalation before CUA | Accepted |
| [010](010-separate-approval-from-approved-artifact.md) | Separate Approval decision from Approved Artifact | Accepted |
| [011](011-isolate-session-backed-retrieval-experiments.md) | Isolate session-backed retrieval experiments; reject Agent Reach as runtime boundary | Accepted |
| [012](012-time-boxed-internal-retrieval-selection.md) | Time-box Obscura and DuckDuckGo Lite for the internal product | Accepted |
| [013](013-subprocess-node-retrieval-seam.md) | Invoke the frozen Node retrieval adapters as a subprocess from Python workers | Accepted |
| [014](014-provider-agnostic-openai-compatible-llm-config.md) | Configure LLM Tasks against any OpenAI-compatible endpoint | Accepted |

## ADR lifecycle

- **Proposed**: under discussion.
- **Accepted**: current architectural direction.
- **Superseded**: replaced by another ADR; retain it for history.
- **Deprecated**: no longer recommended but not necessarily replaced.

## ADR template

```markdown
# ADR-NNN: Decision title

- Status: Proposed | Accepted | Superseded | Deprecated
- Date: YYYY-MM-DD
- Owners: ...
- Supersedes: ... (optional)

## Context
...

## Decision
...

## Consequences
### Positive
- ...

### Negative / trade-offs
- ...

## Revisit when
- ...
```
