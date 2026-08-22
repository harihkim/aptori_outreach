# PostgreSQL Data Model

> **Status:** Draft v0.3
> **Canonical:** Yes - this Markdown documentation is the source of truth.

PostgreSQL is the system of record. This is a persistence contract for the aggregate semantics and invariants in [Domain Model and State Machines](domain-model.md); large provider payloads and model outputs may use JSONB, while authorization-critical fields require queryable columns and constraints.

## Core entities

| Entity | Important fields and relationships |
|---|---|
| Workspace | `id`, `name`, `settings` |
| Campaign | `workspace_id`, `name`, `product_context`, `icp`, `keywords`, `subreddits`, `competitors`, `approved_claims`, `prohibited_claims`, `promotion_posture`, `status` |
| DiscoveryRun | `campaign_id`, frozen query/config, provider plan, `started_at`, `completed_at`, metrics, `status` |
| RetrievalObservation | `discovery_run_id`, provider variant/method/version and config SHA-256, access-identity class and egress environment, source/final URL, external source ID, `fetched_at`, result status, response/rate metadata, attempt and network counters, billable-unit/cost breakdown, raw artifact reference and SHA-256, extractor version, normalized SHA-256, completeness, failure reason |
| SourceItem | source, external ID/fullname, canonical URL, author, community, source timestamps, deletion/tombstone state, latest observed metadata |
| Conversation | `root_source_item_id`, normalized content, content hash, `first_seen_at`, `last_seen_at` |
| ConversationItem | `conversation_id`, `parent_id`, `source_item_id`, depth, normalized text, score |
| ModelRun | task ID, task/prompt/schema versions, requested and actual provider/model/settings, Pydantic AI run metadata, input/output hashes, token/cost usage, retry counts, status, timestamps, redaction policy |
| Analysis | `conversation_id`, `model_run_id`, structured factors, topic, persona, recommended action, rationale, confidence |
| Opportunity | `campaign_id`, `conversation_id`, deterministic overall score, status, `assigned_to`, `saved_at`, dismissal reason |
| ThemeCluster | `campaign_id`, label, summary, member count, period, trend delta, embedding provenance |

## Creative, review, and publishing entities

```text
Draft 1 -------- * DraftVersion
DraftVersion 1 -- * Approval
Approval 1 ------ 1 ApprovedArtifact
                            |
                            | max_uses = 1
                            v
                    PublishPreparation
```

| Entity | Important fields and relationships |
|---|---|
| Draft | `id`, `opportunity_id` or `content_theme_id`, kind, platform, `latest_version_id`, created/archived timestamps |
| DraftVersion | `id`, `draft_id`, `version_number`, text, `model_run_id` or human editor, prompt version, `created_at`, `created_by`, `content_sha256`; immutable |
| MediaJob | draft/theme reference, provider, model, prompt, status, request ID, webhook provenance, result asset IDs |
| MediaAsset | storage URI, MIME type, dimensions/duration, SHA-256, provenance, immutable/finalized timestamp |
| ActorAccount | workspace, platform, external account ID, display name, credential reference, status; secrets remain outside ordinary rows |
| Approval | `id`, `draft_version_id`, `approved_by`, `approved_at`, `expires_at`, `revoked_at`, revocation reason, status |
| ApprovedArtifact | `id`, unique `approval_id`, `draft_version_id`, text and SHA-256, ordered media manifest with asset IDs/SHA-256, destination snapshot, `actor_account_id`, action type, `expires_at`, artifact SHA-256, `max_uses=1`, consumed timestamp; immutable |
| PublishPreparation | `id`, `approved_artifact_id`, status, queued/started/ready timestamps, browser/provider evidence, failure classification; no outbound override columns |
| Feedback | target type/ID, user ID, label, reason, timestamp |
| AuditEvent | actor, action, target, before/after metadata, correlation ID, timestamp; append-oriented |

## Required constraints

- Unique `(source, external_id)` on source items and canonical URL uniqueness where reliable.
- Unique `(draft_id, version_number)` and no updates to content-bearing Draft Version columns.
- `Draft.latest_version_id` must reference a version belonging to that Draft.
- One Approved Artifact per Approval; its stored digest covers every authorization-critical field.
- Approved Artifact media checksums must match finalized Media Assets.
- Publish Preparation references an Approved Artifact and has no text, media, destination, Actor Account, or action override fields.
- Atomic single-use consumption prevents multiple preparations from the same artifact.
- Workspace ownership is enforced through composite constraints or equivalent service-level checks on every cross-aggregate reference.

## Evidence and retention

- Keep immutable raw Retrieval Observations separate from mutable latest projections.
- Preserve the frozen provider configuration or content-addressed reference needed to explain credentials class, Actor/build, proxy policy, rate/spend caps and runtime behavior without storing secrets in the observation.
- Preserve provider, retrieval, model, prompt, schema, and normalization provenance so an Opportunity can be reconstructed.
- Store full prompts/completions only under an explicit redaction and retention policy; hashes and structured outputs are the default evidence.
- The Reddit integration must support refresh and tombstoning of content deleted at the source, in accordance with the approved access and retention posture.
- Crawlee queues/storage are transient adapter mechanics, never the canonical product database.
