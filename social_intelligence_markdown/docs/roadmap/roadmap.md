# Implementation Roadmap

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Prioritizes a convincing Reddit-first demonstration while preserving the architecture needed for later connectors and production hardening.

## Delivery strategy

Optimize the first release around one compelling Reddit demonstration rather than shallow multi-platform breadth. Build the durable domain model and provider interfaces needed for future expansion, but spend implementation effort on discovery quality, opportunity ranking, review UX, and the human approval boundary.


> Definition of done for the first demonstration
> A campaign finds real Reddit conversations, ranks a small set of credible opportunities, explains each choice, drafts a useful response, routes the exact draft through human approval, prepares it in Reddit without auto-submitting, and turns at least one repeated market theme into original content plus a Higgsfield media asset.

## Indicative implementation roadmap

| **Phase**               | **Outcome**                  | **Main deliverables**                                                                              | **Exit gate**                                                                           |
|-------------------------|------------------------------|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| 0. Spike               | Prove retrieval paths.       | CUA sandbox, Gemini Search/URL Context experiments, normalized thread schema, benchmark harness.   | At least one reliable path retrieves recent Reddit posts + useful comment context.      |
| 1. Core                | Headless domain foundation.  | FastAPI, PostgreSQL models/migrations, campaigns, discovery runs, conversations, audit/events.     | End-to-end ingest persists canonical conversations idempotently.                        |
| 2. Intelligence        | Opportunity engine.          | Pydantic AI schemas, cheap filter, scoring, explanations, opportunity inbox API, labeled eval set. | Top results show acceptable precision on test campaigns.                                |
| 3. Product UI          | Operational workflow.        | SvelteKit shell, Campaigns, Opportunities, Conversation detail, SSE job progress.                  | Operator can run discovery and triage without developer tools.                          |
| 4. Creative + approval | Human-controlled engagement. | Drafting, versioning, edit/reject/approve, content hash, browser prepare flow.                     | No outbound preparation can occur without valid approval; edit invalidates approval.    |
| 5. Content + media     | Trend-to-content workflow.   | Theme clustering, Content Studio, Higgsfield image/video job integration, asset storage.           | One theme produces an approved content package and media asset.                         |
| 6. Agent interface     | MCP access.                  | High-level tools/resources/prompts over existing domain services.                                  | External MCP client can discover/analyze/draft/queue review without bypassing approval. |
| 7. Bonus connectors    | Demonstrate extensibility.   | Optional HN/GitHub/RSS/X/LinkedIn research connector where feasible/appropriate.                   | At least one non-Reddit source uses the same normalized/intelligence pipeline.          |

## Suggested 6-week build sequence

This is an indicative sequence, not a commitment. Parallelize frontend shell and retrieval benchmarking if two engineers are available.

| **Week** | **Focus**                 | **Deliverable**                                                                               |
|----------|---------------------------|-----------------------------------------------------------------------------------------------|
| 1        | Retrieval spike + schemas | CUA environment; Gemini Search/URL Context benchmark; normalized RedditThread; sample corpus. |
| 2        | Backend core              | Campaign/discovery/conversation models, jobs, dedupe, audit, REST/SSE.                        |
| 3        | Opportunity engine        | Pydantic AI analysis, scoring, eval harness, Opportunities API and early UI.                  |
| 4        | Review workflow           | Conversation view, drafts, versions, exact-text approval, browser prepare flow.               |
| 5        | Content + media           | Theme clustering, Content Studio, Higgsfield webhooks/assets, polish.                         |
| 6        | MCP + demo hardening      | MCP interface, golden demo corpus/campaign, failure recovery, observability, rehearsal.       |

## Next engineering artifacts to create

- OpenAPI schema and endpoint contracts for Campaigns, Opportunities, Drafts, Approvals, Media, and Events.

- SQLAlchemy models and Alembic migration plan based on the proposed data model.

- Pydantic schemas for RedditThread, ConversationAnalysis, Draft, Approval, and provider results.

- MCP tool/resource specification with JSON schemas and authorization requirements.

- Retrieval benchmark harness with a fixed query set and manual relevance labels.

- Threat model focused on browser sessions, prompt injection, approval bypass, and connector credentials.

- Figma or coded Svelte prototype for Overview, Opportunities, Conversation, and Approvals screens.

## Sequencing principle

Do not start by implementing every provider or a general autonomous agent. First prove retrieval quality, normalization, opportunity scoring, human review and a single browser preparation path. Add MCP early enough to validate the headless boundary, but keep the UI as the primary review/control surface.
