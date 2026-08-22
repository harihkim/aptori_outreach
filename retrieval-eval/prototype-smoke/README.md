# ADR-012 prototype smoke

This directory freezes the smaller Internal Product retrieval gate authorized by ADR-012. It is not Retrieval Gate R0 and cannot graduate a provider or authorize external use.

The protocol commit precedes scored results. The runner refuses a dirty worktree, records the clean Git commit SHA and hashes every frozen input/config file. Generated raw evidence and reports live under ignored `results/` directories so result publication can be a separate reviewed decision.

From the package directory on the WSL reference runtime. The offline tests run on any current Node; the smoke gate requires the pinned Node v20.18.0 enforced by `verifyRuntime` (use your version manager, or point `OBSCURA_NODE_DIR` at a directory containing it):

```bash
cd packages/obscura-retrieval
npm ci
npm test
npm run smoke
```

The runner executes discovery once and the known-thread corpus twice. Every attempt has its own immutable directory containing `observation.json` and, when received, the raw page or structured response.

## Corpus revision 2 (2026-08-21)

The known-thread corpus grew from ten to fourteen fixtures. The four additions are verified stress shapes, each observed through the authorized Obscura extractor path on 2026-08-21 (see each thread's `verification` block):

- `t11` TrueCrypt EOL: high-volume beyond the fetch limit, deep nesting, 153 deleted comments; intentionally incomplete.
- `t12` USAID breach: locked thread, deleted-comment-heavy, near-complete boundary.
- `t13` SHA-1 collision: archived thread where Reddit reports *fewer* comments than the tree contains (`negative_counter_lag`).
- `t14` Bill Gates Twitter hack: fully exhausted tree that still contains 76 deleted comments and the same negative-counter behavior.

Protocol v2 (`evaluationId …-v2`) records these as `expectedNonSuccessThreadIds`; v1 reports stay comparable through their recorded fixture hashes.

## Comment counter delta

Reddit's `num_comments` is not a reliable ground truth in either direction. Every normalized observation now records `reportedCommentDelta` (`num_comments − extracted count`) and a `counterDeltaClass`:

- `match` — counter equals extracted count.
- `within_unresolved_more` — positive delta fully accounted for by unresolved `more` child IDs.
- `exceeds_visible_tree` — positive delta larger than pending `more` children; some counted comments are absent from the returned tree.
- `negative_counter_lag` — the tree contains more comments than the counter reports.
- `unknown` — counter missing from the response.

Completeness claims must rest on `sourceTreeExhausted`, never on the counter.

## Daily canary

`daily-smoke.sh` runs the frozen gate against clean HEAD and appends one TSV line per attempt to `results/daily/log.tsv`, classifying failures against `expectedNonSuccessThreadIds` so only novel regressions surface as `unexpectedFailures`. It never posts results anywhere; forwarding or alerting is an operator decision.

`daily-smoke.sh` derives the repository root from its own location, so it can be installed from any clone. It honors two environment overrides, both defaulting to the reference WSL machine: `OBSCURA_NODE_DIR` (directory holding the pinned Node v20.18.0 toolchain) and `OBSCURA_BIN` (path to the pinned Obscura binary; the default comes from the frozen provider configs and its SHA-256 is always verified).

Install (WSL Ubuntu; cron must be running, e.g. `sudo service cron start`; adjust the path to your clone):

```text
crontab -e
30 5 * * * /path/to/aptori_outreach/retrieval-eval/prototype-smoke/daily-smoke.sh >> /path/to/aptori_outreach/retrieval-eval/prototype-smoke/results/daily/cron.log 2>&1
```

Exit codes: 0 passed, 2 gate failed, 3 skipped (dirty worktree), 1 crashed before writing a report.
