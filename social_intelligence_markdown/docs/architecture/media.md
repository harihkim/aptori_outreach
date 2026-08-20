# Higgsfield Media Integration

> **Status:** Draft v0.1  
> **Canonical:** Yes - this Markdown documentation is the source of truth.

Defines how generated image/video assets enter the same versioned review and approval lifecycle as text.

## Higgsfield integration

1. Creative service creates a structured media brief and platform requirements.

2. Media worker submits to a configured Higgsfield model endpoint.

3. Persist request ID and job metadata immediately.

4. Receive webhook or poll status; make callbacks idempotent.

5. Download completed assets into company-controlled object storage for retention.

6. Associate assets with draft versions. Changing selected media after approval requires a new approval.


> **Retention note.** Higgsfield documents generated outputs as available for at least seven days. Production should copy completed media to owned storage rather than treating provider URLs as durable assets.

## Media approval rule

An approval must cover the selected media asset IDs/checksums as well as the text version. Replacing an image or video after approval invalidates that approval.

See [ADR-008](../adr/008-higgsfield-as-media-provider.md).

## Research references

See the [research source catalog](../research/source-catalog.md) for the primary documentation and open-source repositories used during the initial design.
