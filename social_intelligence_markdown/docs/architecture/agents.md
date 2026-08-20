# AI and Agent Design

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

AI is used as typed, bounded reasoning/generation inside deterministic application workflows rather than as a single autonomous marketing agent.

```mermaid
flowchart LR
    D[Discover] --> N[Normalize]
    N --> X[Deduplicate]
    X --> F[Cheap filter]
    F --> A[Typed intelligence call]
    A --> S[Score + persist]
    S --> G[Typed creative call]
    G --> V[Draft version]
    V --> H[Human review]
```

## AI design: bounded agents inside deterministic workflows

```text
Discover -> Normalize -> Deduplicate -> Cheap filter
-> Analyze (typed AI) -> Score -> Persist
-> Draft (typed AI) -> Persist -> Human review
-> Approved artifact -> Browser prepare/publish worker
```


Do not build one "super-agent" that decides the entire workflow. The application owns state transitions, retries, authorization, content hashes, provider routing, and audit events. AI is invoked for tasks that benefit from semantic reasoning or generation.

### Intelligence agent output


```python
class ConversationAnalysis(BaseModel):
    relevance: float
    pain_intensity: float
    buying_intent: float
    replyability: float
    product_fit: float
    promotion_fit: float
    confidence: float
    persona: str | None
    topic: str
    rationale: str
    recommended_action: Literal[
        "ignore",
        "monitor",
        "reply_helpfully",
        "reply_with_product",
        "content_opportunity",
    ]
```


Use low-cost models for initial relevance/intent analysis. Reserve stronger models for borderline or high-value opportunities, complex thread synthesis, and final creative drafting. Model selection should be a configuration, not hard-coded in domain logic.

### Creative agent separation

- Reply generation uses thread context plus campaign guidance.

- Standalone content generation uses approved company/product knowledge plus aggregate themes and externally verifiable facts as needed.

- Media-brief generation produces visual objective, composition, style, aspect ratio, constraints, and a Higgsfield-ready prompt.

- Scoring and generation are separate model calls. This improves observability, cost control, evaluation, and regeneration behavior.

## Model routing principle

Use the least-expensive model that meets the quality threshold for each stage. Escalate borderline/high-value cases rather than using the strongest model for all candidates. Keep model/provider selection configuration-driven.

See [ADR-002](../adr/002-pydantic-ai-primary-orchestrator.md) and [ADR-005](../adr/005-bounded-agents-deterministic-workflows.md).

## Research references

See the [research source catalog](../research/source-catalog.md) for the primary documentation and open-source repositories used during the initial design.
