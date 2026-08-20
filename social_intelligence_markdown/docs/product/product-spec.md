# Product Specification

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The product requirements document for the Reddit-first MVP and the platform direction beyond Reddit.

## Executive summary

The product is a Reddit-first social intelligence and engagement copilot. A user defines a product, audience, topics, competitors, and positioning constraints. The platform discovers public conversations, normalizes and scores them, highlights high-value opportunities, drafts useful responses and original content, optionally generates image/video assets, and routes every outbound action through explicit human review.

The core value is not scraping. The differentiated layer is deciding which conversations matter, why they matter commercially, how the company should respond, and which recurring market signals should become original content.


> **Positioning.** A headless social intelligence and engagement engine with a human review UI and an agent-native MCP interface. Reddit first; X, LinkedIn, Hacker News, GitHub, YouTube, Stack Overflow, RSS, and the broader web are future connectors.

## Product principles

| **Principle**                                | **Implication**                                                                                                                                      |
|----------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| Human approval is mandatory                  | Automation may discover, read, analyze, draft, generate media, and navigate. It must not publish or engage until an explicit approval record exists. |
| Helpful before promotional                   | Relevance does not imply promotion. The system may recommend an expert-only reply with no product mention.                                           |
| Opportunity intelligence over raw monitoring | The default view is a ranked opportunity inbox, not a dump of keyword matches.                                                                       |
| Deterministic workflow, bounded AI           | Agents operate inside defined steps. State transitions, authorization, deduplication, retries, and audit logging remain application logic.           |
| Headless core, multiple interfaces           | The same domain services power the Svelte application, MCP tools/resources, and future external APIs.                                                |
| Provider abstraction                         | Reddit retrieval is not coupled to one technique. Browser/CUA is the MVP provider; approved official access can be added later.                      |
| Evidence and provenance                      | Every opportunity retains source URL, retrieval method, timestamps, relevant excerpts, model outputs, and decision history.                          |

## Goals and non-goals

### Goals

- Demonstrate high-quality Reddit discovery without requiring Reddit developer approval for the MVP demo path.

- Reduce a large set of noisy conversations into a small, explainable, prioritized opportunity queue.

- Generate context-aware response drafts and original content while preserving human control.

- Detect repeated pains, questions, competitor mentions, and market themes that can drive content strategy.

- Generate supporting image/video assets through Higgsfield when a content idea benefits from media.

- Expose the platform to capable agents through MCP without making MCP the only user experience.

- Make future social-network connectors additive rather than architectural rewrites.

### Non-goals for the first release

- Autonomous posting, commenting, direct messaging, voting, following, or other engagement.

- High-volume scraping or attempts to bypass access controls, blocks, CAPTCHAs, or platform safety mechanisms.

- A fully autonomous general-purpose marketing agent.

- Full attribution/marketing analytics across all external platforms.

- Enterprise multi-tenant billing, complex RBAC, or a marketplace of integrations.

- Production-grade support for LinkedIn/X in the required demonstration; these are bonus/future connectors.

## Target users and jobs-to-be-done

| **User**                        | **Primary job**                                                              | **What success looks like**                                                                 |
|---------------------------------|------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| Founder / product leader        | Know what the market is discussing and where the company can contribute.     | A short daily list of credible opportunities and emerging themes.                           |
| Growth / marketing              | Turn real conversations into useful posts, comments, and visual campaigns.   | Higher-quality content ideas, faster drafting, less generic promotion.                      |
| Developer relations / community | Find technical questions where expert participation is valuable.             | Timely, accurate, non-spammy contributions in relevant communities.                         |
| Agent user                      | Ask an external agent to research, rank, or prepare work using the platform. | Structured MCP tools that return canonical platform data and queue drafts for human review. |

## Functional requirements

| **ID** | **Capability**         | **Requirement**                                                                                                                                       |
|--------|------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| FR-01  | Campaign configuration | Create/edit campaigns with product context, keywords, communities, personas, competitors, positioning, promotion posture, approved/prohibited claims. |
| FR-02  | Reddit discovery       | Discover candidate Reddit URLs/conversations through a pluggable retrieval provider, initially browser/CUA plus search-based discovery.               |
| FR-03  | Thread extraction      | Collect normalized post metadata and relevant thread comments without performing engagement actions.                                                  |
| FR-04  | Deduplication          | Detect URL, post-ID, and semantic duplicates before model analysis.                                                                                   |
| FR-05  | Analysis               | Produce validated structured outputs for relevance, intent, pain, persona, product fit, replyability, promotion fit, action, and reason.              |
| FR-06  | Opportunity inbox      | Rank, filter, search, dismiss, save, and inspect opportunities.                                                                                       |
| FR-07  | Draft generation       | Generate response approaches and drafts consistent with thread context, campaign guidance, and promotion posture.                                     |
| FR-08  | Trend clustering       | Cluster conversations into themes and show counts, recency, and directional change where enough history exists.                                       |
| FR-09  | Content generation     | Generate original Reddit posts and optional variants for other channels from company knowledge plus aggregated themes.                                |
| FR-10  | Media generation       | Submit, poll, receive webhook, store, and review Higgsfield image/video jobs.                                                                         |
| FR-11  | Human approval         | Require explicit approval for the exact outbound artifact. Edits after approval invalidate the approval.                                              |
| FR-12  | Browser preparation    | Open the correct Reddit thread and optionally fill the approved draft; initial mode stops before final submit.                                        |
| FR-13  | Auditability           | Persist source provenance, model/version, prompts/templates, analysis, draft history, approvals, publish attempts, and feedback.                      |
| FR-14  | MCP interface          | Expose high-level research, analysis, creative, and review capabilities as MCP tools/resources without bypassing approval controls.                   |

## Success metrics

| **Metric**                 | **Why it matters**                        | **MVP target / use**                                   |
|----------------------------|-------------------------------------------|--------------------------------------------------------|
| Precision@10 opportunities | Measures ranking quality.                 | Primary quality metric; manually label top results.    |
| Noise reduction            | Shows value over keyword search.          | Share of raw candidates removed before inbox.          |
| Draft acceptance rate      | Measures usefulness of generation.        | Accepted with minor/no edits vs regenerated/rejected.  |
| Time-to-triage             | Measures operator efficiency.             | Time to review daily opportunity set.                  |
| Human override rate        | Reveals scoring/generation failure modes. | Track reason categories, not just a percentage.        |
| Retrieval coverage         | Compares discovery providers.             | Unique relevant conversations per method/cost/latency. |
| Safety violations          | Protects the product boundary.            | Target zero outbound actions without valid approval.   |

## MVP acceptance criteria

- A user can configure a Reddit campaign and run discovery end-to-end.

- The system can retrieve and normalize a meaningful set of recent Reddit conversations using the browser/search retrieval path.

- At least 80% of top-10 demo opportunities are judged relevant by the demo operator on a prepared test campaign.

- Each opportunity includes source, explanation, structured scores, and a recommended action.

- A response draft can be generated, edited, approved, and passed to browser preparation without any automatic final submission.

- Editing an approved draft invalidates its approval until reviewed again.

- A repeated theme can be converted into an original content draft and at least one Higgsfield media job.

- The same campaign/opportunity data can be queried from a minimal MCP server.

- All important actions appear in an audit log.

## Product decisions captured

| **Decision**                                                                           | **Status**                   |
|----------------------------------------------------------------------------------------|------------------------------|
| Reddit is the required demo; other networks are bonus.                                 | Committed                    |
| No automatic outbound engagement.                                                      | Committed                    |
| MVP retrieval does not depend on Reddit developer approval.                            | Committed                    |
| Use browser/CUA and search/URL-context experiments for retrieval.                      | Committed for prototype      |
| Core platform is headless; Svelte UI and MCP are first-class adapters.                 | Committed                    |
| FastAPI + Pydantic AI + PostgreSQL backend.                                            | Recommended baseline         |
| Svelte 5 + SvelteKit + TypeScript + shadcn-svelte/Bits UI + useful TanStack libraries. | Recommended baseline         |
| Higgsfield powers optional image/video generation.                                     | Committed integration target |

## Research references

See the [research source catalog](../research/source-catalog.md) for the primary documentation and open-source repositories used during the initial design.
