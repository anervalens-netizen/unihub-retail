from datetime import date

import pytest

from services.campaigns import CampaignDateRangeError, validate_campaign_date_range


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
