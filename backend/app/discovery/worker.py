"""arq worker wiring for discovery runs.

Launch the worker from the backend directory:

    cd backend && .venv/bin/python -m arq app.discovery.worker.WorkerSettings

The settings class is the whole contract: it registers the plain
run_discovery_query function (no spawn overrides), points Redis at the
configured queue, bounds each job to one attempt plus headroom, and schedules
the stale-run reaper cron.
"""

from datetime import UTC, datetime, timedelta

from arq.connections import RedisSettings
from arq.cron import cron
from sqlalchemy import select

from app.auditing.service import record_audit
from app.config import get_settings
from app.db import DatabaseSessionManager
from app.discovery.models import DiscoveryRun
from app.discovery.runner import run_discovery_query

# A run is stale once it has been running for three full attempt timeouts
# (with a floor so a very small configured timeout cannot reap live runs).
REAP_MULTIPLIER = 3
REAP_FLOOR_SECONDS = 900


def _noop_startup(ctx: dict[str, object]) -> None:
    """arq startup hook; the runner owns its own resources per invocation."""
    del ctx


def _noop_shutdown(ctx: dict[str, object]) -> None:
    """arq shutdown hook; nothing persistent to release."""
    del ctx


async def reap_stale_running_runs(ctx: object) -> int:
    """Fail runs stuck in 'running' past any plausible attempt duration.

    A worker crash between the claim commit and the settle transaction would
    otherwise leave a run running forever. Reaping is row-locked, merges a
    {'reaped': True} note into metrics, and writes its own audit event; the
    returns count of reaped rows for observability.
    """
    del ctx  # the reaper owns its own database session
    settings = get_settings()
    threshold_seconds = max(
        REAP_MULTIPLIER * settings.retrieval_attempt_timeout_seconds,
        REAP_FLOOR_SECONDS,
    )
    cutoff = datetime.now(UTC) - timedelta(seconds=threshold_seconds)

    manager = DatabaseSessionManager(
        settings.database_url,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
    )
    try:
        reaped = 0
        with manager.session_factory() as session, session.begin():
            stale_runs = list(
                session.scalars(
                    select(DiscoveryRun)
                    .where(
                        DiscoveryRun.status == "running",
                        DiscoveryRun.started_at.is_not(None),
                        DiscoveryRun.started_at < cutoff,
                    )
                    .with_for_update()
                )
            )
            for run in stale_runs:
                previous_status = run.status
                run.status = "failed"
                run.completed_at = datetime.now(UTC)
                metrics_note = dict(run.metrics or {})
                metrics_note["reaped"] = True
                run.metrics = metrics_note
                record_audit(
                    session,
                    actor="worker",
                    action="discovery_run.reaped",
                    target_type="discovery_run",
                    target_id=run.id,
                    before={"status": previous_status},
                    after={"status": "failed"},
                    correlation_id=run.correlation_id,
                )
                reaped += 1
        return reaped
    finally:
        manager.dispose()


class WorkerSettings:
    """The single arq entrypoint; see the module docstring for launch."""

    functions = [run_discovery_query]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = _noop_startup
    on_shutdown = _noop_shutdown
    # One retrieval attempt per job plus generous headroom for classification
    # and settle; a stuck job dies here even before the reaper would.
    job_timeout = get_settings().retrieval_attempt_timeout_seconds + 60
    max_tries = 1
    keep_result = 0
    cron_jobs = [
        cron(
            reap_stale_running_runs,
            minute=set(range(0, 60, 5)),  # every 300 seconds
            second=0,
            unique=True,
            run_at_startup=True,
        )
    ]
