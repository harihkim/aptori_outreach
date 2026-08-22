# aptori_outreach

Workspace for a Reddit-first **Social Intelligence & Engagement Copilot**: discover relevant Reddit conversations, draft replies and media with bounded LLM tasks, and prepare outbound posts under strict human approval.

**Core invariant:** nothing is posted automatically. An approval binds the complete outbound action — exact content/media, Actor Account, action type, and Destination. The preferred prototype leaves the final Reddit submit click to a human.

## Layout

| Path | Contents |
|---|---|
| `social_intelligence_markdown/` | Canonical, version-controlled specification: product spec, architecture, 12 ADRs, API/MCP contracts, retrieval research, roadmap. This is the source of truth. |
| `packages/obscura-retrieval/` | ADR-012 retrieval adapters (`ObscuraDuckDuckGoLiteDiscoverySource`, `ObscuraRedditThreadFetcher`) with pinned, hash-verified runtime configuration. |
| `retrieval-eval/prototype-smoke/` | Frozen smoke-gate protocol, known-thread corpus (14 verified fixtures), provider configs, daily canary runner. |
| `experiments/` | Retrieval spikes, including the in-origin thread extractor and its recorded evidence runs. |
| `backend/` | FastAPI application core over PostgreSQL canonical state with Alembic migrations (V1 done; Campaign domain lands in V3). |
| `frontend/` | SvelteKit 5 + shadcn-svelte shell showing live backend connectivity (V2 done; Campaign screens land in V3). |

## Quick start (WSL)

```bash
# Backend: FastAPI + PostgreSQL (needs local Postgres; see backend/README.md)
cd backend && ~/.local/bin/uv sync && ~/.local/bin/uv run alembic upgrade head
~/.local/bin/uv run pytest            # tests
~/.local/bin/uv run uvicorn app.main:app   # GET /health

# Frontend: pnpm on Node >=20.19 (22.x recommended; see frontend/README.md)
cd frontend && pnpm install && pnpm dev    # http://localhost:5173

# Offline adapter and normalizer tests
cd packages/obscura-retrieval
PATH=/home/hari/.local/node-v20.18.0-linux-x64/bin:$PATH npm ci && npm test

# Frozen prototype smoke gate (requires clean worktree; ~5 minutes, hits Reddit anonymously via Obscura)
npm run smoke

# Daily canary (cron)
../retrieval-eval/prototype-smoke/daily-smoke.sh
```

The Obscura binary is pinned at `/home/hari/.local/bin/obscura` (SHA-256 verified against the committed provider configs).

## Documentation entry points

- `social_intelligence_markdown/CONTEXT.md` — ubiquitous language for the domain.
- `social_intelligence_markdown/docs/adr/` — architecture decision records.
- `retrieval-eval/prototype-smoke/README.md` — evaluation protocol, corpus revision history, counter-delta semantics.

Historical note: the original v0.1 stakeholder DOCX exports are superseded by `social_intelligence_markdown/`; that directory is the active source of truth.
