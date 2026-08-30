"""Queue port: hand discovery queries to the arq worker pool.

This module deliberately stays free of arq and Redis imports at module
scope: importing it (and therefore the whole app and test suite) must never
open a Redis connection. The pool is created lazily inside the enqueue
function and closed before it returns.

Failure behavior: every query gets its enqueue attempt even after one is
refused, then a QueueEnqueueError names exactly which job ids landed and
which queries failed — failures are identified loudly, never swallowed.
The error is an ordinary Exception, so the injected-port caller
(service.start_discovery_run) keeps translating it into its queue-unavailable
response; deterministic job ids make the documented same-key retry safe.
"""

import uuid

from app.config import get_settings


class QueueEnqueueError(RuntimeError):
    """One or more discovery jobs were refused by the worker queue."""

    def __init__(self, *, enqueued: list[str], failed: dict[str, str]) -> None:
        self.enqueued = enqueued
        self.failed = failed
        details = ", ".join(
            f"{query_id}: {error}" for query_id, error in sorted(failed.items())
        )
        super().__init__(
            f"worker queue refused {len(failed)} discovery job(s) [{details}]; "
            f"job ids enqueued before failure: {enqueued}. Retrying re-enqueues "
            "deterministically without duplicating work."
        )


async def enqueue_discovery_queries(
    workspace_id: uuid.UUID,
    run_id: uuid.UUID,
    correlation_id: str,
    query_ids: list[str],
) -> list[str]:
    """Enqueue one idempotent job per query; returns the deterministic ids.

    Job identity is f'discovery:{workspace_id}:{run_id}:{query_id}', so
    re-enqueueing the same Workspace/run/query tuple cannot produce duplicate
    work or collide with another Workspace's run identifiers.
    """
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        enqueued_ids: list[str] = []
        failed: dict[str, str] = {}
        for query_id in query_ids:
            job_id = f"discovery:{workspace_id}:{run_id}:{query_id}"
            try:
                await pool.enqueue_job(
                    "run_discovery_query",
                    workspace_id=str(workspace_id),
                    run_id=str(run_id),
                    correlation_id=correlation_id,
                    query_id=query_id,
                    _job_id=job_id,
                )
            except Exception as error:  # noqa: BLE001 - classified below
                failed[query_id] = repr(error)
            else:
                enqueued_ids.append(job_id)
        if failed:
            raise QueueEnqueueError(enqueued=enqueued_ids, failed=failed) from None
        return enqueued_ids
    finally:
        await pool.aclose()
