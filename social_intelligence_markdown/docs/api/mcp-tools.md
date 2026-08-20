# MCP Tools and Resources

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Agent-facing contract over the same core services used by the web application. MCP is not an alternate system of record.

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

## Tool design rules

1. Prefer domain verbs over database CRUD.
2. Return stable IDs and structured objects suitable for follow-up calls.
3. Research/creative tools may create drafts but never manufacture approval.
4. Queueing for review is allowed; approving on behalf of a human is not.
5. A future publish tool, if exposed, takes only an existing server-issued `approval_id`.
6. MCP authentication and workspace authorization are enforced exactly like REST.

## Example agent flow

```text
discover_opportunities(campaign_id)
  -> get_thread(opportunity_id)
  -> draft_reply(opportunity_id, posture="expertise_first")
  -> queue_for_review(draft_id)
  -> human reviews in UI
```
