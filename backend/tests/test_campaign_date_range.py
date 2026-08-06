from datetime import date
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.campaigns import get_promotions_incentives
from services.campaigns import CampaignDateRangeError, validate_campaign_date_range
from services.campaigns.metrics import (
    CAMPAIGN_REQUEST_REJECTED_TOTAL,
    record_campaign_request_rejected,
)


def test_campaign_range_accepts_first_and_last_day_of_one_month() -> None:
    assert validate_campaign_date_range(date(2024, 2, 1), date(2024, 2, 29)) == "2024-02"


@pytest.mark.parametrize(
    ("start", "end", "reason"),
    [
        (date(2026, 8, 2), date(2026, 8, 1), "start_date_after_end_date"),
        (date(2026, 8, 31), date(2026, 9, 1), "cross_month_range_not_supported"),
    ],
)
def test_campaign_range_rejects_ambiguous_ranges(
    start: date,
    end: date,
    reason: str,
) -> None:
    with pytest.raises(CampaignDateRangeError) as exc_info:
        validate_campaign_date_range(start, end)
    assert exc_info.value.code == "campaign_date_range_invalid"
    assert exc_info.value.reason == reason


@pytest.mark.asyncio
async def test_router_records_rejected_campaign_range_with_finite_reason() -> None:
    reason = "cross_month_range_not_supported"
    metric = CAMPAIGN_REQUEST_REJECTED_TOTAL.labels(reason=reason)
    before = metric._value.get()
    service = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_promotions_incentives(
            start_date=date(2026, 8, 31),
            end_date=date(2026, 9, 1),
            svc=service,
        )

    assert exc_info.value.status_code == 422
    assert metric._value.get() == before + 1
    service.get_promotions_incentives.assert_not_awaited()


def test_rejection_metric_refuses_unbounded_reason_labels() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        record_campaign_request_rejected("user-controlled-detail")  # type: ignore[arg-type]
