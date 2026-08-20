# ADR-011: Isolate session-backed retrieval experiments

- **Status:** Accepted
- **Date:** 2026-08-20

## Context

Agent Reach demonstrates useful ordered-backend and diagnostic patterns, but it is an installer/router rather than a typed retrieval SDK. Its Reddit paths delegate to OpenCLI or `rdt-cli`, reuse logged-in browser/session credentials, and install upstream tools that also contain write operations. Direct adoption would couple research retrieval to human-account sessions, mutable external commands, and capabilities that violate the read-only worker boundary.

## Decision

Do not adopt Agent Reach as a production runtime dependency or provider boundary. If Gate R0 evaluates a session-backed mechanism, implement an audited, pinned, project-owned read-only adapter in an isolated process with allowlisted operations, immutable evidence, typed failures, fixed request/cost budgets, no automatic browser-cookie extraction, and no reachable write commands. Treat OpenCLI logged-in-browser JSON as an experimental provider variant; treat `rdt-cli` cookie HTTP as a quarantined higher-policy-risk diagnostic. Neither may satisfy R0's policy threshold without explicit access and commercial-use approval.

## Consequences

- The project forgoes Agent Reach's rapid system-wide installer and direct CLI flexibility.
- Useful browser-origin structured responses can still be measured without exposing general shell or social-write capability.
- Session leakage, expiry and revocation remain explicit experimental risks rather than hidden production dependencies.
- A successful technical benchmark does not authorize production use or weaken the preference for approved official Reddit access.

## Related documentation

- [Reddit Retrieval Architecture](../architecture/retrieval.md)
- [Retrieval Gate R0](../research/retrieval-benchmark.md)
- [Agent Reach assessment](../research/agent-reach.md)
