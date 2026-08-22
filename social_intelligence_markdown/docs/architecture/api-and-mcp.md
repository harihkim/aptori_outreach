# API and MCP Architecture

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

REST/SSE powers the first-party application; MCP exposes selected domain capabilities to agents. Both authenticate, validate, translate, and call the same application services.

## Adapter shape

```text
SvelteKit -> REST/SSE adapter ---+
                                +-> application services -> domain model -> PostgreSQL
MCP host  -> MCP adapter --------+
```

Business rules, lifecycle transitions, score calculation, Draft Version creation, Approval, and Approved Artifact validation do not live in route handlers or MCP tool functions.

## REST scope

| Area | Representative contract |
|---|---|
| Campaigns/retrieval | Campaign CRUD and Discovery Run creation/status |
| Opportunities | ranked query, detail, save/dismiss |
| Drafts | create Draft, append immutable version, regenerate to new version |
| Review | create/revoke Approval for exact scoped action; record rejection |
| Publishing | create Publish Preparation by `approval_id` only |
| Events | SSE projections for long-running work and review/preparation states |

The hand-written semantics are in [REST and SSE API](../api/rest-api.md). Generated OpenAPI becomes the field-level authority when implementation begins.

## MCP scope

The vertical slice proves headless access with three read tools:

```text
list_campaigns
search_opportunities
get_opportunity
```

The adapter is a streamable-HTTP MCP server mounted at `/mcp` inside the same FastAPI application (see [MCP Tools and Resources](../api/mcp-tools.md)); it is not a separate deployment.

Discovery mutation, creative, review-support, and analytics tools are expansion work. The prototype exposes no MCP Approval, Approved Artifact, Publish Preparation, or arbitrary posting capability.

## Shared contract rules

- Stable domain IDs cross adapters; provider SDK models do not.
- Workspace authorization is enforced in application/domain services as well as adapter authentication.
- Retried writes use idempotency keys and return the original canonical result.
- Draft edits/regeneration always create a new immutable Draft Version.
- Publish Preparation accepts no outbound overrides.
- Pydantic AI deferred-tool state and MCP conversation history are not proof of human approval.
- Long-running work returns a run/job ID; SSE or MCP resources expose projections rather than process-local state.

See [MCP Tools and Resources](../api/mcp-tools.md), [Human Approval and Security](approval-security.md), and [Domain Model and State Machines](domain-model.md).
