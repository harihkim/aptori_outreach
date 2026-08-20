# Implementation Roadmap

> **Status:** Draft v0.3
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The plan has one funding gate and two product milestones. It intentionally avoids presenting optional expansion work as committed prototype scope.

## R0: retrieval viability gate

```text
Freeze evaluation protocol, queries, corpus, labels, provider configs
                              |
                              v
                 run matched provider variants
                              |
                              v
                       R0 GO / NO-GO
                         /        \
                      PASS        FAIL
                       |            |
                       v            v
               Vertical slice   Rework retrieval
                                architecture or
                                product premise
```

R0 deliverables:

- frozen query set, known-thread corpus, labeling protocol, metrics, and thresholds;
- benchmark adapters for separately versioned Search APIs, URL Context, Crawlee HTTP/Parsel, Crawlee Playwright, and CUA;
- Async PRAW comparison only if approved Reddit credentials exist;
- optional pinned Apify Actor or logged-in-browser JSON comparisons only after their credential, policy, supply-chain, write-capability and spend boundaries are frozen;
- immutable Retrieval Observations and deterministic normalized `RedditThread` output;
- provider-aware admission control plus separate counts for jobs, attempts, network activity, returned/deduplicated items and billable units;
- dated result dataset and signed pass/fail report.

R0 passes only under [the quantitative evaluation protocol](../research/retrieval-benchmark.md). A curated demo is not evidence of viability.

Domain/approval contract work may proceed alongside R0 because it does not depend on a retrieval winner. Do not fund Content Studio, Higgsfield integration, broad MCP, analytics, bonus connectors, or UI polish before R0 passes.

## Milestone 1: prototype vertical slice

```text
Campaign
  -> real Reddit discovery
  -> Retrieval Observations
  -> normalized Conversations
  -> dedupe
  -> typed analysis
  -> deterministic ranking
  -> Opportunity Inbox
  -> Conversation detail
  -> Draft + immutable DraftVersion
  -> edit/regenerate creates new DraftVersion
  -> scoped Approval + ApprovedArtifact
  -> CUA prepares exact Reddit composer
  -> STOP: human owns final submit
```

### Required deliverables

| Area | Deliverable | Exit evidence |
|---|---|---|
| Domain foundation | FastAPI, PostgreSQL schema/migrations, Campaigns, Discovery Runs, Retrieval Observations, Conversations, Opportunities, Drafts/Versions, Approval/Artifact, audit | Numbered invariants have database/service tests |
| Retrieval | Only the R0-approved provider variants and explicit routing/failure behavior | Reproduces the exact passing configuration, credential class, rate/spend limits and evidence |
| Intelligence | Pydantic AI-backed typed `analyze_conversation`, deterministic score, frozen labeled eval | Top results meet the accepted evaluation threshold |
| UI | Campaign run, Opportunity Inbox, Conversation detail, Draft/version review, Approval, preparation progress | Operator completes the flow without developer tools |
| Publishing preparation | Closed request by `approval_id`, atomic single-use validation, CUA fill, no final-submit capability | Security tests reject every scope override and replay |
| MCP proof | `list_campaigns`, `search_opportunities`, `get_opportunity` | External MCP client reads the same canonical services |
| Operations | Worker queue, SSE, correlated logs, model/retrieval provenance, failure recovery | Demonstrated retry/recovery without duplicate domain output |

### Prototype definition of done

- R0 has passed with a versioned report.
- A real campaign produces a small ranked set of explainable Opportunities.
- Every model operation is a named, versioned, evaluated LLM Task.
- Editing or regenerating creates a new Draft Version.
- Approval binds exact content, media, destination, Actor Account, and action; it is expiring, revocable, and single-use.
- Publish Preparation accepts no overrides and ends at `READY_FOR_HUMAN`.
- The prototype exposes no callable final-submit path.

## Milestone 2: expansion

Expansion is funded from evidence collected in the vertical slice:

- trend clustering and Content Studio;
- Higgsfield media generation and Media Studio;
- broader MCP creative/review/analytics surface;
- engagement and model-quality analytics;
- approved official Reddit provider productionization and deletion/tombstone automation;
- additional sources/connectors;
- durable workflow engine only if long waits/replay/recovery justify it.

Each capability requires its own value, safety, and operating-cost acceptance criteria. “Architecturally possible” is not a roadmap commitment.

## Immediate engineering sequence

1. Create the `retrieval-eval/` frozen artifacts, admit only reviewed provider variants, and run R0.
2. Translate [Domain Model and State Machines](../architecture/domain-model.md) into Pydantic contracts and migration-ready persistence constraints.
3. Translate [Human Approval and Security](../architecture/approval-security.md) into API schemas and invariant tests.
4. If R0 passes, implement the vertical slice in order of the data flow above.
5. Add the three-tool MCP proof after the corresponding read services exist.

Do not begin by implementing every provider, installing a general-purpose retrieval CLI into the worker, or building a general autonomous agent. The first proof is retrieval viability plus one safe, coherent end-to-end workflow.
