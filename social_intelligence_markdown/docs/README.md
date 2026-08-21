# Social Intelligence & Engagement Copilot

Reddit-first social intelligence and engagement platform. The system discovers public conversations, ranks meaningful opportunities, drafts useful responses and original content, generates optional media, and routes **every outbound action through explicit human approval**.

This `docs/` tree is the canonical specification. DOCX/PDF files, when produced, are exports for stakeholder circulation.

## Product shape

```mermaid
flowchart LR
    C[Campaign] --> D[Discovery]
    D --> N[Normalize & Deduplicate]
    N --> I[Intelligence / Scoring]
    I --> O[Opportunity Inbox]
    O --> G[Draft / DraftVersion]
    G --> H[Human Review]
    H --> A[Approval + ApprovedArtifact]
    A --> P[Browser preparation]
    G -. expansion .-> M[Higgsfield Media]
    M -.-> H

    UI[SvelteKit UI] --> API[Headless Core]
    MCP[MCP clients] --> API
    API --> D
    API --> I
    API --> G
    API --> H
```

## Non-negotiable invariant

> No outbound preparation or engagement may execute without an explicit human Approval and immutable Approved Artifact binding exact content/media, Actor Account, action type, and Destination. Changes, expiry, revocation, or consumption remove eligibility.

## Documentation map

### Product
- [Product specification](product/product-spec.md)
- [User flows and UX](product/user-flows.md)
- [Opportunity scoring](product/opportunity-scoring.md)
- [Demo specification](product/demo-spec.md)

### Architecture
- [System design](architecture/system-design.md)
- [Domain model and state machines](architecture/domain-model.md)
- [Reddit retrieval](architecture/retrieval.md)
- [Typed LLM / agent design](architecture/agents.md)
- [Approval and security](architecture/approval-security.md)
- [Data model](architecture/data-model.md)
- [API and MCP architecture](architecture/api-and-mcp.md)
- [Higgsfield media integration](architecture/media.md)
- [Workers, observability and testing](architecture/workers-observability-testing.md)

### API interfaces
- [REST/SSE API](api/rest-api.md)
- [MCP tools and resources](api/mcp-tools.md)

### Delivery
- [Roadmap](roadmap/roadmap.md)
- [Production readiness](roadmap/production-readiness.md)

### Research
- [Open-source projects](research/open-source-projects.md)
- [Reddit access, Gemini and CUA notes](research/reddit-access-and-gemini.md)
- [Retrieval Gate R0](research/retrieval-benchmark.md)
- [Pydantic AI capabilities](research/pydantic-ai-capabilities.md)
- [Crawlee, PRAW and Async PRAW](research/crawlee-praw-asyncpraw.md)
- [Agent Reach and session-backed Reddit retrieval](research/agent-reach.md)
- [Third-party scraping architecture claims](research/third-party-scraping-claims.md)
- [Research source catalog](research/source-catalog.md)

### Architecture Decision Records
- [ADR index](adr/README.md)

## Recommended implementation stack

| Layer | Baseline |
|---|---|
| Backend | FastAPI + Pydantic + Pydantic AI |
| Persistence | PostgreSQL + SQLAlchemy 2 + Alembic |
| Jobs/cache | Redis + a lightweight Python worker queue initially |
| Frontend | Svelte 5 + SvelteKit + TypeScript |
| UI | shadcn-svelte + Bits UI |
| Frontend data | TanStack Query; Table/Virtual where useful |
| Retrieval | ADR-012 provisional Obscura + DuckDuckGo Lite discovery and Obscura thread fetching for the Internal Product; versioned alternatives and provider graduation through R0 |
| Official Reddit | Async PRAW after approved access |
| Browser/computer use | CUA as a bounded last fallback and preparation adapter |
| Media expansion | Higgsfield API |
| Agent interface | MCP over the same domain services as REST/SSE |

## Documentation conventions

1. Architecture-changing decisions require an ADR.
2. Specs describe desired behavior; ADRs explain **why** a major choice was made.
3. Public-platform capabilities and policy assumptions must be dated/revalidated before production decisions.
4. Example schemas are illustrative until an OpenAPI/JSON Schema artifact is committed.
5. Business logic lives in the headless core; UI, MCP, workers and providers are adapters around it.
6. Canonical domain language is defined in the package [CONTEXT](../CONTEXT.md); use `Draft Version`, `Approval`, and `Approved Artifact` precisely.
