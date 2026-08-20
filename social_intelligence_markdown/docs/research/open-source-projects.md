# Open-Source Projects to Study or Reuse

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Projects identified during research, with a deliberate distinction between architecture inspiration, reusable components and production dependencies.

## Open-source projects to study or reuse

| **Project**                | **Use for us**                                                                               | **Recommendation**                                                                                   |
|----------------------------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| trycua/cua                 | Computer-use drivers, sandboxing, agent framework, MCP/automation infrastructure.            | Benchmark as the final semantic/browser fallback and use for approved composer preparation.           |
| Crawlee for Python         | Async HTTP/Parsel/Playwright retrieval, queues, throttling, retries, sessions and evidence storage. | Benchmark fixed HTTP and Playwright known-URL tiers in R0; do not use evasion features or canonical storage. |
| RedoraAI                   | End-to-end Reddit lead workflow: discovery, scoring, AI comments/DMs, scheduling, dashboard. | Study product/data flow deeply; do not copy autonomous-engagement patterns.                          |
| OpenMagpie                 | Clean source/watch/action architecture, semantic filtering, auditability, webhooks.          | Strong architecture reference; possible reusable components depending on fit.                        |
| PRAW / Async PRAW          | Mature synchronous and asynchronous wrappers for approved Reddit API access.                 | Use Async PRAW for the future official provider; PRAW is unnecessary in the async production runtime. |
| Pydantic AI                | Typed model execution, validation, tools, limits, streaming, evals and telemetry.             | Default execution layer for all bounded product LLM Tasks, not only open-ended agents.                |
| RedditRadar                | Dashboard, AI analysis, lead states, campaign/settings concepts.                             | Study UI/data-model ideas; its unauthenticated JSON approach is not a long-term provider assumption. |
| Harken                     | Multi-source social listening, normalization, sentiment/themes.                              | Study for future connector model and topic analytics.                                                |
| Agent-Reach                | Multi-backend routing for many platforms, health checks, connector abstraction.              | Study connector/router philosophy for bonus platforms.                                               |
| Obscura                    | Rust headless browser and scraping/agent automation infrastructure.                          | Useful generic web/browser reference; not required in Reddit-first critical path if CUA works.       |
| Postiz                     | Open-source multi-network scheduling/publishing and agent CLI.                               | Future publishing/integration study; review AGPL/license implications before embedding.              |
| reddit-mcp-server projects | Typed read-only Reddit tools without full product UI.                                        | Study MCP tool shapes; do not make this architecture the system of record.                           |

## Build-versus-reuse recommendation

| **Capability**                       | **Approach**                                                                                                                 |
|--------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| Core data model / opportunity engine | Build. This is the differentiated product and must be designed around our scoring, audit, approval, and multi-source future. |
| Reddit known-URL retrieval           | Benchmark URL Context, Crawlee HTTP/Playwright and bounded CUA independently; adopt only R0-winning tiers.                    |
| Official Reddit provider             | Implement with Async PRAW once Reddit access and the intended use are approved.                                               |
| Typed LLM execution                  | Standardize on a small Pydantic AI-backed LLM Task boundary; keep state, scoring, authorization and persistence in the app.  |
| Social-listening abstraction         | Study OpenMagpie/Harken/Agent-Reach; reuse only components that do not distort our domain model.                             |
| Publishing                           | Build minimal approved Reddit prepare flow first. Evaluate Postiz later for broader network publishing.                      |
| MCP                                  | Build a thin server over existing application services. Study existing Reddit MCP projects for naming and ergonomics.        |
| Media                                | Integrate Higgsfield instead of building image/video generation infrastructure.                                              |
