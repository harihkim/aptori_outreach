# ADR-006: Use CUA/browser automation for Reddit MVP retrieval

- **Status:** Superseded by [ADR-009](009-retrieval-viability-gate-and-escalation.md)
- **Date:** 2026-08-20

## Historical decision

The original package selected Google Search/URL Context with CUA browser extraction as the assumed MVP retrieval ladder because official Reddit access was a separate workstream.

## Why superseded

Retrieval is too load-bearing to select before a frozen quantitative comparison. Crawlee supplies deterministic HTTP and Playwright variants worth measuring, while CUA is slower and less repeatable. The current decision makes retrieval a hard R0 gate and treats CUA as a last fallback rather than an assumed default.

## Related documentation

- [ADR-009](009-retrieval-viability-gate-and-escalation.md)
- [Reddit Retrieval Architecture](../architecture/retrieval.md)
