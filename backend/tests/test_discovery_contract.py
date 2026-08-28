"""Contract sync: backend status vocabulary equals the frozen JSON contract.

contracts/discovery-run-statuses.json is the single source of truth shared
with the frontend; drift in either direction fails here. The alembic-head
database CHECK is compared against the ORM tuples and the JSON so migration
vocabulary drift fails deterministically.
"""

import json
import re
from pathlib import Path
from typing import Any, get_args

from alembic import command
from sqlalchemy import create_engine, text

from app.discovery.models import (
    DISCOVERY_RUN_STATUSES,
    RETRIEVAL_OBSERVATION_STATUSES,
    RUN_COST_STATUSES,
)
from app.discovery.observations import STATUS_VALUES
from app.discovery.schemas import DiscoveryRunResponse
from tests.conftest import TEST_DATABASE_URL

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "discovery-run-statuses.json"
)


def _contract() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return parsed


def test_parser_observation_statuses_match_contract_exactly() -> None:
    contract = _contract()

    assert list(STATUS_VALUES) == contract["observationStatuses"]


def test_run_response_status_literal_matches_contract_exactly() -> None:
    contract = _contract()

    annotation = DiscoveryRunResponse.model_fields["status"].annotation
    assert sorted(get_args(annotation)) == sorted(contract["runStatuses"])
    assert list(DISCOVERY_RUN_STATUSES) == contract["runStatuses"]


def test_cost_vocabulary_is_unpriced_only() -> None:
    """Currency cost is never invented: 'unpriced' is the only honest state."""
    contract = _contract()

    assert list(RUN_COST_STATUSES) == ["unpriced"]
    assert contract["costStatuses"] == list(RUN_COST_STATUSES)


def test_run_metrics_shape_is_pinned_for_frontend_consumers() -> None:
    """Run-metrics keys are contract surface; drift fails deterministically.

    The frontend run screen consumes exactly this shape (metrics.usage
    nesting included) and is being aligned to it, so both sides pin the
    same key sets here via the runner's emitted-shape constants.
    """
    from app.discovery.models import RUN_COST_UNPRICED
    from app.discovery.runner import RUN_METRICS_KEYS, RUN_USAGE_KEYS

    assert (
        frozenset({"counts", "total_elapsed_ms", "cost_usd", "cost_status", "usage"})
        == RUN_METRICS_KEYS
    )
    assert frozenset({"request_count", "bytes_transferred"}) == RUN_USAGE_KEYS
    # The cost_status key in the pinned shape carries only frozen vocabulary.
    assert "cost_status" in RUN_METRICS_KEYS
    assert list(RUN_COST_STATUSES) == [RUN_COST_UNPRICED]


def test_failure_class_vocabulary_matches_every_layer(
    migrated_test_database: str,
) -> None:
    """DB CHECK == ORM tuple == wire Literal == contract JSON, exactly."""
    from typing import get_args as typing_get_args

    from alembic.config import Config

    from app.discovery.models import FAILURE_CLASSES
    from app.discovery.schemas import FailureClass, RetrievalObservationResponse

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            db_classes = _head_check_values(
                connection, "ck_retrieval_observations_failure_class_values"
            )
    finally:
        engine.dispose()

    contract = _contract()
    assert db_classes == tuple(FAILURE_CLASSES)
    assert list(typing_get_args(FailureClass)) == contract["failureClasses"]
    # The wire response allows the Literal or NULL — never a bare str.
    field_annotation = RetrievalObservationResponse.model_fields[
        "failure_class"
    ].annotation
    assert typing_get_args(field_annotation) == (FailureClass, type(None))


def _head_check_values(connection: Any, constraint_name: str) -> tuple[str, ...]:
    definition = connection.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :name"
        ),
        {"name": constraint_name},
    ).scalar_one()
    return tuple(re.findall(r"'([a-z_]+)'", str(definition)))


def test_head_database_checks_match_orm_and_contract(
    migrated_test_database: str,
) -> None:
    """Migration CHECK drift from the ORM tuples fails deterministically."""
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            observation_statuses = _head_check_values(
                connection, "ck_retrieval_observations_status_values"
            )
            run_statuses = _head_check_values(
                connection, "ck_discovery_runs_status_values"
            )
    finally:
        engine.dispose()

    contract = _contract()
    assert observation_statuses == tuple(RETRIEVAL_OBSERVATION_STATUSES)
    assert observation_statuses == tuple(STATUS_VALUES)
    assert observation_statuses == tuple(contract["observationStatuses"])
    assert run_statuses == tuple(DISCOVERY_RUN_STATUSES)
    assert run_statuses == tuple(contract["runStatuses"])
