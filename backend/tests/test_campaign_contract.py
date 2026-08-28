"""Cross-runtime Campaign lifecycle contract checks."""

import json
from pathlib import Path
from typing import Any, cast, get_args

from app.campaigns.models import CAMPAIGN_POSTURES, CAMPAIGN_STATUSES
from app.campaigns.schemas import CampaignStatus, PromotionPosture
from app.campaigns.service import LEGAL_TRANSITIONS

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "contracts/campaign-lifecycle.json"
)


def _contract() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text()))


def test_campaign_enums_match_the_shared_contract() -> None:
    contract = _contract()

    assert list(CAMPAIGN_STATUSES) == contract["statuses"]
    assert list(get_args(CampaignStatus)) == contract["statuses"]
    assert list(CAMPAIGN_POSTURES) == contract["promotionPostures"]
    assert list(get_args(PromotionPosture)) == contract["promotionPostures"]


def test_campaign_transitions_match_the_shared_contract() -> None:
    contract = _contract()
    expected = {
        (current, requested)
        for current, requested_statuses in contract["transitions"].items()
        for requested in requested_statuses
    }

    assert expected == LEGAL_TRANSITIONS
