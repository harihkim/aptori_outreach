# Workers, Observability and Testing

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Long-running browser, model and media work executes in workers, with correlated telemetry and evaluation fixtures.

## Worker and job design

| **Job**              | **Characteristics**                                | **Retry notes**                                                     |
|----------------------|----------------------------------------------------|---------------------------------------------------------------------|
| discovery_run        | Search and browser retrieval; potentially minutes. | Retry provider/transient failures; preserve per-candidate progress. |
| fetch_thread         | Browser/URL retrieval for one conversation.        | Idempotent by source URL/external ID.                               |
| analyze_conversation | Typed model call.                                  | Retry model/network failures; version outputs.                      |
| cluster_themes       | Batch compute over recent relevant conversations.  | Can rebuild from source data.                                       |
| generate_draft       | Model generation.                                  | New model run creates new draft version.                            |
| generate_media       | Long-running provider job.                         | Use provider request ID and webhook idempotency.                    |
| prepare_publish      | Browser navigation/fill.                           | Must revalidate approval and content hash at execution time.        |

FastAPI BackgroundTasks is not the right place for browser sessions, media generation, or multi-step workflows. Use a real worker queue. Start lightweight; move to a durable workflow engine only if workflow complexity, long waits, or human-in-the-loop recovery makes it necessary.

## Observability and auditability

- Correlation IDs across HTTP request, worker job, browser session, model call, and provider request.

- Structured logs for provider, model, latency, token/cost estimate, retries, and failure reason.

- Metrics: candidates/run, fetch success rate, analysis latency, precision labels, draft acceptance, approval latency, CUA step count, media job latency.

- Trace model prompt template version and structured output schema version.

- Store only the minimum browser screenshots/logs necessary for debugging, with configurable retention.

- Audit events for every approval, rejection, publish preparation, and publish attempt.

## Testing and evaluation strategy

### Retrieval benchmark

| **Method**                       | **Measure**                                                     |
|----------------------------------|-----------------------------------------------------------------|
| Gemini Google Search grounding   | Unique Reddit URLs, relevant URLs, freshness, latency, cost.    |
| Search + Gemini URL Context      | Successful full/thread extraction rate and comment coverage.    |
| CUA direct Reddit browser search | Coverage, extraction quality, steps, latency, failure modes.    |
| CUA fetch known URL              | Deterministic thread extraction success and field completeness. |

### Model evaluation

- Maintain a labeled conversation set with relevance, intent, recommended action, and promotion-fit labels.

- Evaluate precision@K, action agreement, calibration, and rationale quality.

- Create adversarial examples: sarcasm, competitor fan posts, generic mentions, old threads, sensitive topics, prohibited-claim traps.

- Evaluate drafts separately from scoring: helpfulness, factuality, naturalness, promotion appropriateness, and community fit.

### Approval invariant tests

- Publish/prepare endpoint rejects missing, expired, rejected, or mismatched approvals.

- Approved text edited by one character becomes ineligible until re-approved.

- Research worker cannot import/invoke publish implementation.

- MCP clients cannot manufacture an approval by submitting client-side history or arbitrary content.
