# Production Readiness and Risk Register

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

R0 authorizes only the measured prototype route. Production use requires separate evidence for access, scale, retention, model behavior, authorization, and recovery.

## Main risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Reddit access/policy changes | Retrieval route becomes prohibited or unavailable | Dated access review, capability-specific adapters, explicit policy stops, official-access workstream |
| Search coverage gaps | Opportunity recall suffers | Frozen repeated benchmarks, provider overlap/incremental-yield measurement, query-family floors |
| HTML/browser brittleness | Incomplete or changing observations | Deterministic raw snapshots, extractor versioning, fixed HTTP-before-browser tiers, regression corpus |
| Crawlee evasion features misused | Policy/compliance harm | Disable proxy/fingerprint/session rotation for Reddit; stop on access controls; configuration tests |
| Official API rate/coverage limits | Missing threads/comments or worker contention | Credential-scoped admission control, explicit `MoreComments` budgets, rate telemetry |
| Deleted Reddit content retained | Data-governance breach | Source refresh, tombstones, deletion processing, approved retention schedule |
| LLM false positives | Noisy inbox | Deterministic filters/score, typed outputs, frozen Pydantic Evals datasets, calibration/feedback |
| Unsupported or promotional drafts | Brand/community harm | Claim/risk task, source references, conservative posture, human review |
| Opaque retry/cost multiplication | Budget and duplicate-state failures | Layered retry ownership, idempotency keys, request/token/cost limits, persisted attempt counts |
| Prompt injection | Source text tries to expand tools/permissions | Treat source as untrusted, narrow read tools, capability separation, no publish access for LLM Tasks |
| Partial model output treated as final | Invalid state or unsafe review | UI-only preview; persist only final validated output |
| Incomplete approval scope | Wrong account/destination/action/media used | Immutable Approved Artifact digest over complete scope |
| Approval replay/race | Duplicate preparation | Atomic single-use consumption and concurrency tests |
| Browser credential leakage | External account compromise | Isolated secret storage/profile, redacted logs/telemetry, least privilege |
| MCP privilege creep | External agent bypasses review | Same domain services, read-only prototype tools, no approval/preparation tools |

## Production gates

### Access and data governance

- Intended Reddit use case and commercial posture are documented and approved.
- OAuth application, truthful User-Agent, scopes, rate limits, and account policy are reviewed.
- Retention, source deletion/tombstone, data-subject request, evidence, screenshot, prompt, and completion policies are implemented and tested.
- Non-API web retrieval has its own policy review; technical success is not permission.

### Retrieval

- The selected production configuration passes a new dated evaluation under realistic load and expected geography/network conditions.
- Monitoring detects coverage, page-shape, rate, completeness, cost, and latency regressions.
- Runbooks distinguish technical outage, provider change, access denial, and policy stop.
- No production configuration silently introduces unbenchmarked adaptive routing or evasion behavior.

### LLM Tasks

- Each production task has a versioned schema, prompt, model/fallback policy, retry/usage budget, and frozen evaluation suite.
- Model/provider upgrades run against the suite before rollout.
- Aggregate budget/admission controls exist beyond per-run Pydantic AI limits.
- Telemetry redaction/retention is reviewed; traces do not replace canonical Model Runs.

### Authorization and preparation

- Draft Version immutability and Approved Artifact digest constraints are database-backed.
- Expiration, revocation, atomic consumption, cross-workspace isolation, and every scope mismatch have automated tests.
- Research/LLM/MCP workers cannot obtain publishing credentials or import preparation capabilities.
- Browser automation is limited to the authorized artifact and production-approved action semantics.
- Incident runbooks cover compromised Actor Accounts, bad approvals, replay attempts, and browser/provider failures.

### Operations

- Correlated dashboards and alerts cover provider failures, model regressions, approval anomalies, preparation attempts, and cost.
- Jobs have bounded retries, dead-letter/manual recovery, idempotency, and reconciliation.
- Backups and restoration include authorization/audit evidence without reviving expired/revoked credentials or work.

See [Retrieval Gate R0](../research/retrieval-benchmark.md), [Human Approval and Security](../architecture/approval-security.md), and [Workers, Observability, and Testing](../architecture/workers-observability-testing.md).
