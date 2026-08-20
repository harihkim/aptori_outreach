# Documentation Contribution Guide

## Source of truth

Markdown under this directory is canonical. Generated DOCX/PDF exports should not be edited as the primary copy.

Canonical domain language is defined in `../CONTEXT.md`. Update it when a domain term is resolved; keep implementation and lifecycle detail in architecture documents.

## Version-control workflow

- Keep documentation changes reviewable and atomic: research evidence, canonical contract changes, and generated exports are separate commits.
- Record expensive-to-reverse decisions in an ADR and update every affected canonical document in the same change set.
- Do not rewrite historical ADR intent silently; mark an ADR superseded and link its replacement when the decision changes materially.
- Run Markdown link, whitespace, terminology, and cross-reference checks before committing.
- Commit benchmark protocols before results so queries, labels, thresholds, and provider configurations cannot move after outcomes are known.

## When to update what

- **Product behavior or scope:** update `product/`.
- **Technical implementation contract:** update `architecture/` and/or `api/`.
- **Sequence or milestone:** update `roadmap/`.
- **External evidence/benchmark:** update `research/`.
- **Major architectural choice:** add or supersede an ADR in `adr/`.

## ADR rule

Create an ADR when a decision is expensive to reverse, crosses multiple modules, changes a security/trust boundary, selects a major framework/provider, or intentionally rejects an obvious alternative.

## Time-sensitive external facts

Reddit policies/access, Gemini capabilities, MCP specification details, Higgsfield API behavior and other external platform facts can change. Date benchmark/research updates and link to primary sources. Do not treat an old research note as a permanent platform guarantee.

## Diagrams

Prefer Mermaid for diagrams that should evolve with the code. Keep diagrams conceptual rather than encoding every class.

## API schemas

Once implementation begins, generated OpenAPI/JSON Schema should supersede hand-written field-level details. Keep Markdown focused on semantics, invariants and examples.
