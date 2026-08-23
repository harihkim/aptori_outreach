# aptori_outreach

Workspace for a Reddit-first **Social Intelligence & Engagement Copilot**: discover relevant Reddit conversations, draft replies and media with bounded LLM tasks, and prepare outbound posts under strict human approval.

**Core invariant:** nothing is posted automatically. An approval binds the complete outbound action — exact content/media, Actor Account, action type, and Destination. The preferred prototype leaves the final Reddit submit click to a human.

## Layout

| Path | Contents |
|---|---|
| `social_intelligence_markdown/` | Canonical, version-controlled specification: product spec, architecture, 15 ADRs, API/MCP contracts, retrieval research, roadmap. This is the source of truth. |
| `contracts/` | Language-neutral executable contracts checked by both backend and frontend suites. |
| `packages/obscura-retrieval/` | ADR-012 retrieval adapters (`ObscuraDuckDuckGoLiteDiscoverySource`, `ObscuraRedditThreadFetcher`) with pinned, hash-verified runtime configuration. |
| `retrieval-eval/prototype-smoke/` | Frozen smoke-gate protocol, known-thread corpus (14 verified fixtures), provider configs, daily canary runner. |
| `experiments/` | Retrieval spikes, including the in-origin thread extractor and its recorded evidence runs. |
| `backend/` | FastAPI application core over PostgreSQL canonical state: authenticated, idempotent Campaign writes plus paginated Campaign and audit reads. |
| `frontend/` | SvelteKit 2 + Svelte 5 with shadcn-svelte: live health diagnostics and Campaign create/edit/lifecycle screens. |

## Quick start (WSL)

```bash
# Backend: FastAPI + PostgreSQL (needs local Postgres; see backend/README.md)
(cd backend && ~/.local/bin/uv sync && ~/.local/bin/uv run alembic upgrade head)
(cd backend && ~/.local/bin/uv run pytest)                 # tests
(cd backend && ~/.local/bin/uv run uvicorn app.main:app)   # GET /health

# Frontend: pnpm on Node >=20.19 (22.x recommended; see frontend/README.md)
(cd frontend && pnpm install && pnpm dev)                  # http://localhost:5173

# Retrieval adapters: offline tests run on any current Node; the frozen smoke
# gate (clean worktree required) pins Node v20.18.0 via verifyRuntime — use your
# version manager, or OBSCURA_NODE_DIR for the daily canary.
(cd packages/obscura-retrieval && npm ci && npm test)
(cd packages/obscura-retrieval && npm run smoke)

# Daily canary (install once via crontab; see retrieval-eval/prototype-smoke/README.md)
retrieval-eval/prototype-smoke/daily-smoke.sh
```

The Obscura binary defaults to the reference machine's stable path `/home/hari/.local/bin/obscura` (recorded in the frozen provider configs) and can be relocated with `OBSCURA_BIN`; its SHA-256 is always verified against the committed configs.

## Documentation entry points

- `social_intelligence_markdown/CONTEXT.md` — ubiquitous language for the domain.
- `social_intelligence_markdown/docs/adr/` — architecture decision records.
- `retrieval-eval/prototype-smoke/README.md` — evaluation protocol, corpus revision history, counter-delta semantics.

Historical note: the original v0.1 stakeholder DOCX exports are superseded by `social_intelligence_markdown/`; that directory is the active source of truth.
