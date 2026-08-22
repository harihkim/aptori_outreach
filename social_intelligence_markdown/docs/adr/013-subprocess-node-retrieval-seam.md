# ADR-013: Invoke the frozen Node retrieval adapters as a subprocess from Python workers

- **Status:** Accepted
- **Date:** 2026-08-22
- **Builds on:** [ADR-012](012-time-boxed-internal-retrieval-selection.md)

## Context

The ADR-012 retrieval variants (`ObscuraDuckDuckGoLiteDiscoverySource`, `ObscuraRedditThreadFetcher`) are implemented in `packages/obscura-retrieval/` as Node.js CommonJS modules pinned to Node 20.18.0 and a SHA-256-verified Obscura binary. The application core, workers, and persistence are Python (FastAPI, SQLAlchemy). The specification fixed both halves but was silent on how a Python retrieval worker executes the frozen Node adapters.

Options considered:

1. Reimplement the adapters in Python — breaks the frozen protocol identity: the smoke gate's recorded SHA-256 digests, the `verifyRuntime` reference-runtime pins, and the deterministic replay evidence all attach to the Node package. A port is a new, unevaluated provider.
2. Run a long-lived Node sidecar service — adds a second always-on service to install, supervise, authenticate, and monitor for the lifetime of the prototype.
3. Spawn the existing `bin/retrieval-cli.js` wrapper as a subprocess per retrieval job.

## Decision

Python retrieval workers invoke the frozen adapters by spawning `node bin/retrieval-cli.js` (discover / fetch) once per attempt, passing a per-run evidence output root, and reading back the `observation.json` the wrapper writes. The wrapper is exactly the "project-owned narrow wrapper with pinned binary/version/configuration and retained raw evidence" that ADR-012 already requires; the subprocess seam adds no new trusted surface.

Concretely:

- One subprocess per discovery query or thread fetch; the worker owns process timeout and maps the observation's explicit status (`SUCCESS`, `NO_RESULTS`, `BLOCKED`, `INCOMPLETE`, transport failures) into Retrieval Observation records — no silent fallback.
- Evidence directories remain owned by the Node package under a configured, git-ignored evidence root; the Python side records references, never rewrites evidence.
- The wrapper's own runtime verification (exact Node version, binary hash, Obscura version) continues to gate every run; failures surface as job failures with the wrapper's classification.
- No sidecar service and no reimplementation.

## Consequences

### Positive

- The frozen protocol, its recorded hashes, and the daily canary keep meaning: the executed code path is unchanged.
- Immutable evidence and explicit failure classification arrive for free from the wrapper.
- One fewer service to operate on the reference machine.
- The seam is trivially testable: subprocess output is JSON on disk.

### Negative / trade-offs

- Process-spawn overhead per job (tens of milliseconds) — negligible against multi-second browser retrieval.
- The Python worker host must carry the Node 20.18.0 toolchain; this is already an explicit ADR-012 reference-runtime constraint.
- The observation contract exists as JSON on disk, so the Python parser duplicates the shape; it must pin the observation schema version and reject unknown versions loudly.

## Revisit when

- Retrieval Gate R0 graduates a Python-native provider (for example the official Reddit API after approval) for the graduated route.
- Evidence volume outgrows local disk and moves to S3-compatible storage.
- Retrieval frequency makes per-job process spawn measurable.

## Related documentation

- [ADR-012](012-time-boxed-internal-retrieval-selection.md)
- [Reddit Retrieval Architecture](../architecture/retrieval.md)
- [Workers, Observability, and Testing](../architecture/workers-observability-testing.md)
