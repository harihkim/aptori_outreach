# PostgreSQL Data Model

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

The initial relational model. PostgreSQL is the system of record; large flexible analysis/provenance fields may use JSONB where appropriate.

## PostgreSQL data model

| **Entity**        | **Important fields / relationships**                                                                       |
|-------------------|------------------------------------------------------------------------------------------------------------|
| workspace         | id, name, settings                                                                                         |
| campaign          | workspace_id, name, product_context, ICP, keywords, subreddits, competitors, promotion_posture, status     |
| discovery_run     | campaign_id, provider, query, started_at, completed_at, metrics, status                                    |
| source_item       | source, external_id, url, canonical_url, author, community, created_at, raw_metadata, retrieval_provenance |
| conversation      | root_source_item_id, normalized_text, thread_metadata, content_hash, first_seen_at, last_seen_at           |
| conversation_item | conversation_id, parent_id, source_item_id, depth, text, score                                             |
| analysis          | conversation_id, model, schema_version, scores JSONB, topic, persona, action, rationale, confidence        |
| opportunity       | campaign_id, conversation_id, overall_score, status, assigned_to, saved_at, dismissed_reason               |
| theme_cluster     | campaign_id, label, summary, member_count, period, trend_delta, embedding metadata                         |
| draft             | opportunity_id/content_theme_id, kind, platform, version, text, model, prompt_version, status              |
| approval          | draft_id, draft_version, approver_id, approved_at, content_hash, status                                    |
| media_job         | draft_id/theme_id, provider, model, prompt, status, request_id, webhook payload, asset_id                  |
| media_asset       | storage_uri, mime_type, width, height, duration, checksum, provenance                                      |
| publish_job       | approval_id, destination, provider, status, prepared_at, posted_at, external_id, error                     |
| feedback          | entity_type/id, user_id, label, reason, created_at                                                         |
| audit_event       | actor, action, entity, before/after metadata, correlation_id, timestamp                                    |

## Modeling guidance

- Use UUID/ULID identifiers consistently.
- Make draft versions immutable; edits create a new version.
- Store canonical source identifiers separately from provider-specific raw metadata.
- Keep audit events append-oriented.
- Add unique constraints for `(source, external_id)` and normalized/canonical URLs where reliable.
- Preserve retrieval and model provenance so any opportunity can be reconstructed and explained.
