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
| `backend/`, `frontend/` | Reserved for the planned FastAPI/Pydantic AI and Svelte implementations (not started). |

## Quick start (WSL)

```bash
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
