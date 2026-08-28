"""Discovery-run domain service: start runs, read them and their evidence."""

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auditing.service import record_audit
from app.auth import Principal
from app.campaigns.models import Campaign
from app.discovery.models import DiscoveryRun, RetrievalObservation
from app.discovery.schemas import (
    DiscoveryMethodPlan,
    DiscoveryPlanQuery,
    DiscoveryRunResponse,
)
from app.idempotency import service as idempotency
from app.pagination import decode_cursor, encode_cursor

OBSERVATION_CURSOR_NAMESPACE = "discovery-observations"

# Query ids flow into filesystem paths and deterministic job ids; they stay
# boring on purpose. The runner re-validates its kwarg against this exact
# pattern before spawning anything.
QUERY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

PlanLoader = Callable[[], DiscoveryMethodPlan]
# The production adapter (queue.enqueue_discovery_queries) is async; the port
# is async-only by design — no sync-or-coroutine speculation. Coroutine is
# required (not just Awaitable) because the service drives it via asyncio.run.
Enqueue = Callable[[UUID, str, list[str]], Coroutine[Any, Any, object]]


class WorkspaceAccessDenied(PermissionError):
    """The authenticated principal cannot operate on this workspace."""


class RetrievalInputsInvalid(ValueError):
    """The frozen query document or provider config is unusable."""


class WorkerQueueUnavailable(RuntimeError):
    """The worker queue could not accept the run's jobs."""


class DiscoveryRunNotFound(LookupError):
    """No run with that id exists, or it belongs to another workspace."""


def load_frozen_plan(
    query_document_path: Path, provider_config_path: Path
) -> DiscoveryMethodPlan:
    """Read the frozen retrieval inputs (READ ONLY) into a typed plan.

    Both files are fingerprinted by the sha256 of their exact bytes so every
    run records precisely which evidence contract it executed against.
    """
    document_bytes, document = _load_json(query_document_path)
    config_bytes, config = _load_json(provider_config_path)

    if document.get("schemaVersion") != 1:
        raise RetrievalInputsInvalid(
            f"query document schemaVersion must be 1, got {document.get('schemaVersion')!r}"
        )

    entries = document.get("queries")
    if not isinstance(entries, list) or not entries:
        raise RetrievalInputsInvalid("query document carries no queries list")

    queries: list[DiscoveryPlanQuery] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RetrievalInputsInvalid("query entries must be JSON objects")
        qid = entry.get("id")
        text = entry.get("query")
        if not isinstance(qid, str) or not qid:
            raise RetrievalInputsInvalid("query entry needs a non-empty string id")
        if QUERY_ID_PATTERN.fullmatch(qid) is None:
            raise RetrievalInputsInvalid(
                f"query id {qid!r} must match ^[A-Za-z0-9_-]{{1,64}}$"
            )
        if qid in seen_ids:
            raise RetrievalInputsInvalid(
                f"query id {qid!r} appears more than once in the plan"
            )
        seen_ids.add(qid)
        if not isinstance(text, str) or not text:
            raise RetrievalInputsInvalid(
                f"query {qid!r} needs a non-empty string query"
            )
        pattern = entry.get("pattern")
        if pattern is not None and not isinstance(pattern, str):
            raise RetrievalInputsInvalid(
                f"query {qid!r} pattern must be a string or null"
            )
        subreddits = entry.get("subreddits", [])
        if not isinstance(subreddits, list) or not all(
            isinstance(item, str) for item in subreddits
        ):
            raise RetrievalInputsInvalid(
                f"query {qid!r} subreddits must be a string list"
            )
        queries.append(
            DiscoveryPlanQuery(
                id=qid, pattern=pattern, query=text, subreddits=subreddits
            )
        )

    variant = config.get("providerVariant")
    if not isinstance(variant, str) or not variant:
        raise RetrievalInputsInvalid("provider config needs a providerVariant string")

    return DiscoveryMethodPlan(
        source="prototype-smoke",
        provider_variant=variant,
        config_sha256=hashlib.sha256(config_bytes).hexdigest(),
        document_sha256=hashlib.sha256(document_bytes).hexdigest(),
        queries=queries,
    )


def _load_json(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(raw.decode("utf-8"))
    except OSError as error:
        raise RetrievalInputsInvalid(f"{path.name} is unreadable") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RetrievalInputsInvalid(f"{path.name} is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise RetrievalInputsInvalid(f"{path.name} must contain a JSON object")
    return raw, parsed


def start_discovery_run(
    session: Session,
    principal: Principal,
    workspace_id: UUID,
    campaign_id: UUID,
    key: str,
    *,
    plan_loader: PlanLoader,
    enqueue: Enqueue,
) -> idempotency.Replay:
    """Start a run through the authorized, idempotent transaction seam."""
    _require_workspace_access(principal, workspace_id)

    def operation() -> idempotency.Replay:
        campaign = session.scalar(
            select(Campaign)
            .where(Campaign.id == campaign_id, Campaign.workspace_id == workspace_id)
            .with_for_update()
        )
        if campaign is None:
            return _error_result(404, "campaign_not_found", "Campaign not found.")
        if campaign.status != "active":
            return _error_result(
                409,
                "campaign_not_active",
                f"Campaign is {campaign.status}; discovery runs require an "
                "active campaign.",
            )
        # Frozen inputs are read inside the locked transaction; a failure
        # rolls the whole attempt back so the key stays cleanly retryable.
        plan = plan_loader()

        run = DiscoveryRun(
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.id,
            status="queued",
            method_plan=plan.model_dump(mode="json"),
            correlation_id=uuid.uuid4().hex[:16],
            metrics=None,
        )
        session.add(run)
        session.flush()
        record_audit(
            session,
            actor=principal.actor,
            action="discovery_run.created",
            target_type="discovery_run",
            target_id=run.id,
            after={"status": run.status},
            correlation_id=run.correlation_id,
        )
        return _run_result(session, run, status_code=201)

    result = idempotency.execute(
        session,
        workspace_id=workspace_id,
        key=key,
        method="POST",
        path=f"/campaigns/{campaign_id}/discovery-runs",
        payload={},
        operation=operation,
    )

    # The run row is committed at this point (fresh or replayed success).
    # Enqueueing happens for BOTH of those paths: deterministic job ids make
    # a replay re-enqueue safe, and a queue failure here leaves the stored
    # result intact so the same key retries the enqueue without duplicating
    # the run. Deterministic domain errors carry no run and nothing to queue.
    body = result.body
    if "id" not in body:
        return result
    try:
        asyncio.run(
            enqueue(
                UUID(body["id"]),
                body["correlation_id"],
                [q["id"] for q in body["method_plan"]["queries"]],
            )
        )
    except Exception as error:
        raise WorkerQueueUnavailable(
            "the worker queue refused the run; retrying with the SAME key "
            "re-enqueues deterministically"
        ) from error
    return result


def get_discovery_run(
    session: Session, principal: Principal, run_id: UUID
) -> DiscoveryRun:
    run = session.get(DiscoveryRun, run_id)
    if run is None or not principal.can_access(run.workspace_id):
        # Foreign workspaces cannot even confirm a run exists.
        raise DiscoveryRunNotFound(str(run_id))
    return run


def list_run_observations(
    session: Session,
    principal: Principal,
    run_id: UUID,
    *,
    limit: int,
    cursor: str | None,
) -> tuple[list[RetrievalObservation], str | None]:
    run = get_discovery_run(session, principal, run_id)
    statement = select(RetrievalObservation).where(
        RetrievalObservation.discovery_run_id == run.id
    )
    if cursor is not None:
        statement = statement.where(
            RetrievalObservation.creation_order
            > decode_cursor(OBSERVATION_CURSOR_NAMESPACE, cursor)
        )
    rows = list(
        session.scalars(
            statement.order_by(RetrievalObservation.creation_order.asc()).limit(
                limit + 1
            )
        )
    )
    page = rows[:limit]
    next_cursor = (
        encode_cursor(OBSERVATION_CURSOR_NAMESPACE, page[-1].creation_order)
        if len(rows) > limit
        else None
    )
    return page, next_cursor


def _run_result(
    session: Session, run: DiscoveryRun, *, status_code: int
) -> idempotency.Replay:
    session.flush()
    session.refresh(run)
    body = DiscoveryRunResponse.model_validate(run).model_dump(mode="json")
    return idempotency.Replay(status_code=status_code, body=body)


def _error_result(status_code: int, code: str, message: str) -> idempotency.Replay:
    return idempotency.Replay(
        status_code=status_code,
        body={"detail": {"code": code, "message": message}},
    )


def _require_workspace_access(principal: Principal, workspace_id: UUID) -> None:
    if not principal.can_access(workspace_id):
        raise WorkspaceAccessDenied(str(workspace_id))
