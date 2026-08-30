# aptori_outreach — agent notes

## Tooling

In pnpm-managed JavaScript (the `frontend/` workspace), run everything through
pnpm — `pnpm <script>`, `pnpm dlx <bin>` — so installs and versions match the
pinned `packageManager`. `packages/obscura-retrieval/` is the exception: its
ADR-012 reference runtime pins Node 20.18.0, below pnpm 11's floor, so it keeps
its npm toolchain (`npm ci`, `npm test`). Use npm/npx nowhere else: they bypass
the pnpm lockfile.

## Agent skills

### Issue tracker

GitHub Issues at `github.com/harihkim/aptori_outreach`, operated via the `gh` CLI.
See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo; the canonical glossary (`CONTEXT.md`) and ADRs live under
`social_intelligence_markdown/`, not the repo root. See `docs/agents/domain.md`.
