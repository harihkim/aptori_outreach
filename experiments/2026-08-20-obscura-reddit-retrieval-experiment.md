# Obscura In-Origin Reddit Retrieval Spike

> **Date:** 2026-08-20  
> **Status:** Working, repeatable single-thread spike; not an R0 provider qualification  
> **Runtime:** WSL2 Ubuntu, Node.js 20.18.0, Playwright Core 1.62.1, Obscura 0.2.0  
> **Access mode tested here:** Anonymous standard Obscura CDP; no Reddit account and no `--stealth`

## Result

The in-origin structured JSON route worked twice in fresh WSL runs against the known AskRobotics thread. Obscura navigated to the public thread, and Playwright then fetched the thread JSON from the same page context.

Both fresh runs produced:

- HTTP 200 for the page navigation and structured JSON response;
- the complete root post body and metadata;
- 22 unique `t1` comments with clean bodies, authors, scores, UTC timestamps, depths and parent IDs;
- maximum observed depth 2;
- zero duplicate IDs and zero missing parent references;
- zero unresolved `more` nodes or child IDs; and
- the same stable comment-content hash when volatile scores are excluded.

Reddit reported `num_comments = 23`, while both raw JSON responses contained 22 `t1` objects. The experiment therefore claims **22/22 retrievable comments from the returned source tree**, not that the unexplained counter difference is definitely a deleted placeholder.

## Fresh WSL runs

| Run | Mode | Elapsed | JSON bytes | Comments | Max depth | Unresolved `more` | Obscura-tree peak RSS | Node peak RSS |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [`117f54cd`](runs/obscura_2026-08-20T10-58-18-354Z_117f54cd/result.json) | Standard anonymous | 21.09 s | 73,409 | 22 | 2 | 0 | 233.73 MB | 124.40 MB |
| [`4038cbd8`](runs/obscura_2026-08-20T11-14-35-533Z_4038cbd8/result.json) | Standard anonymous | 7.71 s | 73,409 | 22 | 2 | 0 | 196.66 MB | 118.90 MB |

The raw response hashes differ because one comment score changed from 22 to 23 between runs. IDs, authors, bodies, timestamps, parent relationships and depths remained identical.

Memory is sampled every 250 ms. `obscuraTreePeakRssMB` sums the Obscura process and its descendants; `nodePeakRssMB` measures the Playwright runner. These results replace the earlier unsupported 42 MB estimate. They are not yet a matched comparison against Chromium.

## Evidence layout

Each run has an immutable directory:

```text
experiments/runs/<run-id>/
├── raw-thread-response.txt
├── result.json
└── stderr.log
```

`result.json` records the response hash, status, bytes, runtime versions, Obscura binary hash, WSL/kernel details, redacted URLs, memory samples and normalization validation. Captured stderr is sanitized before it is written so transient challenge query values are not retained.

## Extractor behavior

[`obscura_deep_comment_extractor.js`](obscura_deep_comment_extractor.js) now:

1. creates a unique run directory before starting network work;
2. waits for CDP readiness instead of sleeping for a fixed startup duration;
3. allowlists Reddit hosts and builds a canonical `.json` endpoint;
4. saves and hashes the raw response before normalization;
5. fails on non-2xx, non-JSON or malformed responses;
6. preserves visible, deleted and removed `t1` records;
7. records unresolved `more` nodes instead of silently declaring completeness;
8. validates ID uniqueness and parent references;
9. samples the Obscura process tree and Node runner memory; and
10. redacts transient challenge parameters from URLs and captured stderr.

Offline contract coverage is in [`obscura_deep_comment_extractor.test.js`](obscura_deep_comment_extractor.test.js).

## Reproduce in WSL

The Obscura binary now lives at the stable path `/home/hari/.local/bin/obscura` (SHA-256 `dbd8fd5147c1aeff30165c9d7884e777bcd630493bd83e20148fa57c71e91d94`, identical to the originally recorded scratch copy). Dependencies resolve from the retrieval package instead of IDE scratch space:

```bash
cd /home/hari/myroot/intern_aptr/aptori_outreach

OBSCURA_BIN=/home/hari/.local/bin/obscura \
OBSCURA_PORT=9234 \
OBSCURA_STEALTH=0 \
NODE_PATH=$PWD/packages/obscura-retrieval/node_modules \
/home/hari/.local/node-v20.18.0-linux-x64/bin/node \
experiments/obscura_deep_comment_extractor.js
```

Run the offline checks with:

```bash
/home/hari/.local/node-v20.18.0-linux-x64/bin/node --test \
experiments/obscura_deep_comment_extractor.test.js
```

## Follow-up verification (2026-08-21)

Seven additional threads were extracted with this runner to curate smoke-corpus revision 2. Two findings changed the tooling:

1. **Sequential-run port race (fixed).** The runner SIGTERMed Obscura without awaiting exit, so the next run could hit `bind: address already in use` and fail before CDP ready. The teardown now waits for exit and escalates to SIGKILL, matching `ObscuraRuntime.stop()`.
2. **Comment counter is unreliable in both directions.** Archived threads returned trees with *more* comments than `num_comments` reports (e.g. SHA-1 collision thread: 332 extracted vs 321 reported). Normalization now records `reportedCommentDelta` and a `counterDeltaClass` (`match`, `within_unresolved_more`, `exceeds_visible_tree`, `negative_counter_lag`, `unknown`) so completeness claims rest on `sourceTreeExhausted`, never on the counter.

Verified shapes included locked (USAID breach), high-volume beyond limit (TrueCrypt EOL, 905-comment positive delta), exhausted-tree-with-deleted-comments, and deep nesting up to depth 9. These fixtures and observations are frozen in `retrieval-eval/prototype-smoke/known-threads-2026-08.json` (revision 2).

## What this proves—and what comes next

This proves that anonymous standard Obscura plus an in-origin structured fetch is a viable known-thread extraction candidate for this thread. It does not yet prove discovery quality, large-thread completeness, reliability across Reddit page types, policy approval or production stability.

The next fast-but-not-fragile step is a small pre-R0 corpus of 5–10 threads covering deep replies, a high-comment thread with `more` nodes, deleted/removed comments, locked threads, media/link/self posts and an expected failure. Run each at least three times before deciding whether this route deserves the full R0 corpus or a long-term provider adapter.
