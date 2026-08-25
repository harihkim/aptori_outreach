# Outreach

**Find the conversations that matter. Understand why they matter. Engage with human control.**

Outreach is a social-intelligence and engagement system for discovering relevant public conversations, explaining why they matter, and helping a human respond thoughtfully.

The repository is **Reddit-first** and under active development. The current implementation is a walkable Campaign → Discovery vertical slice. Conversation normalization, analysis, ranking, drafting, approval, and platform preparation remain planned work.

## Daily user flow

The daily user does not define a Campaign or operate discovery jobs. Campaign context and retrieval run as workspace setup and background work; the user opens the opportunities that are ready for attention.

```text
Opportunity Inbox
        ↓
Open the best opportunity
        ↓
Read the conversation, evidence, and rationale
        ↓
Dismiss ─── Save ─── Engage
                         ↓
                  Review or edit Draft
                         ↓
                  Approve exact action
                         ↓
                  Prepare platform composer
                         ↓
                     Human Submit
```

In practice, the daily loop is:

1. **Open the Opportunity Inbox** and see what deserves attention.
2. **Understand why an opportunity was surfaced** by inspecting the source conversation and evidence.
3. **Decide quickly**: dismiss it, save it for later, or engage.
4. **Review or edit the Draft** when engaging.
5. **Approve one exact action**, then review the prepared platform composer and submit it yourself.

This is the intended product flow. The current implementation stops after the Discovery Run and Retrieval Observations; the Opportunity Inbox, Draft, Approval, and composer steps are planned.

## Current status

The current engineering path today is:

```text
Create Campaign
    ↓
Activate Campaign
    ↓
Start Discovery Run
    ↓
Inspect Discovery Run
    ↓
Inspect immutable Retrieval Observations
```

| Capability | Status |
|---|---|
| Campaign create/edit/lifecycle | Implemented |
| PostgreSQL canonical state and migrations | Implemented |
| Authenticated, idempotent Campaign and discovery writes | Implemented |
| Redis/arq discovery workers | Implemented |
| Immutable Retrieval Observations and explicit failure classification | Implemented |
| Discovery Run UI and polling | Implemented |
| Conversation normalization and deduplication | Planned |
| Typed analysis, Opportunity scoring, and Inbox | Planned |
| Triage, Draft Versions, Approval, and Approved Artifact | Planned |
| Publish Preparation and browser composer preparation | Planned |
| Automatic submission | Intentionally absent |

Discovery is started explicitly today; there is no continuous Campaign watcher yet.

## Human authorization boundary

Outreach is not an autonomous posting bot. Finding a conversation, analyzing it, or generating a Draft does not authorize an outbound action.

The canonical approval model binds one immutable Approved Artifact to:

- the exact Draft Version and content;
- ordered media assets and their checksums;
- the Actor Account;
- the action type;
- the exact Destination;
- expiry and revocation state; and
- a single-use limit.

Any bound-value change requires a new Approval. Publish Preparation accepts the server-issued approval identifier and cannot replace the content, media, account, action, or destination. The current prototype stops at `READY_FOR_HUMAN`; a human performs the final platform submission.

See [Human Approval and Security](social_intelligence_markdown/docs/architecture/approval-security.md) for the canonical contract.

## Architecture in one view

```text
Platform / retrieval adapters
            ↓
     Retrieval evidence
            ↓
       Conversations
            ↓
  Typed analysis + deterministic signals
            ↓
   Opportunity scoring and Inbox
            ↓
       Human triage
            ↓
      Draft Versions
            ↓
 Approval + Approved Artifact
            ↓
    Platform preparation adapter
            ↓
       READY_FOR_HUMAN
```

The design keeps provider objects at the boundary, preserves retrieval evidence separately from inferred state, uses workers for long-running work, and keeps lifecycle, scoring, idempotency, authorization, and persistence in application code. Models interpret bounded tasks; they do not own business state or publishing authority.

## Repository layout

| Path | Purpose |
|---|---|
| `backend/` | FastAPI application, domain services, PostgreSQL models, workers, and migrations |
| `frontend/` | SvelteKit operator UI |
| `contracts/` | Language-neutral executable contracts |
| `packages/obscura-retrieval/` | Frozen discovery and Reddit retrieval implementation |
| `retrieval-eval/prototype-smoke/` | Retrieval fixtures, provider configs, and live smoke tooling |
| `experiments/` | Retrieval and implementation experiments |
| `social_intelligence_markdown/` | Canonical product and architecture documentation |
| `.github/workflows/` | CI workflows |

## Documentation map

- [Domain context and glossary](social_intelligence_markdown/CONTEXT.md)
- [Canonical documentation index](social_intelligence_markdown/docs/README.md)
- [Product user flows](social_intelligence_markdown/docs/product/user-flows.md)
- [Domain model and state machines](social_intelligence_markdown/docs/architecture/domain-model.md)
- [Approval and security contract](social_intelligence_markdown/docs/architecture/approval-security.md)
- [REST and SSE API direction](social_intelligence_markdown/docs/api/rest-api.md)
- [Architecture Decision Records](social_intelligence_markdown/docs/adr/README.md)
- [Backend setup and API notes](backend/README.md)
- [Frontend setup and UI notes](frontend/README.md)
- [Retrieval smoke protocol](retrieval-eval/prototype-smoke/README.md)
- [Milestone 1: Walkable Vertical Slice](https://github.com/harihkim/aptori_outreach/issues/19)

## What is authoritative?

For implemented behavior, trust the code, tests, migrations, and runtime configuration. The Markdown under `social_intelligence_markdown/` is the canonical source for product/domain intent and architecture decisions. ADRs explain why major choices were made; GitHub issues describe planned implementation work.

A documented capability should not be assumed to exist until it is implemented and tested. Where an intended workflow and the current-status table differ, the current-status table and executable repository artifacts win.

## Local development

### Requirements

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- PostgreSQL
- Redis
- Node.js 20.19+ for the frontend
- pnpm 11 (the pinned version is in `frontend/package.json`)
- Node.js 20.18.0 for the retrieval package and its pinned smoke runtime

### Backend

```bash
cd backend

cp .env.example .env
# Set APTORI_API_TOKEN in .env.
# Set APTORI_DATABASE_URL too when local peer/trust auth is not available.

uv sync
createdb aptori_outreach
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. `GET /health` reports database health. Start the discovery worker in a second terminal after Redis is running:

```bash
cd backend
uv run python -m arq app.discovery.worker.WorkerSettings
```

### Frontend

```bash
cd frontend

cp .env.example .env
# Set PUBLIC_API_BASE_URL=http://127.0.0.1:8000
# Set API_TOKEN to the backend's APTORI_API_TOKEN.

pnpm install
pnpm dev
```

The frontend listens on `http://localhost:5173`.

### Retrieval package

Offline tests:

```bash
cd packages/obscura-retrieval
npm ci
npm test
```

The live smoke gate is deliberately separate from normal CI. It requires the pinned Obscura binary, reference runtime, live network behavior, and a clean worktree:

```bash
cd packages/obscura-retrieval
npm run smoke
```

See [the smoke protocol](retrieval-eval/prototype-smoke/README.md) before running it.

## Testing and CI gates

The backend CI job uses Python 3.12, PostgreSQL 16, and the frozen `uv` lockfile. From `backend/`, the local static/test sequence is:

```bash
uv python install 3.12
uv sync --frozen
uv run mypy
uv run ty check app tests
uv run pyrefly check
uv run pytest
```

Frontend checks:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm check
pnpm test
pnpm build
```

The retrieval CI job runs `npm ci` and `npm test` under Node.js 20.18.0. The live retrieval smoke gate is not part of normal CI because it depends on the reference environment and external network behavior.

## Roadmap

Milestone 1 is the walkable vertical slice. Follow-on implementation is tracked in:

- [#19 — Walkable Vertical Slice](https://github.com/harihkim/aptori_outreach/issues/19)
- [#23 — Conversations, normalization, and deduplication](https://github.com/harihkim/aptori_outreach/issues/23)
- [#24 — Typed analysis and Opportunity Inbox](https://github.com/harihkim/aptori_outreach/issues/24)
- [#27 — Draft generation and immutable versions](https://github.com/harihkim/aptori_outreach/issues/27)
- [#28 — Scoped Approval and Approved Artifact](https://github.com/harihkim/aptori_outreach/issues/28)
- [#29 — Publish Preparation](https://github.com/harihkim/aptori_outreach/issues/29)
- [#30 — Composer preparation ending at `READY_FOR_HUMAN`](https://github.com/harihkim/aptori_outreach/issues/30)

The repository name remains `aptori_outreach`; **Outreach** is the product name.
