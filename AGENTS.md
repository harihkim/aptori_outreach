# aptori_outreach — agent notes

## Tooling

Run all JavaScript tooling through pnpm — `pnpm <script>`, `pnpm dlx <bin>` —
so installs and versions match the pinned `packageManager`. Use npm/npx
nowhere: they bypass the pnpm lockfile.

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
