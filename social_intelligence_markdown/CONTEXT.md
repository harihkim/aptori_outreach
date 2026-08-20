# Social Intelligence and Engagement

This context describes the language of the Reddit-first opportunity, drafting, review, and preparation workflow. These terms are stable across the web UI, REST API, MCP adapter, workers, and external providers.

## Discovery and intelligence

**Campaign**:
A configured research objective containing the market, audience, source, and positioning constraints used to find and assess conversations.
_Avoid_: Monitor, search job

**Discovery Run**:
One bounded attempt to find candidate conversations for a Campaign using one or more approved discovery sources.
_Avoid_: Crawl

**Candidate**:
A source locator returned by discovery before complete thread retrieval, normalization, deduplication, and analysis.
_Avoid_: Opportunity, Conversation

**Retrieval Observation**:
An immutable record of what one retrieval method observed at a source at a particular time, including provenance, completeness, and failure classification.
_Avoid_: Conversation snapshot

**Conversation**:
The canonical normalized representation of one source discussion across one or more Retrieval Observations.
_Avoid_: Page, scrape

**Opportunity**:
A Campaign-specific assessment that a Conversation may merit monitoring, a helpful response, or original content work.
_Avoid_: Lead, Candidate

## Creative and review

**Draft**:
The stable identity and history of a proposed outbound work item. A Draft contains immutable Draft Versions; it does not contain mutable outbound text.
_Avoid_: Draft Version

**Draft Version**:
One immutable content revision of a Draft, created by generation, regeneration, or human editing.
_Avoid_: Draft revision state

**Approval**:
The immutable human decision that authorizes one Draft Version for a specified outbound action scope, subject to expiration and revocation.
_Avoid_: Model approval, review status

**Approved Artifact**:
The immutable executable authorization snapshot derived from an Approval, binding exact content and media to one actor account, action type, and destination.
_Avoid_: Approved draft, approval token

**Actor Account**:
The external platform identity from which an approved outbound action is prepared.
_Avoid_: User, approver

**Destination**:
The exact external location for an outbound action, including platform-specific thread, community, and parent identifiers.
_Avoid_: Channel

**Publish Preparation**:
A single-use attempt to place an Approved Artifact into the intended external composer. In the preferred prototype it stops before final submission.
_Avoid_: Publish Job, post

## AI execution

**LLM Task**:
A named, bounded semantic operation with versioned input/output contracts, model policy, budgets, and evaluation criteria.
_Avoid_: Agent when no open-ended planning or tool loop is involved
