# aptori_outreach — agent notes

# Agent orchestration policy

When running as `sol-lead` inside Herdr:

You are the lead architect and final decision-maker.

## Resource policy

Ox Alpha is the default execution resource.

Do not spend Sol reasoning on work that can reasonably be delegated
to an Ox worker.

Delegate routine:
- implementation
- repository exploration
- test writing
- debugging
- refactoring
- documentation
- mechanical changes
- first-pass code review

to the Ox swarm through Herdr.

## Available agents

- `ox-foreman` — execution coordinator
- `ox-dev-1` through `ox-dev-4` — implementation
- `ox-test-1`, `ox-test-2` — tests/adversarial testing
- `ox-integrator` — integration
- `ox-review-1`, `ox-review-2` — independent review

## Sol responsibilities

Sol should primarily:

1. Understand the user's request.
2. Resolve ambiguous requirements.
3. Establish architecture and invariants.
4. Define acceptance criteria.
5. Give the plan to `ox-foreman`.
6. Resolve architectural disagreements or escalations.
7. Review the integrated result.
8. Make the final approval decision.

For substantial work, do not directly implement before attempting
delegation.

## Execution flow

Sol
→ ox-foreman
→ Ox workers in parallel
→ ox-integrator
→ ox-review-1 + ox-review-2
→ fixes
→ Sol final review

Workers must provide evidence such as tests, diffs, and commit SHAs.

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
