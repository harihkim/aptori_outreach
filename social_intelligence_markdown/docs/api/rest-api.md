# REST and SSE API

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

This is the semantic application-facing contract. FastAPI/Pydantic models will become the generated OpenAPI authority once implementation begins.

## API surface

| Area | Representative endpoints |
|---|---|
| Campaigns | `GET /campaigns`; `POST /campaigns`; `GET/PATCH /campaigns/{id}`; `POST /campaigns/{id}/discovery-runs` |
| Opportunities | `GET /opportunities`; `GET /opportunities/{id}`; `POST /opportunities/{id}/dismiss`; `POST /opportunities/{id}/save` |
| Analysis | `POST /conversations/{id}/analyses`; later `POST /campaigns/{id}/theme-clusters` |
| Drafts | `POST /opportunities/{opportunity_id}/drafts`; `GET /drafts/{id}`; `POST /drafts/{id}/versions`; `POST /drafts/{id}/regenerate` |
| Review | `GET /reviews/pending`; `POST /approvals`; `POST /approvals/{id}/revoke`; `POST /draft-versions/{id}/rejections` |
| Media | Later: `POST /media/jobs`; `GET /media/jobs/{id}`; `POST /webhooks/higgsfield` |
| Publishing | `POST /publish-preparations`; `GET /publish-preparations/{id}` |
| Events | `GET /events/stream` for retrieval, analysis, drafting, review, browser, and media progress |

## Draft contract

`POST /opportunities/{opportunity_id}/drafts` creates a Draft and its first immutable Draft Version. `POST /drafts/{draft_id}/versions` records a human edit as another version. `POST /drafts/{draft_id}/regenerate` runs the configured LLM Task and creates another version.

No endpoint updates Draft Version content in place. In particular, there is no `PATCH /drafts/{id}` mutation for text.

Example human edit:

```http
POST /drafts/draft_123/versions
Idempotency-Key: edit-456
```

```json
{
  "base_version_id": "dv_3",
  "text": "Revised response text"
}
```

The response contains a newly allocated `DraftVersion`; a stale `base_version_id` returns a conflict unless the client explicitly rebases.

## Approval contract

Approval targets one immutable Draft Version and the complete outbound action scope:

```http
POST /approvals
Idempotency-Key: approval-request-789
```

```json
{
  "draft_version_id": "dv_123",
  "action": "reddit_comment",
  "actor_account_id": "acct_456",
  "destination": {
    "platform": "reddit",
    "subreddit": "cybersecurity",
    "thread_id": "abc123",
    "parent_comment_id": null
  },
  "media_asset_ids": [],
  "expires_at": "2026-08-20T18:30:00Z"
}
```

The server authenticates the human, resolves the Draft Version text and finalized media checksums, validates workspace ownership and destination semantics, and creates both:

- an immutable `Approval` decision; and
- an immutable `ApprovedArtifact` authorization snapshot and digest.

The server does not accept client-supplied content hashes as proof that content was reviewed. It computes all digests from canonical state.

## Publish Preparation contract

```http
POST /publish-preparations
Idempotency-Key: preparation-012
```

```json
{
  "approval_id": "approval_789"
}
```

This request schema is intentionally closed. It accepts no text, destination, Actor Account, action, media, or prompt override. Unknown fields fail validation. The service revalidates and atomically consumes the Approved Artifact before enqueueing browser work.

The prototype has no automatic-submit endpoint. A successful preparation ends at `READY_FOR_HUMAN`.

## Status and error semantics

| Condition | Result |
|---|---|
| Stale Draft edit base | `409 draft_version_conflict` |
| Missing or cross-workspace reference | `404` or policy-safe `403` |
| Expired approval | `409 approval_expired` |
| Revoked approval | `409 approval_revoked` |
| Already consumed approval | `409 approval_consumed` |
| Artifact digest mismatch | `409 approved_artifact_mismatch` and security event |
| Override field supplied to preparation | `422 request_contract_violation` |
| Access block/rate limit during retrieval | Stable provider result; never silently escalated as evasion |

## Conventions

- Resource mutations return canonical server state.
- Long-running operations return a run/job identifier; progress is available through SSE.
- All retryable writes require an idempotency key and preserve the original result.
- Approval requires authenticated human identity; MCP or model history cannot manufacture it.
- API/MCP adapters authenticate, validate, translate, and call application services; they do not implement domain rules.
- Provider/model failures use stable machine-readable classes plus human-readable detail.

## SSE event families

```text
discovery.started
discovery.candidate_found
discovery.completed
retrieval.observed
conversation.normalized
analysis.completed
draft.version_created
approval.created
approval.revoked
approval.expired
approval.consumed
media.started
media.completed
browser.started
browser.ready_for_human
job.failed
```

See [Domain Model and State Machines](../architecture/domain-model.md) and [Human Approval and Security](../architecture/approval-security.md).
