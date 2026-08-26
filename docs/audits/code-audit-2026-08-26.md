# Codebase Audit — 2026-08-26

Full-source audit of first-party code. Documentation was deliberately excluded; every
finding below cites code read line-by-line.

## Scope and method

| Area | Files | Notes |
|---|---|---|
| `backend/app` (FastAPI, SQLAlchemy 2, arq) | 40 | core, campaigns, auditing, idempotency, workspaces, discovery |
| `backend/alembic` | 10 | env + migrations 0001–0009 |
| `backend/tests` | 12 | full suite |
| `frontend/src` (SvelteKit, Svelte 5) | 33 | lib, server, routes, ui components, configs |
| `packages/obscura-retrieval` (Node 20.18, CommonJS) | 18 | src, bin, test |
| `experiments`, `retrieval-eval/tools` | 4 | spike code and report tooling |

Total: ~15,240 lines of first-party source. Method: five parallel deep-read passes
covering every file completely, followed by first-hand verification of every
high-severity claim against the actual files.

**Provenance tags:** `[VERIFIED]` = confirmed by direct re-read of the cited lines.
All other findings carry exact citations from the deep-read pass; snippets are verbatim.

---

## 1. Bugs

### High severity

#### A1 · Timeout recovery can attribute another query's evidence (cross-query contamination) `[VERIFIED]`

`backend/app/discovery/cli.py:105-113` prefers a recovery candidate whose parent
directory is literally named for the query id:

```python
preferred_parent = f"attempt-{query_id}"
def recovery_sort_key(path: Path) -> tuple[bool, int, str]:
    return (
        path.parent.name != preferred_parent,
```

The frozen CLI never creates such a directory. It writes
`<outputRoot>/<capability>/<logicalId>_<timestamp>_<rand>/observation.json`
(`packages/obscura-retrieval/src/evidence.js:11-17`):

```js
const parent = path.resolve(outputRoot, safeName(capability));
const directory = path.join(parent, `${safeName(logicalId)}_${attemptId}`);
```

The preference branch can therefore never match, and recovery falls through to
"newest `observation.json` anywhere under the run's **shared** output root"
(`cli.py:96-121`). All queries of one run share that root, so a query that times out
right after a sibling finished adopts the sibling's document under its own
`query_id` — wrong observation content, wrong attribution.

Tests mask the bug because both fake CLIs create exactly `$OUT/attempt-$ID`
(`backend/tests/test_cli_adapter.py:34`, `backend/tests/test_worker_runner.py:86`).

*Fix direction:* prefer directories matching `{safeName(query_id)}_…` (the real
layout) or filter candidates by logicalId prefix; add a regression test that uses the
real `evidence.js` directory shape.

#### A2 · One unreachable poll permanently kills run-page polling and erases the run `[VERIFIED]`

The production chain turns a transient backend outage into a dead end on the run page:

1. Network failure returns `status: 0` (`frontend/src/lib/server/api.ts:54-55`):
   ```ts
   } catch {
       return { ok: false, status: 0, body: null };
   }
   ```
2. The load converts 0 → null (`runs/[runId]/+page.server.ts:19-22`):
   ```ts
   const runState = parseDiscoveryRunResponse({
       httpStatus: runResult.status || null,
   ```
3. null ⇒ run discarded (`frontend/src/lib/discovery.ts:177-178`):
   ```ts
   if (httpStatus === null) {
       return { apiReachable: false, run: null, detail: 'Backend did not answer' };
   ```
4. `isLive` derives from the now-missing run (`runs/[runId]/+page.svelte:20-26`),
   so `unreachableWhileLive === false` — the amber "Backend unreachable - retrying..."
   banner (`data-testid="unreachable-retrying"`, `+page.svelte:103-110`) is
   unreachable during real outages. The whole `{#if run}` block unmounts, replaced by
   the red alert.
5. Worst of all, the polling attachment's gate reads `isLive`
   (`+page.svelte:72-78`), so `startDiscoveryRunPolling` runs with
   `initial.live === false` and returns a no-op stopper (`polling.ts:38-41`) —
   polling halts until manual refresh/navigation.

Why tests miss it: `page.test.ts:111-126` fabricates
`{ apiReachable: false, run: <non-null> }` — a state the real server load can never
produce.

*Fix direction:* preserve last-known run across unreachable polls (server or client
side), or derive liveness from something sticky rather than the transient payload;
add a test asserting the amber banner renders when the API call fails outright.

#### A3 · Timed-out subprocess survives task cancellation (orphaned process tree)

`cli.py:162-175` kills the process group only in the `asyncio.TimeoutError` branch;
there is no `finally`:

```python
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
```

arq enforces `job_timeout = retrieval_attempt_timeout_seconds + 60` by cancelling the
job task (`worker.py:105-107`); the resulting `CancelledError` propagates through
`communicate()` without any kill. The child was spawned with `start_new_session=True`
(`cli.py:157`), so the Node process plus its browser-driver children survive
indefinitely, holding pipes/CPU; settle never runs and the orphan keeps running while
the reaper later fails the run.

*Fix direction:* wrap the wait in `try / except BaseException` → killpg → re-raise,
or use an inner timeout owned by this function instead of relying solely on arq.

#### A4 · Retrieval package violates its own ADR-012 invariant: some failures leave no evidence `[VERIFIED]`

`packages/obscura-retrieval/src/thread-fetcher.js:24-32`: input validation and config
dereferences execute **before** the `try` block (line 34):

```js
const canonical = canonicalizeRedditThreadUrl(input.url);
const structuredEndpoint = redditJsonUrl(canonical.url, this.config.thread);
...
const attempt = createAttempt(this.outputRoot, 'thread-fetch', input.id || canonical.postId);

try {
```

`canonicalizeRedditThreadUrl` throws for malformed/non-Reddit URLs (`reddit.js:20,25`)
and missing config sections raise `TypeError` — both escape before `createAttempt`,
so no attempt directory and no `observation.json` is written. Same shape in
`discovery.js:31`. Consequences:

- Violates ADR-012's invariant ("a discovery or fetch attempt persists its own
  outcome"; failure classifications are explicit outcomes).
- `bin/retrieval-cli.js:66-68` exits 1 with a bare message instead of classified
  exit 2 with evidence.
- `bin/run-prototype-smoke.js` propagates it: whole smoke dies via `main().catch`
  with no `report.json` even though earlier observations were already written.

Compounding factor: `validateConfigShape` (`config.js:20-39`) checks only
`schemaVersion`/`providerVariant`/`accessMode`/`obscura.*`/`runtime.*` — not the
`discovery.{minimumGapMs,maxCandidates}` and `thread.{commentLimit,sort,minimumGapMs}`
sections the adapters dereference. Shipped provider configs contain them; hand-authored
configs crash mid-flight.

*Fix direction:* move validation inside the adapters' try after `createAttempt`; extend
`validateConfigShape` to require the capability sections.

### Medium severity

#### A5 · Missing database index declared by the model `[VERIFIED]`

`backend/app/discovery/models.py:145` declares
`workspace_id … ForeignKey("workspaces.id"), index=True` on `retrieval_observations`,
demanding `ix_retrieval_observations_workspace_id` under the repo naming convention.
Migration `0006_discovery_runs.py` creates only three indexes: two on `discovery_runs`
(lines 81-92) and `ix_retrieval_observations_run_creation_order` (line 175). The
workspace-scoped observation index is never created — workspace queries seq-scan.
Undetectable by tooling because `alembic/env.py:19` sets `target_metadata=None`.

*Fix direction:* migration 0010 creating the index; then wire `target_metadata`
(after fixing M2 below) so drift becomes catchable.

#### A6 · Non-ASCII bearer token ⇒ HTTP 500 instead of 401 `[VERIFIED]`

`backend/app/deps.py:44`:

```python
    if credentials is None or not hmac.compare_digest(credentials.credentials, token):
```

`hmac.compare_digest(str, str)` requires ASCII-only strings; Starlette decodes header
values as latin-1, so `Authorization: Bearer té` raises `TypeError`, surfacing as a
500 (log noise from garbage tokens) instead of a clean 401.

*Fix direction:* compare bytes: `hmac.compare_digest(credentials.credentials.encode(), token.encode())`.

#### A7 · Late observations mutate already-terminal runs

`runner.py:604-619` inserts recovered observations without checking `run.status`,
while `_roll_up_run` refuses terminal recount (`runner.py:429-430`):

```python
    if run.status in TERMINAL_RUN_STATUSES:
        return
```

If the reaper failed the run mid-spawn, the late observation still lands on the
terminal row while `metrics.counts` stays frozen at reap time — metrics diverge from
the observations list, contradicting the replay-invariant comment at
`runner.py:61-63`.

*Fix direction:* guard the settle insert with the terminal-status check (classify as
`already_done`-style outcome instead).

#### A8 · Enqueue failure after commit leaves immortal `queued` orphans

`discovery/service.py:217-229` commits the 201 run row first, then enqueue failure
returns 503. The stale-run reaper scans only `status == "running"`
(`worker.py:67-68`), so orphaned `queued` rows with zero jobs live forever unless the
client retries with the same idempotency key (the documented healing path).

*Fix direction:* extend the reaper to stale `queued` rows older than a threshold, or
document the retry-heals contract loudly in the API response.

#### A9 · Spawn-time errors crash the retrieval package uncaught `[VERIFIED]`

`packages/obscura-retrieval/src/runtime.js:65-72` attaches `stderr.on('data')` and
`process.on('exit')` but no `'error'` handler on the spawned process:

```js
this.process = spawn(this.runtimeIdentity.binaryPath, this.args, {
    stdio: ['ignore', 'ignore', 'pipe'],
});
```

An async `'error'` event (e.g. EAGAIN at spawn time — the synchronous
`fs.accessSync(X_OK)` check only pre-clears ENOENT/EACCES) becomes an
uncaughtException bypassing both CLIs' catch blocks: no evidence write, no smoke
report. Same pattern in `experiments/obscura_deep_comment_extractor.js:261-265`.
`connectOverCdp`'s exit-code poll cannot see spawn-time errors since `'exit'` never fires.

*Fix direction:* attach `process.on('error', …)` routed through the same failure
channel as exit codes.

### Low severity

| # | Finding | Location | Note |
|---|---|---|---|
| L1 | Unbounded JSON parse + unbounded JSONB payloads contradict the model's own docstring "Every string field carries an explicit bound so a hostile or broken provider cannot balloon a database row" — only scalar strings are bounded; `input`/`response`/`network`/`runtime`/`raw_artifact`/`candidates` persist at any size | `cli.py:54`; `observations.py:65-74`; docstring `observations.py:46-51` | memory + row-size hazard |
| L2 | Correctness-critical vocabulary guards use `assert` — stripped under `python -O`; DB CHECK still catches but as opaque IntegrityError instead of loud classifier bug | `runner.py:273-277, 444` | |
| L3 | Stale experiments copy crashes on missing `created_utc`: `new Date(postObj.created_utc * 1000).toISOString()` → `RangeError: Invalid time value`; canonical package has truthiness guards (`reddit.js:87-92`) | `experiments/obscura_deep_comment_extractor.js:167, 189` | divergence, see D-section |
| L4 | DuckDuckGo-Lite parser relies entirely on table markup; partial markup change makes the sibling-walk silently attach wrong snippet/url to results while status stays `success` | `discovery.js:44-53` | wrong-evidence class; frozen corpus mitigates today |
| L5 | Failure classification keys on English regexes over error messages (`/JSON\|parse\|root post\|two-listing array/i` etc.) — depends on V8 phrasing; custom error classes silently reclassify | `status.js:34-38` | fragile typing seam |
| L6 | Oversized hostile `query_id` (>200 chars) crashes the violation-row INSERT itself (`String(200)` column) → evidence-less claim rollback, same stall shape as spawn errors | `runner.py:530-533`; `models.py:147` | kwargs are runner-untrusted by design |
| L7 | Cursor length enforced twice with different codes: FastAPI `Query(max_length=200)` yields 422 pre-handler while all other bad cursors yield documented 400 `page_cursor_invalid` | `campaigns/router.py:81, 140` vs `pagination.py:16-17` | inconsistent client error shapes; same pattern in discovery router |
| L8 | Poll backoff doc says "consecutive failed polls double the delay", but `attempts` increments on every tick regardless of outcome — healthy long runs decay 3s→6s→12s→15s anyway; `gate.reachable` is dead input; behavior codified by `page.test.ts:267-298` (intended-but-misdocumented) | `polling.ts:4-8, 57-65` | fix docs or consult `reachable` |
| L9 | `execFileSync(binaryPath, ['--version'])` has no timeout — hung binary wedges startup forever | `config.js:49` | hash-pinned binary lowers likelihood |
| L10 | Smoke-gate pairs observations to fixture ids by array index only (`threads[itemIndex].id`); count checked, order not — permuted collection scores wrong fixtures; also `Number.isInteger` accepts 0/negative baseline floor making criterion vacuous (protocol uses 8); unguarded `observation.normalized.validation` deref crashes whole run instead of failing gate | `smoke-gate.js:68-70, 16, 73-76` | latent |
| L11 | Client-side `crypto.randomUUID()` exists only in secure contexts — plain-http LAN deployment throws at form submit | `campaigns/+page.svelte:74` | deployment-dependent |
| L12 | Substring marker matching ("Node version", "Obscura version") over stderr tail can misclassify an unrelated wrapper crash as `runtime_verification_failed` | `runner.py:66, 378` | taxonomy purity |

Also noted (minor): unguarded top-level `JSON.parse` in `summarize-report.js:35`;
fixed-port CDP attach can hit a stale Obscura instance in experiments
(`obscura_deep_comment_extractor.js:32,273`); network-bytes accounting listener is a
floating promise racing snapshot (`runtime.js:100-104`); bind-then-release port TOCTOU
(`runtime.js:16-19`); `stop()` SIGKILL not awaited (package copy regressed vs
experiments copy which races a second wait, `runtime.js:136` vs
`obscura_deep_comment_extractor.js:368-370`).

---

## 2. Dead code

### Backend

| Item | Location | Evidence |
|---|---|---|
| `CampaignNotFound` (discovery's own) — defined, never raised/caught (missing campaign returns `_error_result(404, …)` directly) | `discovery/service.py:46-47` | repo-wide grep: only `campaigns.service.CampaignNotFound` referenced elsewhere |
| `CampaignNotActiveError` — same | `discovery/service.py:50-55` | non-active handled inline at `service.py:168-173` |
| Columns always written `None`, never read, absent from wire schema: `external_source_id`, `normalized_content_sha256` | written at `runner.py:193,197`; omitted from `schemas.py:65-87` | write-only storage |
| Columns persisted but unread/unexposed: `source_url`, `final_url`, `runtime`, `raw_artifact` | populated `runner.py:224-234`; only `row.network` consumed (`runner.py:394-402`) | reserved-for-future surface — decide keep-or-drop |
| Run status `'cancelled'` — member of every vocabulary layer, no producer short of raw SQL in one test | `models.py:26`, `schemas.py:9`, `runner.py:63`, migration `0006:77`, `contracts/discovery-run-statuses.json:3`; only writer `tests/test_worker_runner.py:755` | parity-tested in three layers — confirm intent before removing |
| `Workspace.settings` JSONB column — zero readers/writers | `workspaces/models.py:20` | |
| Probe diagnostic half discarded by only caller | built `db.py:69`, discarded `main.py:60` (`healthy, _diagnostic = manager.probe()`) | log-only channel per `db.py:52-54` |
| Unreachable defensive 403 — sole principal always contains default workspace | `deps.py:65-72` vs construction `deps.py:52` | scaffolding; label it |

Note (not removable): `DiscoveryRunCreate` payload immediately `del`-ed
(`router.py:66,72`) is an intentional extra="forbid" gate preserving 422-on-body
behavior.

### Frontend

Verified by grep over `frontend/src`:

- `CardAction` component exported (`card/index.ts`), never mounted; its styling hook
  `has-data-[slot=card-action]:grid-cols-[1fr_auto]` in `card-header.svelte:17`
  never exercised
- Re-exports unused outside their modules: `badgeVariants`, `ButtonProps`,
  `ButtonSize`, `ButtonVariant`, `buttonVariants`, duplicate alias
  `type ButtonProps as Props` (`button/index.ts:10`)
- `WithoutChild` / `WithoutChildren` / `WithoutChildrenOrChild` (`utils.ts:8-10`) —
  referenced nowhere; these are the file's only `any`s
- `CostStatus` type (`discovery-format.ts:11`, re-exported `discovery.ts:28`) — no consumer
- `USABLE_STATUSES` (`discovery-contract.ts:24`) — test-only; app logic re-hardcodes
  the same triple inside `observationTone` (`discovery-tones.ts:24-30`)
- Contract guard functions publicly re-exported via `export *`
  (`isRunStatus`/`isObservationStatus`/`isFailureClass`/`isTimestampOrNull`/
  `isStringList`/`isRecord`) — consumers internal-only
- Spinner compat props `name`, `color`, `stroke` (`spinner.svelte:11-13`) — never passed
- Unused variants/sizes: Badge `default`/`ghost`/`link` + anchor mode; Button `ghost`/
  `link`/`destructive`, sizes `xs`/`lg`/`icon-xs`/`icon-sm`/`icon`/`icon-lg`; Card
  `size="sm"`
- Navigation gap: run page `/campaigns/[campaignId]/runs/[runId]` has no inbound link
  anywhere; sole entry is the post-action redirect (`campaigns/+page.server.ts:195`) —
  a user who loses the tab cannot navigate back from the UI

### Package & experiments

Dead exports (function alive internally, export imported nowhere after repo-wide grep):

- `unwrapDuckDuckGoUrl` (`src/reddit.js:204`) — unsafe standalone anyway (no host
  validation; safe only behind its sole internal caller)
- `findAvailablePort` (`src/runtime.js:142`)
- `canonicalize` (`src/json.js:26`)
- `extractCompleteRedditThread` (`experiments/obscura_deep_comment_extractor.js:382`) —
  only its own `require.main` block calls it

Options/flags:

- Unknown CLI flags accepted silently (`bin/retrieval-cli.js:16-21`) — `--outpt-root`
  typo falls through to confusing "Missing --output-root"; junk keys retained unread
- Whole-document fallback ignores `--id` (`bin/retrieval-cli.js:33-36`)
- `thread-fetcher.js:29` forwards entire `thread` section into `redditJsonUrl`,
  unknown keys ignored — obscures the actual contract

Experiments fork: `experiments/obscura_deep_comment_extractor.js` is the pre-package
spike and has diverged (lacks `Array.isArray` payload guard, `Number.isFinite` score
guards, `created_utc` guards → bug L3; contains the ADR-012-excluded stealth knob).
Canonical for every overlapping concern is `packages/obscura-retrieval/src/*`. Its
test file near-duplicates `test/reddit.test.js:153-176`. Keep as historical evidence
or prune exports to what its own test needs.

Tests:

- Unused import `select` (`tests/test_discovery_runs.py:20`)

---

## 3. Test-suite gaps and migration issues

### Suite gaps

1. **Hardcoded DB URLs ignore the override env var** `[VERIFIED]` —
   `test_discovery_runs.py:29-30` and `test_worker_runner.py:38-39` hardcode
   `postgresql+psycopg://@/<name>` plus bare `connect("postgresql://")` for CREATE
   DATABASE, while conftest honors `APTORI_TEST_DATABASE_URL` (default socket auth).
   CI sets a TCP URL with credentials; these two modules work only if the runner
   happens to permit local socket auth. Two coexisting DB-resolution policies.
2. **Order dependence** — `test_migrations.py:234-259` leaves undeletable rows behind
   by design; `test_write_auth.py`'s cleanup (`DELETE FROM campaigns`) survives only
   because the final migrations test downgrades past `discovery_runs` first. Any new
   module sorting between them breaks with FK violations.
3. **Latent ordering flake** — audit assertions order by
   `occurred_at, id` where `id` is a random UUID tie-breaker; four back-to-back
   PATCHes can share microsecond timestamps. `event_order` identity exists precisely
   for this (`test_campaigns.py:139-143`; correct pattern used in
   `test_worker_runner.py:266-281`).
4. **No negative-auth coverage for discovery routes** — `test_write_auth.py` proves
   the fail-closed matrix exhaustively for campaigns; none of the three discovery
   endpoints is ever exercised with missing/wrong/unconfigured bearer
   (`test_discovery_runs.py:73-76` bakes in a good header).
5. **Campaign CHECK vocabulary lacks DB-side parity test** — discovery constraints
   are pinned four ways (`test_discovery_contract.py:123-151`);
   `ck_campaigns_status_values`/`posture_values` are compared only at Python level.
6. Uncovered behaviors: parallel duplicate-idempotency-key race, concurrent run-start,
   redelivery racing terminal transition beyond sequential replays, `updated_at`
   advancement semantics, pagination bounds (`limit=0`, huge limits).

### Migration issues

1. **Missing index** — see A5.
2. **Constraint-name style trap** — `discovery/models.py:79-83,122-129` pass fully
   prefixed names (`name="ck_discovery_runs_status_values"`) into a convention that
   prepends `ck_%(table_name)s_%(constraint_name)s`; rendering DDL from metadata
   would double-prefix (`ck_ck_discovery_runs_...`). Nil impact today
   (`target_metadata=None`), a trap when autogenerate gets wired. Campaign models use
   the intended short style (`campaigns/models.py:35-38`).
3. **0004 data migration destroys original partial state** — upgrade overwrites both
   columns for any partially-written legacy row; downgrade restores only rows whose
   body carries the reconciliation marker. Original values unrecoverable.
4. **Vocabulary-narrowing upgrades can brick mid-chain** — recreating CHECKs in 0008
   validates against existing rows; a legal-under-0007 `evidence_unreadable` row
   would wedge deployment with no documented purge step (0006's downgrade, by
   contrast, documents its escape hatch at `0006_discovery_runs.py:207-220`).
5. Hygiene: f-string SQL interpolation of a module constant in `0002:133-135`
   (inconsistent with bound-parameter style in 0004); `gen_random_uuid()` needs PG ≥ 13
   (undocumented floor; CI uses PG16); duplicated string literals across 0007/0008
   downgrade/upgrade paths (drift-guarded at head only).

---

## 4. Improvements

### Performance / resource lifecycle

1. New engine pool built and disposed **per arq job** (`runner.py:638-658`); worker
   startup/shutdown hooks are deliberate noops (`worker.py:31-38`). Hold a manager on
   ctx/module scope.
2. New Redis pool per start-run POST (`queue.py:49,70-71`); no connect timeout — hung
   Redis hangs the request thread inside `asyncio.run`.
3. Input scratch files accumulate forever: `scratch/discovery-inputs/<run_id>/input-*.json`
   never deleted (`runner.py:567-570`, root `config.py:43`).
4. Reaper predicate `(status == 'running' AND started_at < cutoff)` has no supporting
   index (only campaign composite exists, `models.py:78-84`); full scan every 300 s.
5. `idempotency_events` grows monotonically — full JSONB response bodies stored, no
   TTL sweep, `created_at` never queried.
6. `list_campaign_audit` hydrates a full Campaign entity for an existence check
   (`campaigns/service.py:146`) — EXISTS subquery would drop a round trip.
7. Reaper takes many run locks without deterministic order (`worker.py:64-74`) —
   deadlock hygiene debt if cron uniqueness ever degrades across replicas.

### Observability / robustness

8. Zero logging in the entire discovery slice — failures observable only through DB
   rows; `QueueEnqueueError` embeds raw exception reprs (potential DSN fragments if
   redis_url ever carries credentials, `queue.py:64`).
9. Health endpoint drops the probe correlation id operators could use to match logged
   warnings (`main.py:60` vs `db.py:63-68`).
10. Internal spawn errors raise past the classifier (`create_subprocess_exec` outside
    try, `cli.py:140-144`) contradicting the adapter contract "Raises nothing for
    provider failures" (`cli.py:137-139`) — misconfiguration surfaces as evidence-less
    stalled runs.
11. Queue adapter counts arq-deduplicated jobs as enqueued (arq returns None for
    existing job id; lands in success branch, `queue.py:63-66`).
12. Layered stderr caps confuse: 4000-char tail pre-redaction (`cli.py:32`) → 500-char
    persistence cap (`observations.py:113`) → classification slices again
    (`runner.py:389`); the 4000 figure matters only for marker matching — document.
13. Timeout coupled in three places, one captured at import time
    (`config.py:44`; `worker.py:107` snapshots at class definition; `worker.py:51-54`
    recomputes per cron tick) — changing env after import leaves `job_timeout` stale.
14. `total_elapsed_ms` zero-fills unmeasured attempts (`runner.py:450`:
    `sum(row.elapsed_ms or 0 …)`) conflicting with the module's own "never zero"
    philosophy (`models.py:62-66`).

### Consistency / API design

15. Field-update audits record field names only (`after={"fields": sorted(updates)}`,
    `service.py:257`) — pre-edit state unrecoverable, unlike transitions which store
    before/after (`service.py:271-272`).
16. Hardcoded `/campaigns` paths inside idempotency fingerprints (`service.py:69,227`)
    duplicate router truth; remounting changes fingerprints and invalidates stored
    replays as conflicts.
17. Silent whitespace-stripping merges distinct client idempotency keys
    (`(idempotency_key or "").strip()`, `router.py:222`).
18. Failed PATCH 404s commit as permanent idempotent replays (documented contract,
    footgun for clients retrying across creation ordering; no purge path).
19. Tag-list length cap applied before blank-item cleanup — 101 raw items 422 even if
    cleaned list is tiny (`schemas.py:37`).
20. Redundant transition guard repeated (`service.py:245` vs `260`).
21. Odd default DSN with empty host component (`config.py:14`).
22. Duplicate canonical tuples maintained in parallel:
    `RETRIEVAL_OBSERVATION_STATUSES` ≡ `STATUS_VALUES` (`models.py:32-45` vs
    `observations.py:20-33`), drift-guarded only by tests — one should reference the other.

### Frontend

23. Response-parse envelope triplicated (`health.ts:23-60`, `campaigns.ts:98-165`,
    `discovery.ts:170-243`): same null-status branch, same `Unexpected response (HTTP n)`
    template — extract a shared helper.
24. `explainCampaignError` / `explainDiscoveryError` share nine identical case arms
    plus the 422 fallback — compose a base mapper.
25. Base URL captured once at module scope (`api.ts:4`) vs re-read per request with a
    second literal fallback (`routes/+page.server.ts:7`) — can diverge.
26. Health load bypasses `callApi` (raw fetch, ad-hoc timeout, no unified handling,
    `routes/+page.server.ts:12-18`).
27. Type-safety holes: unchecked casts laundering `unknown` for error-code extraction
    (`campaigns.ts:222`, `discovery-errors.ts:3`); redundant cast after existing guard
    (`campaigns/+page.svelte:180`); `latencyLabel` renders negative/non-finite numbers
    literally (`discovery-format.ts:41-44`); `usageLabel(run)` evaluated twice per render
    (`run/+page.svelte:143-144`).
28. Implicit `status || null` sentinel conversion hides the 0-means-unreachable
    boundary that caused A2 — a named `toHttpStatusCode()` would have surfaced it.
29. Accessibility minors: card titles render `<div>` not headings
    (`card-title.svelte:13-18`); two simultaneous `role="alert"` regions possible on
    run page; disabled-anchor button emits odd `role="link"`+`tabindex={-1}` combo
    (currently unexercised); Spinner live region nested inside Refresh button.
30. Cross-package test import couples frontend tests to monorepo layout
    (`campaigns.test.ts:3`, `discovery.test.ts:3` import `../../../contracts/*.json`).

### Package

31. Success vs failure observations omit different keys (`finalUrl`, `response`,
    `network`, `normalizedSha256`, `candidateCount`, `rawArtifact` absent on failure
    paths) — emitting explicit nulls would make downstream consumers shape-agnostic.
32. `sleep()` defined identically four times; relative `--output-root` resolves
    against process CWD (cron surprise); multi-subreddit inputs silently widen DDG
    scope to generic `site:reddit.com comments` with no observation marker.
33. `ObscuraRuntime` itself untested (connect deadline loop, SIGTERM→SIGKILL
    escalation, stderr cap) — injectable with fake ChildProcess emitters on pinned Node.

### Test utilities duplication

34. Triplicated `API_TOKEN = "test-token"`; verbatim-duplicated `write_headers()`;
    divergent cleanup fixtures; quintuplicated alembic-config boilerplate;
    triplicated CREATE-DATABASE blocks; triplicated observation-document builders;
    duplicated redaction sample literal — consolidate into `tests/support.py`.

---

## 5. Confirmed clean (checked, no action needed)

These areas were examined and found correct — listed so nobody re-audits blindly:

- Pagination off-by-one logic: `limit + 1` fetch, strict `<` cursor, unique identity
  columns; cursor namespaces prevent cross-endpoint reuse (`campaigns/service.py:123-165`,
  `pagination.py:29`)
- Workspace authz scoping: every campaign/discovery query filters workspace_id; 404
  anti-enumeration for foreign resources; audit listing re-validates existence
- Timezones: aware `datetime.now(UTC)`, `DateTime(timezone=True)` columns, naive ISO
  rejected at parser boundary
- Transition TOCTOU: FOR UPDATE row locks held through validation+mutation; lock order
  consistently run→observations; replay guard backed by unique constraint
- Subprocess argument injection: exec-array without shell; `query_id` charset-validated
  before filename use
- Token comparison constant-time; unset token fails closed with 503
- Reddit URL allowlisting/injection surfaces: strict host allowlist defeats userinfo/
  suffix/backslash spoofs; endpoint rebuilt with `searchParams.set` only
- Exit-code contracts coherent across CLI/smoke/daily scripts
- XSS: zero `{@html}` occurrences; framework-escaped interpolation throughout
- N+1 queries: none found (list endpoints use single indexed queries)
- Wire-contract parity: frontend `discovery-contract.ts` matches `discovery.ts`
  parsing exactly (11 run fields, 18 observation fields, vocabulary enforcement),
  consistent with frozen `contracts/discovery-run-statuses.json`

---

## 6. Remediation plan

Ordered by value; each item sized for delegation to an implementation worker with
test evidence required.

| Priority | Items | Rationale |
|---|---|---|
| **P0 — correctness** | A1 (+regression test using real `evidence.js` layout), A2 (+honest unreachable-state test), A3 | Wrong evidence attribution, user-facing polling death, leaked processes |
| **P0 — data integrity** | A5 (migration 0010 + wire `target_metadata` after fixing name-style trap), A7, A8 | Index/perf debt becomes correctness risk; metrics-vs-evidence divergence; immortal rows |
| **P1 — package contract** | A4 + `validateConfigShape` extension, A9 | Restores ADR-012's own invariant; crash-proofing |
| **P1 — API hygiene** | A6, L7 (single cursor-validation path), L1/L2/L6 bounds | Cheap, removes 500-noise and contract ambiguity |
| **P2 — tests** | Fix hardcoded DB-URL modules (G1), `ORDER BY event_order` (G3), self-cleaning migrations test (G2), discovery auth-negatives matrix (G4), campaign CHECK parity (G5) | Flake removal + coverage of the auth boundary |
| **P2 — dead code sweep** | Backend exceptions/columns (decide keep-vs-drop for reserved fields), frontend dead exports/variants, banner experiments fork as historical, remove unused imports | Shrinks review surface |
| **P3 — improvements** | Pooled engines/Redis, scratch-file GC, minimal discovery logging, dedupe frontend parsers/error mappers, remaining consistency items | Quality-of-life, perf |

## 7. Suggested issue breakdown

One issue per P0/P1 item above with the finding text as acceptance context; P2 groups
naturally into one "test suite hardening" issue and one "dead code sweep" issue; P3
into "resource lifecycle" and "frontend dedup". Each should reference this file for
full citations.
