# Research Source Catalog

> **Status:** Living reference
> **Canonical:** Yes - this Markdown documentation is the source of truth.

External references used during the initial product/architecture research. Verify time-sensitive policy/API claims against current primary documentation before shipping.

## Research source catalog

**\[R1\]** [Cua GitHub repository](https://github.com/trycua/cua) - Computer-use drivers, sandbox SDK, agent framework, benchmarks; MIT.

**\[R2\]** [Gemini API - Computer Use](https://ai.google.dev/gemini-api/docs/computer-use) - Native computer-use tooling and safety behavior.

**\[R3\]** [Gemini API - Google Search grounding](https://ai.google.dev/gemini-api/docs/generate-content/google-search) - Real-time web search grounding and source metadata.

**\[R4\]** [Gemini API - URL Context](https://ai.google.dev/gemini-api/docs/url-context) - URL retrieval and Search combination.

**\[R5\]** [Reddit and Google partnership](https://redditinc.com/news/reddit-and-google-expand-partnership) - Google access to structured Reddit Data API content; does not alter developer commercial-use terms.

**\[R6\]** [Reddit and OpenAI partnership](https://redditinc.com/news/reddit-and-oai-partner) - Separate Reddit Data API partnership demonstrating Google access is not exclusive.

**\[R7\]** [Reddit - Developer Platform & Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data) - Current developer interfaces, approval, and commercial-use information.

**\[R8\]** [Reddit - Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy) - App transparency and automated-activity restrictions.

**\[R9\]** [Reddit - Modernizing Infrastructure and Moderation Tools](https://redditinc.com/news/modernizing-reddits-infrastructure-and-moderation-tools) - August 2026 plans to strengthen anti-scraping and shift third-party apps toward Developer Platform.

**\[R10\]** [Higgsfield API](https://docs.higgsfield.ai/docs) - Async image/video/audio/3D API and asset-retention guidance.

**\[R11\]** [Pydantic AI - overview](https://pydantic.dev/docs/ai/overview/) - Typed agent framework and integrations.

**\[R12\]** [Pydantic AI - Deferred Tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/) - Human-in-the-loop approval and external tool execution.

**\[R13\]** [MCP specification 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28) - Current MCP architecture, tools/resources/prompts, security principles.

**\[R14\]** [OpenMagpie GitHub](https://github.com/obris-dev/openmagpie) - Self-hosted social listening, Reddit/RSS connectors, semantic filter; Apache-2.0.

**\[R15\]** [RedoraAI GitHub](https://github.com/donebyai-team/RedoraAI) - Reddit lead-generation workflow and architecture; MIT.

**\[R16\]** [PRAW GitHub](https://github.com/praw-dev/praw) - Mature synchronous Python Reddit API wrapper; BSD-2-Clause.

**\[R17\]** [RedditRadar GitHub](https://github.com/devravik/RedditRadar) - Reddit monitoring and AI lead dashboard; MIT.

**\[R18\]** [Harken GitHub](https://github.com/VladUZH/harken) - Multi-source social listening and themes; MIT.

**\[R19\]** [Agent Reach GitHub](https://github.com/Panniantong/Agent-Reach) - Installer/doctor/skill router over upstream CLIs; reference engineering, not a production retrieval SDK.

**\[R20\]** [Obscura GitHub](https://github.com/h4ckf0r0day/obscura) - Rust headless browser for scraping/agent automation.

**\[R21\]** [Postiz GitHub](https://github.com/gitroomhq/postiz-app) - Self-hosted multi-channel social scheduling; evaluate licensing/integration model before reuse.

**\[R22\]** [reddit-mcp-server GitHub](https://github.com/eliasbiondo/reddit-mcp-server) - Example Reddit MCP read/search tool surface.

**\[R23\]** [Async PRAW GitHub](https://github.com/praw-dev/asyncpraw) - Official asynchronous PRAW variant and recommended implementation for the async backend; BSD-2-Clause.

**\[R24\]** [Crawlee for Python GitHub](https://github.com/apify/crawlee-python) - Async HTTP/browser crawling, queues, sessions, retries, throttling and storage; Apache-2.0.

**\[R25\]** [Crawlee - Pydantic AI crawler](https://crawlee.dev/python/docs/guides/pydantic-ai-crawler) - Experimental typed LLM extraction over HTTP/Parsel and its cost/runtime boundaries.

**\[R26\]** [Pydantic AI - output](https://pydantic.dev/docs/ai/core-concepts/output/) - Typed structured outputs, validation, retries and streaming semantics.

**\[R27\]** [Pydantic AI - retries](https://pydantic.dev/docs/ai/core-concepts/retries/) - Distinguishes transport, model, tool, output and whole-run retry responsibilities.

**\[R28\]** [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/) - Versioned datasets, evaluators and experiment reports for bounded LLM Tasks.

**\[R29\]** [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki) - OAuth, User-Agent, rate-limit and deletion/retention guidance.

**\[R30\]** [Reddit Data API Terms](https://redditinc.com/policies/data-api-terms) - Access, use, retention and control-circumvention constraints.

**\[R31\]** [OpenCLI GitHub](https://github.com/jackwener/opencli) - Browser-extension/local-daemon CLI whose Reddit adapter uses logged-in browser-origin JSON endpoints and also exposes write operations.

**\[R32\]** [`rdt-cli` GitHub](https://github.com/public-clis/rdt-cli) - Reverse-engineered cookie-authenticated Reddit web-JSON CLI; higher-policy-risk diagnostic reference.

**\[R33\]** [Brave Search API authentication](https://api-dashboard.search.brave.com/documentation/guides/authentication) - Supported Brave Search API requests require a subscription token.

**\[R34\]** [Brave Search API rate limiting](https://api-dashboard.search.brave.com/documentation/guides/rate-limiting) - Subscription-scoped limit, remaining and reset headers plus `429` behavior.

**\[R35\]** [Apify - Run Actors](https://docs.apify.com/actors/running) - Actor selection, structured invocation, dataset retrieval and account billing behavior.

**\[R36\]** [Apify - Actor input and output](https://docs.apify.com/actors/running/input-and-output) - Actor-specific input, build/runtime options, output schemas and storage locations.

**\[R37\]** [Apify residential proxy](https://docs.apify.com/proxy/residential-proxy) - Explicit proxy configuration, traffic pricing, latency variation and connection interruptions.

**\[R38\]** [Apify blocked-proxy guidance](https://docs.apify.com/academy/node-js/filter-blocked-requests-using-sessions) - Proxy pools can remain or become blocked; no proxy is guaranteed indefinitely.

**\[R39\]** [Reddit User Agreement](https://redditinc.com/policies/user-agreement) - Current automated collection, crawling and scraping restrictions.

**\[R40\]** [Reddit robots/crawler statement](https://redditinc.com/news/robot-txt-update) - Unknown crawlers may be rate-limited or blocked; technical reachability does not confer permission.
