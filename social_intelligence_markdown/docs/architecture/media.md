# Higgsfield Media Integration

> **Status:** Draft v0.2
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines the expansion-stage Higgsfield integration and how generated image/video assets enter the same action-scoped approval lifecycle as text.

## Higgsfield integration

1. Creative service creates a structured media brief and platform requirements.

2. Media worker submits to a configured Higgsfield model endpoint.

3. Persist request ID and job metadata immediately.

4. Receive webhook or poll status; make callbacks idempotent.

5. Download completed assets into company-controlled object storage for retention.

6. Finalize each asset with an immutable SHA-256 and associate its provenance with the relevant Draft/Draft Version.


> **Retention note.** Higgsfield documents generated outputs as available for at least seven days. Production should copy completed media to owned storage rather than treating provider URLs as durable assets.

## Media approval rule

An Approved Artifact stores the ordered media asset IDs and checksums along with the exact Draft Version, Actor Account, action, and Destination. Replacing, reordering, or mutating media requires a new Approval.

Higgsfield is not a Retrieval Gate R0 or prototype vertical-slice dependency. Implement this integration only in the expansion milestone defined by the [roadmap](../roadmap/roadmap.md).

See [ADR-008](../adr/008-higgsfield-as-media-provider.md).

## Research references

See the [research source catalog](../research/source-catalog.md) for the primary documentation and open-source repositories used during the initial design.
