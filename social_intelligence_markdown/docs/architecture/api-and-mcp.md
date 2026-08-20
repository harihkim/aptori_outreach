# API and MCP Architecture

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

REST/SSE powers the first-party application; MCP exposes high-level domain capabilities to agents. Both are thin adapters over shared domain services.

## API surface

| **Area**      | **Representative endpoints**                                                                      |
|---------------|---------------------------------------------------------------------------------------------------|
| Campaigns     | POST /campaigns; GET/PATCH /campaigns/{id}; POST /campaigns/{id}/discover                         |
| Opportunities | GET /opportunities; GET /opportunities/{id}; POST /{id}/dismiss; POST /{id}/save                  |
| Analysis      | POST /conversations/{id}/analyze; POST /campaigns/{id}/cluster-themes                             |
| Drafts        | POST /opportunities/{id}/drafts; PATCH /drafts/{id}; POST /drafts/{id}/regenerate                 |
| Review        | GET /reviews/pending; POST /drafts/{id}/approve; POST /drafts/{id}/reject                         |
| Media         | POST /media/jobs; GET /media/jobs/{id}; POST /webhooks/higgsfield                                 |
| Publishing    | POST /publish/prepare/{approval_id}; publish execution disabled unless server validates approval. |
| Events        | GET /events/stream (SSE) for discovery, analysis, browser, and media job progress.                |

## MCP design

MCP should expose domain-level operations, not raw database CRUD. External agents should be able to research, analyze, create drafts, and queue review while preserving the same server-side authorization and approval rules as the first-party UI.

### Tools

| **Category** | **Tools**                                                                                                        |
|--------------|------------------------------------------------------------------------------------------------------------------|
| Discovery    | search_reddit, discover_opportunities, refresh_campaign, get_thread                                              |
| Intelligence | analyze_conversation, rank_opportunities, explain_opportunity, find_emerging_topics, cluster_conversations       |
| Creative     | draft_reply, draft_reddit_post, create_content_ideas, create_content_package, create_media_brief, generate_media |
| Review       | list_pending_reviews, get_draft, revise_draft, queue_for_review                                                  |
| Analytics    | campaign_summary, topic_trends, retrieval_benchmark, engagement_summary                                          |

### Resources and prompts


```text
Resources
campaign://{campaign_id}
opportunity://{opportunity_id}
conversation://{conversation_id}
draft://{draft_id}
theme://{theme_id}
Prompt templates
/reddit-opportunities
/create-content
/review-drafts
```


Do not initially expose a generic post_reddit_comment(text=...) MCP tool. If publishing through MCP is added later, it should accept only an approval_id for an immutable approved artifact.

## Boundary rule

Do not put business rules in route handlers or MCP tool functions. They authenticate/validate/translate and call domain services. This is what prevents the UI and external agents from developing different approval or scoring behavior.

Detailed interface notes: [REST/SSE API](../api/rest-api.md) and [MCP tools/resources](../api/mcp-tools.md).
