"""Contract sync: backend status vocabulary equals the frozen JSON contract.

contracts/discovery-run-statuses.json is the single source of truth shared
with the frontend; drift in either direction fails here.
"""

import json
from pathlib import Path
from typing import Any, get_args

from app.discovery.models import DISCOVERY_RUN_STATUSES
from app.discovery.observations import STATUS_VALUES
from app.discovery.schemas import DiscoveryRunResponse

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
