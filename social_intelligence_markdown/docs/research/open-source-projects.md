# Open-Source Projects to Study or Reuse

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Projects identified during research, with a deliberate distinction between architecture inspiration, reusable components and production dependencies.

## Open-source projects to study or reuse

| **Project**                | **Use for us**                                                                               | **Recommendation**                                                                                   |
|----------------------------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| trycua/cua                 | Computer-use drivers, sandboxing, agent framework, MCP/automation infrastructure.            | Top-priority integration study for MVP browser execution.                                            |
| RedoraAI                   | End-to-end Reddit lead workflow: discovery, scoring, AI comments/DMs, scheduling, dashboard. | Study product/data flow deeply; do not copy autonomous-engagement patterns.                          |
| OpenMagpie                 | Clean source/watch/action architecture, semantic filtering, auditability, webhooks.          | Strong architecture reference; possible reusable components depending on fit.                        |
| PRAW                       | Mature Python wrapper for approved Reddit API access.                                        | Future official-provider implementation once access is available.                                    |
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
| Reddit browser automation            | Integrate/learn from CUA. Keep our own provider contract and task definitions.                                               |
| Official Reddit provider             | Implement later with PRAW or direct API once approved.                                                                       |
| Social-listening abstraction         | Study OpenMagpie/Harken/Agent-Reach; reuse only components that do not distort our domain model.                             |
| Publishing                           | Build minimal approved Reddit prepare flow first. Evaluate Postiz later for broader network publishing.                      |
| MCP                                  | Build a thin server over existing application services. Study existing Reddit MCP projects for naming and ergonomics.        |
| Media                                | Integrate Higgsfield instead of building image/video generation infrastructure.                                              |
