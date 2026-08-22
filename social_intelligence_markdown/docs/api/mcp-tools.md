# MCP Tools and Resources

> **Status:** Draft v0.3
> **Canonical:** Yes - this Markdown documentation is the source of truth.

MCP is an agent-facing adapter over the same application services and authorization rules as REST. It is neither an alternate system of record nor a second workflow engine.

## Transport

The prototype MCP adapter speaks **streamable HTTP** (the standard remote transport since spec revisions 2025-03-26 / 2025-06-18, which deprecated HTTP+SSE), mounted at `/mcp` inside the existing FastAPI application via the official `mcp` Python SDK's ASGI app — no separate process or stdio entrypoint. Authentication matches REST rules (bearer token for the internal deployment).

Implementation notes from the SDK's tracker: forward the MCP app's lifespan to the parent FastAPI app (otherwise the session manager never starts and every request 404s), and account for trailing-slash redirect behavior when mounting at `/mcp`.

## Prototype proof

The first vertical slice needs only enough MCP surface to prove that domain services are headless:

| Tool | Purpose |
|---|---|
| `list_campaigns` | Return campaigns visible to the authenticated workspace principal. |
| `search_opportunities` | Query canonical ranked Opportunities by campaign and filters. |
| `get_opportunity` | Return one Opportunity with Conversation, analysis, and provenance projections. |

These read tools should be implemented after their underlying domain services exist, without delaying the ADR-012 prototype smoke, full Retrieval Gate R0 work, or the first-party review workflow.

## Expansion tools

| Category | Later tools |
|---|---|
| Discovery | `start_discovery_run`, `get_discovery_run`, `get_conversation` |
| Intelligence | `analyze_conversation`, `explain_opportunity`, `find_emerging_topics`, `cluster_conversations` |
| Creative | `create_reply_draft`, `create_draft_version`, `regenerate_draft`, `create_content_package`, `create_media_brief` |
| Review support | `list_pending_reviews`, `get_draft`, `queue_for_review` |
| Analytics | `campaign_summary`, `retrieval_benchmark`, `model_evaluation_summary` |

Creating or revising a Draft always returns a new immutable Draft Version. MCP tools may queue a version for human review but cannot create an Approval, Approved Artifact, or Publish Preparation.

## Resources

```text
campaign://{campaign_id}
opportunity://{opportunity_id}
conversation://{conversation_id}
draft://{draft_id}
draft-version://{draft_version_id}
retrieval-observation://{observation_id}
```

Resources are projections of canonical state. Sensitive account credentials, raw browser secrets, and unredacted model telemetry are never resources.

## Capability boundary

- Do not expose generic database CRUD.
- Do not expose `approve`, `create_approved_artifact`, `prepare_publish`, or arbitrary posting tools in the prototype MCP server.
- External clients cannot prove human approval through message history or Pydantic AI deferred-tool results.
- A future publishing MCP tool, if separately approved, may accept only `approval_id`; it cannot accept text, media, destination, Actor Account, or action overrides.
- Authentication and workspace authorization are identical to REST.
- Tool functions contain adapter logic only and call application/domain services.

## Example prototype flow

```text
list_campaigns()
  -> search_opportunities(campaign_id, limit=10)
  -> get_opportunity(opportunity_id)
```

## Example later creative flow

```text
create_reply_draft(opportunity_id)
  -> create_draft_version(draft_id, base_version_id, text)
  -> queue_for_review(draft_version_id)
  -> human reviews and approves in first-party UI
```

See [API and MCP Architecture](../architecture/api-and-mcp.md), [REST and SSE API](rest-api.md), and [Human Approval and Security](../architecture/approval-security.md).
