# ADR-015: Stratify the provisional retrieval smoke baseline and stress fixtures

- **Status:** Accepted
- **Date:** 2026-08-23
- **Amends:** [ADR-012](012-time-boxed-internal-retrieval-selection.md)

## Context

ADR-012 fixed a ten-thread prototype gate at 8/10 successful, sufficiently complete fetches per run and an automatic-suspension threshold below 80%. Corpus revision 2 added four deliberately difficult fixtures, three of which were expected to remain incomplete, but protocol v2 replaced the original floor with 9/14. That made a 64% result pass even though the governing decision still treated repeated results below 80% as grounds for suspension.

The added fixtures carry useful conformance evidence: they test explicit access failure, honest incompleteness, counter lag, deleted-comment trees, and complete exhaustion. Treating their designed non-success as ordinary success-rate failures discards that value; adding them to the denominator weakens the original baseline.

## Decision

Protocol v3 evaluates two obligations on every run:

1. **Baseline cohort:** the original ten fixtures retain the ADR-012 floor of at least 8/10 successful, sufficiently complete fetches.
2. **Stress-fixture conformance:** each added stress fixture must produce one of its frozen acceptable explicit outcomes. A future complete fetch may replace an `INCOMPLETE` outcome only where the fixture contract permits it; parse, transport, challenge-continuation, tree-integrity, or other unlisted outcomes fail the gate.

The retained access-regression fixture remains in the baseline and permits either an explicit `BLOCKED` result or a complete `SUCCESS`. Stress-fixture outcomes never enter the baseline denominator. Zero duplicate IDs, zero missing parent references, and deterministic raw-artifact replay remain independent hard requirements.

The provisional selection is automatically suspended if three consecutive frozen v3 batches fail this combined thread gate. The access-boundary and material-runtime-drift suspension conditions in ADR-012 remain immediate and unchanged.

Protocol v2 and its reports remain historical evidence; they are not rewritten or relabeled as v3 passes.

## Consequences

### Positive

- Corpus growth cannot silently lower the original success-rate bar.
- Known hard fixtures test classification and integrity without pretending designed incompleteness is success.
- The executable protocol and ADR suspension rule use the same pass/fail semantics.

### Negative / trade-offs

- Fixture expectations are part of the frozen protocol and must be reviewed when the corpus changes.
- Results from protocol v2 and v3 are historically comparable by fixture hash and cohort, but their top-level pass booleans have different semantics.

## Related documentation

- [ADR-012](012-time-boxed-internal-retrieval-selection.md)
- [Prototype smoke protocol](../../../retrieval-eval/prototype-smoke/README.md)
- [Retrieval Gate R0](../research/retrieval-benchmark.md)
