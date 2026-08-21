# Workers, Observability, and Testing

> **Status:** Draft v0.4
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Long-running retrieval, model, browser, and later media work executes in workers with explicit capability boundaries, idempotent jobs, correlated telemetry, and frozen evaluation fixtures.

## Worker and job design

| Job | Characteristics | Retry and idempotency rule |
|---|---|---|
| `run_discovery` | Executes frozen provider plan and records Candidates/observations | Preserve per-query/provider progress; classify access/policy stops separately from transient failures |
| `fetch_thread` | One locator through one explicit fetcher tier | Every attempt creates a Retrieval Observation; idempotent canonical upsert by source ID |
| `normalize_observation` | Deterministic raw-evidence transformation | Same raw artifact + extractor version must produce the same hash |
| `analyze_conversation` | Versioned Pydantic AI LLM Task | Whole-job idempotency prevents duplicate Analysis; model retries are separately counted |
| `generate_draft` | Versioned Pydantic AI LLM Task | Each successful new attempt creates exactly one Draft Version |
| `prepare_publish` | Revalidate/consume Approved Artifact and prepare browser | Atomic single-use transition; no arbitrary payload or blind whole-job replay |
| `cluster_themes` | Expansion batch computation | Rebuildable from canonical Conversations/Analyses |
| `generate_media` | Expansion provider job | Idempotent by provider request key and webhook event ID |

FastAPI `BackgroundTasks` is not suitable for browser sessions, multi-provider retrieval, model pipelines, or human-waiting workflows. Start with a real Redis-backed worker queue; adopt a durable workflow engine only when demonstrated recovery/replay needs justify it.

## Capability separation

```text
retrieval worker
  has: discovery/fetch ports, evidence store
  lacks: review and publishing ports/credentials
  never exposes: unrestricted shell, write-capable social CLI, browser-cookie extractor

LLM Task worker
  has: Pydantic AI, read-only task dependencies
  lacks: approval and publishing ports/credentials

preparation worker
  has: read-only Approved Artifact resolver, preparation browser profile
  lacks: content editing, approval creation, final-submit capability
```

## Observability and evidence

- Correlation IDs span request, application command, worker job, Retrieval Observation, Model Run, browser session, and external provider request.
- Retrieval telemetry includes provider/method/version, access-identity class, egress environment, status/failure class, completeness, latency, retries, rate/reset headers, bytes/browser time/model tokens, and cost.
- Counters distinguish domain jobs/queries, provider attempts, top-level API calls or navigations, browser/network subrequests, returned/normalized/deduplicated items, and provider billable units.
- Model telemetry includes task/prompt/schema versions, requested/actual provider/model/settings, transport/output/tool retries, usage, estimated cost, and time to first/final output.
- Approval telemetry records the human decision, artifact digest, expiry/revocation/consumption, and rejected override/replay attempts.
- OpenTelemetry/Logfire may aid operations, but PostgreSQL/domain audit remains authoritative.
- Prompt/completion bodies and browser screenshots are redacted/excluded by default and retained only under explicit policy.

## Retrieval Gate R0 tests

- Frozen query/corpus/label/config hashes match `protocol.json`.
- Each provider run emits results even for terminal failures.
- Discovery and known-thread metrics are computed independently.
- Same raw observation replay produces identical normalized output.
- Access denial never triggers proxy, fingerprint, session, or identity rotation.
- Provider admission limits are coordinated across workers by provider, credential/subscription, workspace and egress identity; retry/reset handling stays within the frozen budget.
- A managed-Actor test proves exact Actor/build/input/output/proxy/spend configuration; possession of a token cannot select defaults implicitly.
- Session-backed experimental adapters expose only allowlisted read operations and fail the capability test if upstream write commands or automatic cookie extraction are reachable.
- Report includes all variants, costs, and policy stops; no winner-only report.

Detailed metrics and thresholds are in [Retrieval Gate R0](../research/retrieval-benchmark.md).

## ADR-012 prototype smoke tests

- Freeze 10 representative discovery queries, 10 varied known threads, and the exact Obscura/browser/extractor configuration before scoring.
- Discovery returns at least one canonical Reddit thread candidate for at least 8 of 10 queries; every emitted candidate is a valid canonical thread URL.
- Run the known-thread corpus twice; at least 8 of 10 threads succeed in each run.
- Successful normalized trees contain no duplicate comments and no missing parent references.
- Any unresolved Reddit `more` node forces `INCOMPLETE` rather than `COMPLETE`.
- Same retained raw evidence and extractor version produce the identical normalized hash.
- Empty results, blocks, parse failures, and transport failures remain explicit; no automatic provider hopping occurs.
- Capability tests reject accounts/sessions, CAPTCHA continuation, stealth, residential proxies, proxy rotation, and identity rotation.

Passing these tests completes the provisional internal retrieval increment only. It does not satisfy R0. Three consecutive frozen batches below 80% sufficiently complete thread-fetch success, material runtime drift, or any forbidden access requirement automatically suspends the provisional route.

## LLM Task tests

- Unit tests use Pydantic AI `TestModel`/`FunctionModel`, dependency overrides, and a default block on accidental real model requests.
- Contract tests cover typed input/output validation and domain validators.
- Frozen Pydantic Evals datasets compare prompt/model/schema variants for each task.
- Real-model quality tests are separate from deterministic integration tests.
- Streaming tests prove partial output cannot create authoritative Analysis, Draft Version, Approval, or score state.
- Retry tests prove replay does not duplicate Model Runs' domain effects.

## Approval invariant tests

- Draft Version rows reject mutation and version numbers are unique per Draft.
- Editing/regeneration always produces a new version.
- Approval rejects unresolved, mutable, checksum-mismatched, or cross-workspace content/media/account/destination references.
- Preparation rejects missing, expired, revoked, consumed, or digest-mismatched artifacts.
- One-character text changes and every media/destination/account/action substitution require re-approval.
- Unknown preparation override fields fail closed.
- Concurrent preparation attempts cannot consume the same single-use artifact.
- Research, MCP, and LLM Task workers cannot invoke preparation.
- The prototype browser adapter exposes no final-submit action.

## Failure recovery rule

Resume technical work from persisted observations, Model Runs, and job checkpoints. Never recover by weakening authorization, silently changing provider configuration, discarding failed variants, or mutating an immutable Draft Version/Approved Artifact.
