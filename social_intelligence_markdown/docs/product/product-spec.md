# Product Specification

> **Status:** Draft v0.4
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The product is a Reddit-first social intelligence and engagement copilot. It turns a campaign definition into a small, explainable Opportunity Inbox, then helps a human create and safely prepare a useful response. Retrieval viability is not assumed: the Internal Product uses a dated provisional route while full R0 remains the graduation and external-use gate.

## Product thesis

The differentiated value is deciding which conversations matter, why they matter, what helpful action fits the community context, and how repeated signals may later become original content. Retrieval is necessary infrastructure whose coverage, completeness, legality, reliability, latency, and cost must be proven at Gate R0.

> **Positioning:** a headless opportunity-intelligence engine with a first-party human review surface and a bounded MCP adapter. Reddit first; other sources and content/media workflows are expansion.

## Product principles

| Principle | Implication |
|---|---|
| Human authorization covers the exact action | Approval binds immutable text/media, Actor Account, action type, and Destination; edits or substitutions require approval again |
| Helpful before promotional | Relevance can produce `monitor`, `do not respond`, or an expert-only response with no product mention |
| Opportunity intelligence over monitoring | The default output is a ranked, explainable queue rather than keyword-result volume |
| Retrieval viability before product breadth | ADR-012 permits the team-only vertical slice after a frozen smoke gate; provider graduation and external use still require full R0 |
| Deterministic control plane, typed LLM execution | Application code owns state, scoring, routing, retries, authorization, and persistence; Pydantic AI executes named bounded semantic tasks |
| Headless core, bounded adapters | UI, REST, MCP, workers, and providers use the same domain services and cannot create alternate rules |
| Evidence and provenance | Every Candidate, Conversation, Analysis, Draft Version, Approval, and preparation is reconstructable from versioned evidence |
| No access-control evasion | A provider or browser capability never grants permission to bypass blocks, authentication, CAPTCHAs, rate limits, or platform terms |

## Goals

### Gate R0

- Demonstrate at least one compliant end-to-end discovery and thread-fetch route meeting frozen quantitative thresholds.
- Measure discovery relevance, thread completeness, reliability, failure semantics, latency, and cost/useful-opportunity.
- Preserve immutable retrieval evidence and explicit policy/access stops.

### Prototype vertical slice

- Configure a Campaign and run real Reddit discovery using the exact ADR-012 provisional route, or a later R0-graduated route.
- Reduce noisy Candidates to ranked, explainable Opportunities.
- Generate, edit, and regenerate typed response candidates as immutable Draft Versions.
- Capture scoped, expiring, revocable, single-use human authorization.
- Prepare the exact approved Reddit composer and stop before final submit.
- Prove the headless boundary with three read-only MCP tools.

### Expansion

- Detect recurring themes and create original content packages.
- Generate optional image/video assets through Higgsfield.
- Add broader MCP, analytics, approved official Reddit productionization, and additional sources based on evidence.

## Non-goals for the prototype

- Autonomous posting, commenting, messaging, voting, following, or final submission.
- High-volume scraping or bypass of access controls and safety mechanisms.
- Treating a provider token, proxy pool, browser session, managed Actor or general-purpose CLI as permission or as a production retrieval contract.
- A general-purpose autonomous marketing agent.
- Content Studio, Higgsfield integration, broad analytics, or multi-platform breadth on the critical path.
- Enterprise billing, complex RBAC, or an integration marketplace.
- Treating Pydantic AI deferred-tool approval or MCP history as publishing authorization.

## Target users and jobs

| User | Primary job | Prototype success |
|---|---|---|
| Founder/product leader | Find credible market conversations worth attention | A short, explainable daily Opportunity queue |
| Growth/community operator | Prepare helpful context-aware responses safely | Useful Draft Versions with explicit action-scoped review |
| Developer relations | Find technical questions where expertise adds value | Timely, accurate, non-spammy recommendations |
| Agent user | Query canonical research state from an external agent | Stable MCP reads over the same services as the UI |

## Functional requirements

| ID | Capability | Requirement |
|---|---|---|
| FR-00 | Retrieval gate | For the Internal Product, freeze and pass the ADR-012 prototype smoke before completing the retrieval increment; pass full R0 before provider graduation or external use |
| FR-01 | Campaign configuration | Capture product context, audience, keywords, communities, competitors, positioning, promotion posture, approved/prohibited claims |
| FR-02 | Discovery | Use the exact ADR-012 provisional or R0-graduated provider variant and record every attempt, configuration identity, and policy outcome as a Retrieval Observation |
| FR-03 | Thread fetching | Use the exact ADR-012 provisional or R0-graduated fetcher variant and return typed success/incomplete/access/failure semantics |
| FR-04 | Normalization/deduplication | Deterministically normalize immutable observations and deduplicate by source ID/URL before semantic analysis |
| FR-05 | Typed analysis | Use versioned Pydantic AI LLM Tasks for semantic factors; compute overall score deterministically |
| FR-06 | Opportunity Inbox | Rank, filter, search, dismiss, save, and inspect Opportunities with evidence and rationale |
| FR-07 | Drafting | Create a Draft whose generation, regeneration, and edits append immutable Draft Versions |
| FR-08 | Human approval | Bind one Draft Version, finalized media checksums, Actor Account, action, Destination, approver, expiry, and single-use limit |
| FR-09 | Browser preparation | Accept only `approval_id`, atomically revalidate/consume the artifact, fill the exact composer, and stop before submit |
| FR-10 | Auditability | Persist retrieval/model/version/approval/preparation provenance and security-relevant failures |
| FR-11 | MCP proof | Expose `list_campaigns`, `search_opportunities`, and `get_opportunity` without approval/publishing capabilities |
| FR-12 | Trend/content/media | Expansion only after vertical-slice evidence justifies it |

## Success metrics

| Metric | Purpose |
|---|---|
| ADR-012 smoke pass/fail | Determines whether the provisional route can complete the internal retrieval increment |
| R0 pass/fail | Determines whether a provider route graduates beyond the time-box or can support future external use |
| Precision@5/10 and NDCG@10 | Measures discovery/ranking usefulness |
| Cost/useful opportunity surfaced | Measures retrieval economics |
| Known-thread completeness | Measures whether analysis has enough source context |
| Noise reduction | Measures value over raw keyword discovery |
| Draft acceptance/edit distance | Measures generation usefulness without hiding human changes |
| Time to triage | Measures operator efficiency |
| Human override reasons | Exposes systematic scoring/generation errors |
| Authorization violations | Target zero preparations without a valid complete Approved Artifact |

## Prototype acceptance criteria

- The ADR-012 prototype smoke passes for the Internal Product, or R0 passes under the committed frozen evaluation protocol.
- A user configures a Campaign and runs the measured real Reddit route end to end.
- Every retrieval attempt has immutable provenance and every Conversation can be reconstructed.
- The Opportunity Inbox meets the accepted quality threshold and explains each recommendation.
- Every semantic model call is a named, versioned Pydantic AI LLM Task with usage/provenance.
- An edit or regeneration creates a new Draft Version; no content-bearing version is mutated.
- Approval covers exact text, media, Actor Account, action, and Destination, with expiry/revocation/single-use behavior.
- Publish Preparation accepts no overrides and the prototype stops at `READY_FOR_HUMAN`.
- The MCP proof reads the same Campaign/Opportunity data without bypassing review or authorization.
- Numbered domain and security invariants have automated tests.

## Committed decisions

| Decision | Status |
|---|---|
| ADR-012 provisionally selects Obscura + DuckDuckGo Lite discovery and Obscura thread fetching for the Internal Product through 2026-09-20 | Committed time-boxed exception |
| Provider graduation and any future external use must pass R0 | Committed gate |
| No automatic outbound engagement or final submit in prototype | Committed |
| Draft and Draft Version are distinct; versions are immutable | Committed |
| Approval and Approved Artifact are distinct; authorization binds the complete action | Committed |
| Pydantic AI is the default typed LLM execution layer, not only an agent framework | Committed architecture |
| Discovery and thread fetching use separate provider ports | Committed architecture |
| Async PRAW is the future approved official implementation; not an MVP dependency | Conditional on access |
| Crawlee HTTP/Playwright and CUA are benchmark variants; CUA remains last fallback | Experimental until R0 |
| Agent Reach is reference engineering only; session-backed routes require isolated read-only adapters | Committed security boundary |
| Brave, DuckDuckGo-page and Apify Actor routes are separate configured benchmark variants, never a generic keyless/commercial switch | Experimental until R0 and policy review |
| MCP begins as a three-tool read proof | Committed prototype scope |
| Content Studio and Higgsfield are expansion | Deferred |

See [Implementation Roadmap](../roadmap/roadmap.md), [Domain Model and State Machines](../architecture/domain-model.md), [ADR-012](../adr/012-time-boxed-internal-retrieval-selection.md), and [Retrieval Gate R0](../research/retrieval-benchmark.md).
