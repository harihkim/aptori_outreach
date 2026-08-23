# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`social_intelligence_markdown/CONTEXT.md`** — the ubiquitous-language glossary for the Reddit-first discovery, drafting, review, and preparation workflow.
- **`social_intelligence_markdown/docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context, spec-first repo: domain language and architecture decisions live beside the canonical specification under `social_intelligence_markdown/`, not at the repo root.

```
/
├── AGENTS.md
├── docs/agents/                          ← agent configuration (this file)
├── packages/
│   └── obscura-retrieval/                ← code consumes the spec's vocabulary
└── social_intelligence_markdown/
    ├── CONTEXT.md                        ← glossary (single context)
    └── docs/
        ├── adr/                          ← ADR-001 … ADR-015
        └── …                             ← product, architecture, research, roadmap
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids (e.g. say *Candidate*, not "lead"; *Draft Version*, not "draft revision state").

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-007 (human final submit in demo mode) — but worth reopening because…_
