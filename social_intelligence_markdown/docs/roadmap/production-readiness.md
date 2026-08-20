# Production Readiness and Risk Register

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The demo path is intentionally not the final production posture. These controls and evidence are required before relying on the system operationally.

## Main risks and mitigations

| **Risk**                            | **Impact**                                  | **Mitigation**                                                                                                   |
|-------------------------------------|---------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Reddit anti-scraping/access changes | Retrieval path breaks.                      | Provider abstraction; conservative browser use; official-access workstream; cached demo corpus only as fallback. |
| CUA/browser brittleness             | Higher latency/failure rate.                | Use browser only when simpler retrieval is insufficient; narrow tasks; health checks; retry/backoff; benchmark.  |
| Search misses fresh/niche threads   | Opportunity recall suffers.                 | Mix site-scoped queries, subreddit discovery, direct browser search; compare overlap.                            |
| AI false positives                  | Inbox becomes noisy.                        | Cheap filter + structured scoring + labeled eval set + human feedback.                                           |
| Over-promotional drafts             | Brand/community harm.                       | Separate promotion_fit, conservative defaults, campaign rules, human review.                                     |
| Prompt injection in page content    | Agent may follow hostile page instructions. | Treat source content as untrusted; fixed browser contract; no write tools; safety scanning/confirmation.         |
| Accidental auto-post                | Severe product/safety failure.              | Server-side state machine, exact-content hashes, separate workers, final-click human mode.                       |
| Media provenance/retention          | Lost assets or unclear generation history.  | Persist job metadata and copy completed assets to owned storage.                                                 |
| MCP privilege creep                 | External agents bypass UI assumptions.      | MCP calls same domain services; no arbitrary publish tool; authenticate server and enforce authorization.        |

## Definition of production-readiness beyond the demo

- Documented Reddit access/commercial-use posture reviewed for the intended deployment.

- Retrieval provider meets target reliability and cost under realistic load.

- Operator-labeled opportunity evaluation demonstrates consistent precision, not only curated demo success.

- Prompt-injection and approval-invariant security tests are automated.

- Secrets, cookies, browser profiles, and generated media are stored with clear retention and access controls.

- Observability dashboards and alerting exist for browser failure rate, provider changes, model regressions, and outbound-action attempts.

- Runbooks exist for Reddit UI changes, provider outage, compromised browser session, bad model output, and accidental approval.
