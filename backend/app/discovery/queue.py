"""Queue port: hand discovery queries to the arq worker pool.

This module deliberately stays free of arq and Redis imports at module
scope: importing it (and therefore the whole app and test suite) must never
open a Redis connection. The pool is created lazily inside the enqueue
function and closed before it returns.
"""

import uuid

from app.config import get_settings


async def enqueue_discovery_queries(
    run_id: uuid.UUID, correlation_id: str, query_ids: list[str]
) -> list[str]:
    """Enqueue one idempotent job per query; returns the deterministic ids.

    Job identity is f'discovery:{run_id}:{query_id}', so re-enqueueing the
    same run/query pair cannot produce duplicate work.
    """
    from arq import create_pool
    from arq.connections import RedisSettings

    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        job_ids: list[str] = []
        for query_id in query_ids:
            job_id = f"discovery:{run_id}:{query_id}"
            await pool.enqueue_job(
                "run_discovery_query",
                run_id=str(run_id),
                correlation_id=correlation_id,
                query_id=query_id,
                _job_id=job_id,
            )
            job_ids.append(job_id)
    finally:
        await pool.aclose()
    return job_ids
