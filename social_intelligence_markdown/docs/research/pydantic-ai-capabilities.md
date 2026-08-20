# Pydantic AI Capabilities and Recommended Scope

> **Status:** Research note
> **Researched:** 2026-08-20
> **Sources:** Official Pydantic AI documentation only. Revalidate before implementation because the framework is evolving.
> **Incorporated:** Canonical typed-LLM architecture and ADRs; reconfirmed for documentation v0.3.

## Conclusion

Use Pydantic AI as the project's **default typed LLM execution layer**, not only for open-ended agents or tool-calling workflows.

That means using it for bounded calls such as conversation extraction, classification, thread synthesis, promotion-posture assessment, draft generation and media briefs, even when a call has no tools and completes in one model turn. Pydantic AI explicitly positions itself for work ranging from simple typed data extraction to long-running multi-agent systems, and its `Agent` abstraction combines a model, instructions, typed dependencies, typed output, retries and optional tools; using `Agent` does not imply autonomous control of an application. ([Overview](https://pydantic.dev/docs/ai/overview/), [Agents](https://pydantic.dev/docs/ai/core-concepts/agent/))

Do **not** make Pydantic AI the owner of campaigns, job state, scoring formulas, provider policy, persistence, audit, approval or publishing. Those remain deterministic application/domain concerns, consistent with [ADR-005](../adr/005-bounded-agents-deterministic-workflows.md). Pydantic AI should execute bounded semantic tasks inside those workflows.

In short:

```text
Application workflow owns: state, routing policy, retries across jobs,
idempotency, persistence, authorization, approval and audit

Pydantic AI owns: model invocation, typed output, model-facing retries,
optional tools, per-run limits, streaming events and model telemetry
```

## Capability assessment

| Capability | What Pydantic AI provides | Recommended use here | Important boundary |
|---|---|---|---|
| Structured extraction and classification | `output_type` accepts Pydantic models, dataclasses, typed dictionaries, scalars, collections and unions. Pydantic AI builds the JSON schema, validates the result and preserves the output type. It supports tool-based, provider-native and prompted structured-output modes. ([Output](https://pydantic.dev/docs/ai/core-concepts/output/)) | Use for `ConversationAnalysis`, thread summaries, intent/persona/topic classification, recommended-action inputs, claim/risk extraction and `MediaBrief`. A task may be a single model call with no tools. | Validation proves schema conformance, not truth, calibration or product correctness. Keep deterministic validation and labeled evaluations outside the model call. Provider-native structured output is not universally supported, while prompted output is documented as the least reliable mode. |
| Drafting and generation | Agent output may be text or a typed object, and output functions/validators can post-process or reject an answer with `ModelRetry`. ([Output functions and validators](https://pydantic.dev/docs/ai/core-concepts/output/)) | Prefer a typed `DraftCandidate` containing `text`, `posture`, `claims`, `source_refs`, `uncertainties` and `safety_flags`, rather than returning only an unstructured string. Persist the resulting immutable `DraftVersion` in the domain layer. | A valid draft is not an approved draft. Pydantic output validation must never create approval or publish eligibility. Model retries create new model turns and cost money. |
| Model/provider portability | Pydantic AI exposes vendor-SDK-independent model classes and supports multiple providers; model profiles describe capabilities and schema restrictions. Switching the model can be as small as changing the model identifier, subject to feature compatibility. ([Models and providers](https://pydantic.dev/docs/ai/models/overview/)) | Put Pydantic AI behind a small internal `LLMTaskRunner` and configure model IDs per task/version. Run the same evaluation corpus against each candidate provider. | Portability is not equivalence. Native tools, structured-output modes, JSON-schema support and model settings differ. Maintain a tested compatibility matrix rather than promising transparent substitution. |
| Model routing and fallback | A run may choose its model dynamically; the `SelectModel` capability can select from dependencies, history, usage or step context. `FallbackModel` moves to another model after configured failures. ([Select Model](https://pydantic.dev/docs/ai/capabilities/select-model/), [Fallback Model](https://pydantic.dev/docs/ai/models/overview/#fallback-model)) | Keep task-level routing deterministic and configuration-driven: cheap model for ordinary analysis, stronger model for explicitly identified borderline/high-value cases, and a separate availability fallback chain. | Do not let the model decide business routing. By default, validation errors cause a retry of the same model rather than fallback; response-based fallback is currently non-streaming only. Provider SDK retries can also delay fallback. |
| Retries | Pydantic AI distinguishes transport retries, model fallback, tool retries, output retries and model-request-hook retries. It explicitly does not retry an entire agent run. ([Retries](https://pydantic.dev/docs/ai/core-concepts/retries/), [HTTP request retries](https://pydantic.dev/docs/ai/models/http-request-retries/)) | Use transport retries for transient HTTP/rate-limit failures, small output-retry budgets for malformed/semantically invalid structured results, and the worker/job layer for whole-task retry and recovery. Persist attempt counts and failure classes. | Do not stack opaque retry loops. Every output/tool retry is another model request. Whole-job retry must stay idempotent and must not create duplicate analyses or draft versions for the same attempt key. |
| Streaming | Agents can stream text, structured-output snapshots, raw model events and tool events. Structured snapshots may omit incomplete fields until partial validation succeeds. ([Streaming](https://pydantic.dev/docs/ai/core-concepts/output/#streamed-results), [agent event streams](https://pydantic.dev/docs/ai/core-concepts/agent/#streaming-events-and-final-output)) | Stream draft previews and worker progress to the UI where it improves perceived latency. Forward selected events through the application's SSE/job-event contract. Persist only the final validated output as the authoritative analysis or draft version. | Partial structured output is not domain state. Streaming has early-final-result and cancellation semantics that require care when tools and final output appear together. Do not drive approval or scoring from partial output. |
| Dependency injection | Typed dependencies are available to instructions, tools and output validators, and can be overridden for tests. ([Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/)) | Inject narrow, stage-specific services and immutable context: campaign guidance, approved company knowledge, clock, correlation metadata and read-only source access. Use overrides for tests. | Dependency injection is not a permission boundary. The analysis/drafting task must never receive publishing credentials or a publishing service; capability absence should enforce separation. |
| Usage and cost limits | `UsageLimits` can bound tokens, requests, tool calls, per-request input and estimated cost; run results expose usage. The documentation warns that cost calculation is best-effort and is not a hard billing guarantee. ([Usage limits](https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits)) | Set task-specific request/token limits, record actual usage with each model run, and enforce campaign/workspace budgets in application code. Use provider spend controls as a backstop. | Per-run limits do not replace aggregate tenant budgets, queue admission control or provider billing limits. Some limits can only be detected after a response has already been generated and billed. |
| Evaluation and testing | Pydantic Evals supports datasets, cases, tasks, built-in/custom/LLM/trace-based evaluators and experiment reports for systems ranging from single calls to multi-agent applications. `TestModel`, `FunctionModel`, dependency overrides and a global model-request block support unit tests. ([Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/), [Unit testing](https://pydantic.dev/docs/ai/guides/testing/)) | Use one evaluation suite per semantic task: analysis labels/calibration, recommended-action agreement, draft quality and media-brief completeness. Add deterministic evaluators first and carefully scoped LLM judges for subjective draft qualities. Run provider/model/prompt/schema variants against frozen datasets. | Evals do not supply the project's retrieval metrics automatically; precision@K, NDCG, provider overlap and cost/useful-opportunity remain domain-specific calculations. `TestModel` validates integration/schema behavior, not real-model quality. |
| Durable execution | Pydantic AI documents supported integrations with Temporal, DBOS, Prefect and Restate for fault-tolerant, long-running and human-in-the-loop agent runs. A durability capability only becomes durable when executed inside the corresponding workflow runtime. ([Durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Temporal details](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/)) | Keep the current Redis-backed worker plan for the prototype. Reconsider a supported durable runtime when workflows genuinely need multi-day waits, replay, suspended human turns or reliable recovery across many external calls. | Pydantic AI is an integration with a durable engine, not a durable engine by itself. Durable activities can be retried from the beginning, so outbound side effects still need idempotency and server-side authorization. |
| Deferred tools and human review | Tools may require approval or defer execution, either resolved inline or by ending a run with `DeferredToolRequests` and resuming in a later run. The official docs explicitly warn that this approval mechanism is not an authorization boundary against an untrusted client. ([Deferred tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)) | Use deferral to pause an agent-facing workflow or queue work for the first-party review UI. It can represent “human input needed” in an LLM interaction. | It must not become the canonical publish authorization. The project's server-issued `Approval` and immutable `ApprovedArtifact` bind content, media, Actor Account, destination and action, and must be revalidated by `PublishPreparation`. Never trust client-supplied message history as proof of approval. |
| MCP | Pydantic AI agents can consume MCP tools and can be used inside MCP servers. Its MCP capability supports local execution and optional provider-native MCP with fallback. ([MCP](https://pydantic.dev/docs/ai/mcp/overview/)) | It is suitable for implementing or consuming MCP at the AI boundary, but the product's MCP server should remain a thin adapter over application services, as specified in [MCP Tools and Resources](../api/mcp-tools.md). | MCP must not become a second business-logic or authorization path. Do not expose raw publishing tools or allow an external MCP client to manufacture approval. |
| Observability | Pydantic AI emits OpenTelemetry traces for agent runs, model requests and tool calls and can use Logfire or another OTel backend. Instrumentation can exclude prompts/completions and binary content; it also reports token, estimated-cost and streaming latency metrics. ([Observability](https://pydantic.dev/docs/ai/integrations/logfire/)) | Correlate each Pydantic AI run with the application's HTTP request, worker job, campaign, conversation/opportunity and prompt/schema versions. Prefer content-redacted production telemetry by default and explicitly govern any captured Reddit text or proprietary prompt content. | Telemetry is not the audit log or system of record. Keep approval, artifact, job and model-run provenance in PostgreSQL. OpenTelemetry conventions and emitted attributes may change across minor releases. |

## Recommended project shape

Do not create one generic marketing agent. Create a catalog of named, independently evaluated LLM tasks behind one execution interface:

```text
Domain worker/service
        |
        v
LLMTaskRunner
  - task_id + prompt_version + schema_version
  - model policy + fallback policy
  - retry and usage limits
  - correlation metadata
        |
        v
Pydantic AI Agent[TaskDependencies, TaskOutput]
  - zero tools for ordinary extraction/classification/drafting
  - narrow read tools only when the task genuinely needs them
        |
        v
Final validated output + usage/provenance
        |
        v
Domain validation -> deterministic score/state transition -> persist
```

Suggested first task catalog:

| Task | Output | Tools? |
|---|---|---|
| `analyze_conversation` | `ConversationAnalysis` factors, rationale, confidence and recommended action | None after normalized thread context is supplied |
| `synthesize_thread` | Summary, actors/positions, unresolved questions, evidence references | None normally |
| `assess_claims_and_risk` | Claims, support status, uncertainty and prohibited-claim flags | Optional narrow retrieval/knowledge lookup |
| `generate_reply_candidates` | One or more typed `DraftCandidate`s | Optional read-only company knowledge |
| `generate_content_package` | Typed platform variants and provenance | Optional read-only sources |
| `create_media_brief` | Typed `MediaBrief` | None |
| `label_theme_cluster` | Stable topic label and explanation for a deterministic cluster | None |

Normalization, URL/post-ID deduplication, score calculation, state transitions, approval, authorization and publish preparation should not be LLM tasks.

## API choice inside Pydantic AI

Use the higher-level `Agent` API for most project LLM tasks, including non-agentic single-turn calls, because it supplies structured output parsing, validation retries, dependencies, usage limits, streaming and instrumentation in one consistent boundary. Use the low-level `direct` model API only where the project intentionally wants raw request/response control and is prepared to implement the missing higher-level behavior itself; Pydantic describes `direct` as a thin model wrapper and recommends `Agent` for most application use cases. ([Direct model requests](https://pydantic.dev/docs/ai/core-concepts/direct/))

Name project components after their domain purpose (`ConversationAnalyzer`, `ReplyDraftGenerator`) rather than calling everything an “agent.” The implementation may use `Agent` without giving the component an open-ended plan/tool loop.

## Canonical documentation changes incorporated

1. [ADR-002](../adr/002-pydantic-ai-primary-orchestrator.md) now defines Pydantic AI as the **primary typed LLM execution layer**, with agent/tool orchestration as one use case.
2. [ADR-005](../adr/005-bounded-agents-deterministic-workflows.md) retains deterministic application workflows as the control plane.
3. [Typed LLM and Agent Design](../architecture/agents.md) now defines the task catalog, versioned contracts, model policy, retry/usage budgets, provenance, and evaluation boundaries.
4. [Human Approval and Security](../architecture/approval-security.md) now states explicitly that Pydantic AI deferred-tool approval cannot authorize publishing.
5. [PostgreSQL Data Model](../architecture/data-model.md) now records actual provider/model/settings, usage, retries, prompt/schema versions, hashes, and redaction policy in `ModelRun`.
6. Implementation must pin a Pydantic AI v2-compatible dependency range. Stable v2 was released on 2026-06-23; minor releases are intended to avoid breaking changes, but new message/event variants and OpenTelemetry attributes may change, and APIs under `beta` are explicitly not stable. ([Version policy](https://pydantic.dev/docs/ai/project/version-policy/))

## Final recommendation

The existing choice of Pydantic AI is sound, but “AI orchestration” undersells the useful scope and can mislead implementers into using vendor SDKs for ordinary LLM calls. Standardize all product LLM work on a small Pydantic AI-backed typed execution layer, then use tools, MCP, deferral, streaming or durable execution only when a particular task requires them.

This preserves the strongest part of the current architecture: semantic work is typed, measurable and provider-portable, while the product's state machine and authorization boundary remain ordinary application code.
