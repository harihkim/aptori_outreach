# Architecture Decision Records

ADRs capture important architectural choices and their consequences. They complement the specs: the spec says what the system should do; an ADR records why a significant design choice was selected.

| ADR | Decision | Status |
|---|---|---|
| [001](001-headless-core-plus-ui-and-mcp.md) | Headless core with first-party UI and MCP adapters | Accepted |
| [002](002-pydantic-ai-primary-orchestrator.md) | Pydantic AI as primary AI orchestration layer | Accepted |
| [003](003-human-approval-exact-content-gate.md) | Human approval for exact outbound artifacts | Accepted |
| [004](004-reddit-provider-abstraction.md) | Pluggable Reddit retrieval providers | Accepted |
| [005](005-bounded-agents-deterministic-workflows.md) | Bounded AI inside deterministic workflows | Accepted |
| [006](006-cua-browser-for-mvp-retrieval.md) | CUA/browser retrieval for the Reddit MVP | Accepted for MVP |
| [007](007-human-final-submit-demo-mode.md) | Preferred demo stops before final Reddit submit | Accepted for demo |
| [008](008-higgsfield-as-media-provider.md) | Higgsfield as external media-generation provider | Accepted for MVP |

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
