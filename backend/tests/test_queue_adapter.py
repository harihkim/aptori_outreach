"""Queue adapter fan-out against a stubbed arq pool — never a real Redis.

arq is imported freely (importing it opens no sockets); the Redis pool and
connection are stub objects that record enqueue calls. Job identity, spawn
arguments, and failure behavior are pinned against the registered worker
function and the production runner signature.
"""

import asyncio
import inspect
import uuid
from collections.abc import Iterator
from typing import Any

import arq
import pytest
from arq.connections import RedisSettings

from app.config import get_settings
from app.discovery.queue import QueueEnqueueError, enqueue_discovery_queries
from app.discovery.runner import run_discovery_query
from app.discovery.worker import WorkerSettings

RUN_ID = uuid.UUID("00000000-0000-0000-0000-00000000c101")
WORKSPACE_ID = uuid.UUID("00000000-0000-0000-0000-00000000c001")
CORRELATION_ID = "corr-queue-fanout"
QUERY_IDS = [
    "q01-api-security-broad",
    "q02-appsec-tools-broad",
    "q03-sast-false-positives",
]


class StubPool:
    """An arq-pool stand-in: records calls, raises on demand, no sockets."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.redis_settings: RedisSettings | None = None
        self.fail_query_ids: set[str] = set()
        self.closed = False

    async def enqueue_job(self, function: str, **kwargs: Any) -> object:
        query_id = str(kwargs.get("query_id"))
        if query_id in self.fail_query_ids:
            raise RuntimeError(f"stub redis refused {query_id}")
        self.calls.append({"function": function, **kwargs})
        return object()  # arq would return a Job; the adapter ignores it

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture()
def stub_pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[StubPool]:
    """Route arq.create_pool to a stub; importing arq connects to nothing."""
    pool = StubPool()

    async def fake_create_pool(settings: RedisSettings) -> StubPool:
        pool.redis_settings = settings
        return pool

    monkeypatch.setattr(arq, "create_pool", fake_create_pool)
    yield pool


def expected_job_id(query_id: str) -> str:
    return f"discovery:{WORKSPACE_ID}:{RUN_ID}:{query_id}"


def test_fanout_enqueues_one_job_per_query_and_closes_pool(stub_pool: StubPool) -> None:
    job_ids = asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )

    assert job_ids == [expected_job_id(qid) for qid in QUERY_IDS]
    assert len(stub_pool.calls) == len(QUERY_IDS)
    assert stub_pool.closed is True
    assert stub_pool.redis_settings == RedisSettings.from_dsn(get_settings().redis_url)


def test_job_ids_are_deterministic_per_frozen_query(stub_pool: StubPool) -> None:
    """Same inputs produce identical ids; distinct queries never collide."""
    first = asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )
    second = asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )

    assert first == second
    assert len(set(first)) == len(QUERY_IDS)
    for query_id in QUERY_IDS:
        assert f"discovery:{WORKSPACE_ID}:{RUN_ID}:{query_id}" in first
    # A different run id must not reuse another run's deterministic ids.
    other_run = uuid.UUID("00000000-0000-0000-0000-00000000c102")
    other = asyncio.run(
        enqueue_discovery_queries(
            WORKSPACE_ID, other_run, CORRELATION_ID, QUERY_IDS[:1]
        )
    )
    assert other[0] != first[0]

    # Workspace ownership is part of identity even if IDs are reused.
    other_workspace = uuid.UUID("00000000-0000-0000-0000-00000000c002")
    foreign = asyncio.run(
        enqueue_discovery_queries(
            other_workspace, RUN_ID, CORRELATION_ID, QUERY_IDS[:1]
        )
    )
    assert foreign[0] != first[0]


def test_jobs_target_the_registered_function_with_runner_kwargs(
    stub_pool: StubPool,
) -> None:
    """Each job names the worker-registered function and runner kwargs only."""
    asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )

    registered_names = [function.__name__ for function in WorkerSettings.functions]
    runner_params = set(inspect.signature(run_discovery_query).parameters) - {"ctx"}

    assert "run_discovery_query" in registered_names
    assert [call["query_id"] for call in stub_pool.calls] == QUERY_IDS
    for index, call in enumerate(stub_pool.calls):
        assert call["function"] == "run_discovery_query"
        # Exactly the runner's keyword contract plus arq's job-id knob.
        assert set(call) - {"function"} == runner_params | {"_job_id"}
        assert call["workspace_id"] == str(WORKSPACE_ID)
        assert call["run_id"] == str(RUN_ID)
        assert call["correlation_id"] == CORRELATION_ID
        assert call["query_id"] == QUERY_IDS[index]
        assert call["_job_id"] == expected_job_id(QUERY_IDS[index])


def test_partial_failure_raises_identifying_failed_and_enqueued(
    stub_pool: StubPool,
) -> None:
    """Refusals are loud: failed query ids named, enqueued ids accounted."""
    failing = QUERY_IDS[1]
    stub_pool.fail_query_ids = {failing}

    with pytest.raises(QueueEnqueueError) as excinfo:
        asyncio.run(
            enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
        )

    error = excinfo.value
    assert error.enqueued == [
        expected_job_id(QUERY_IDS[0]),
        expected_job_id(QUERY_IDS[2]),
    ]
    assert set(error.failed) == {failing}
    message = str(error)
    assert failing in message
    assert expected_job_id(QUERY_IDS[0]) in message
    assert "deterministically" in message  # retry guidance stays attached
    # The injected port stays an ordinary Exception for service.py to wrap.
    assert isinstance(error, Exception)
    # The pool is closed even when the fan-out fails.
    assert stub_pool.closed is True


def test_total_failure_reports_every_failed_query_id(stub_pool: StubPool) -> None:
    stub_pool.fail_query_ids = set(QUERY_IDS)

    with pytest.raises(QueueEnqueueError) as excinfo:
        asyncio.run(
            enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
        )

    error = excinfo.value
    assert error.enqueued == []
    assert set(error.failed) == set(QUERY_IDS)


def test_replay_enqueues_identical_job_ids_again(stub_pool: StubPool) -> None:
    """Re-enqueueing the same run/query pair reuses the same job ids."""
    first = asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )
    second = asyncio.run(
        enqueue_discovery_queries(WORKSPACE_ID, RUN_ID, CORRELATION_ID, QUERY_IDS)
    )

    assert first == second
    both_batches = [call["_job_id"] for call in stub_pool.calls]
    assert both_batches == first + first
