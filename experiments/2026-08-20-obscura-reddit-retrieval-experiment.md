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

```bash
cd /home/hari/myroot/intern_aptr/aptori_outreach

NODE_PATH=/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/node_modules \
OBSCURA_BIN=/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/obscura \
OBSCURA_PORT=9234 \
OBSCURA_STEALTH=0 \
/home/hari/.local/node-v20.18.0-linux-x64/bin/node \
experiments/obscura_deep_comment_extractor.js
```

Run the offline checks with:

```bash
NODE_PATH=/home/hari/.gemini/antigravity-ide/brain/97af282d-c646-4491-92a4-5745dadb63c0/scratch/node_modules \
/home/hari/.local/node-v20.18.0-linux-x64/bin/node --test \
experiments/obscura_deep_comment_extractor.test.js
```

## What this proves—and what comes next

This proves that anonymous standard Obscura plus an in-origin structured fetch is a viable known-thread extraction candidate for this thread. It does not yet prove discovery quality, large-thread completeness, reliability across Reddit page types, policy approval or production stability.

The next fast-but-not-fragile step is a small pre-R0 corpus of 5–10 threads covering deep replies, a high-comment thread with `more` nodes, deleted/removed comments, locked threads, media/link/self posts and an expected failure. Run each at least three times before deciding whether this route deserves the full R0 corpus or a long-term provider adapter.
