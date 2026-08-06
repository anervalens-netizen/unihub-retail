"""Typed monthly date boundary for Campaigns requests."""

from __future__ import annotations

from datetime import date


class CampaignDateRangeError(ValueError):
    """Finite, client-safe validation failure for monthly campaign ranges."""

    code = "campaign_date_range_invalid"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def validate_campaign_date_range(start_date: date | str, end_date: date | str) -> str:
    """Validate the authoritative monthly Campaigns boundary and return YYYY-MM."""
    try:
        start_date = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
        end_date = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    except ValueError as exc:
        raise CampaignDateRangeError("invalid_iso_date") from exc
    if start_date > end_date:
        raise CampaignDateRangeError("start_date_after_end_date")
    if (start_date.year, start_date.month) != (end_date.year, end_date.month):
        raise CampaignDateRangeError("cross_month_range_not_supported")
    return start_date.strftime("%Y-%m")
