# REST and SSE API

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Initial application-facing contract. Exact request/response JSON schemas should become generated OpenAPI from FastAPI/Pydantic models.

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

## Conventions

- Resource mutations return canonical server state, not optimistic client-only state.
- Long-running operations return a job/run identifier and progress is available through SSE.
- All write endpoints are idempotency-key aware where retries could duplicate work.
- Approval endpoints require authenticated human identity.
- `prepare_publish` accepts an `approval_id`; it never accepts arbitrary outbound text.
- Browser/model/provider errors use stable machine-readable error codes plus human-readable detail.

## Suggested SSE event families

```text
discovery.started
discovery.candidate_found
discovery.completed
conversation.fetch_started
conversation.fetch_completed
analysis.completed
draft.generated
media.started
media.completed
browser.started
browser.ready_for_human
publish.completed
job.failed
```
