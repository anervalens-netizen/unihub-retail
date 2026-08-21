"""Campaigns request assembly: parse dates, load configuration, build internal request."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from domain.filter_scope import FilterInput

from services.campaigns.dates import (
    CampaignDateRangeError,
    validate_campaign_date_range,
)
from services.campaigns.loader import load_campaign_configuration
from services.campaigns.metrics import record_campaign_request_rejected


@dataclass(slots=True)
class CampaignRequest:
    """Immutable Campaigns request built from validated inputs and configuration."""

    start: date
    end: date
    month: str
    firma: str | None
    regional: str | None
    asm: str | None
    site_code: FilterInput
    agent: FilterInput
    config_error: str | None
    promotion_definitions: list[dict[str, Any]]
    promotion_list_error: str | None
    promotion_definition: dict[str, Any] | None
    promotion_error: str | None
    include_incentive: bool
    current_scope: bool
    include_closed_stores: bool


def parse_campaign_dates(
    start_date: date | str,
    end_date: date | str,
) -> tuple[date, date]:
    """Parse ISO date inputs; record invalid_iso_date metric and raise on failure."""
    try:
        start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
        end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
    except ValueError as exc:
        record_campaign_request_rejected("invalid_iso_date")
        raise CampaignDateRangeError("invalid_iso_date") from exc
    return start, end


def build_campaign_request(
    start_date: date,
    end_date: date,
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    promotion_key: str | None,
    view: str,
    current_scope: bool,
    include_closed_stores: bool,
    config_loader: Callable[[], tuple[dict[str, Any], str | None]],
    definitions_loader: Callable[
        [dict[str, Any], str], tuple[list[dict[str, Any]], str | None]
    ],
    definition_loader: Callable[
        [dict[str, Any], str, str | None],
        tuple[dict[str, Any] | None, str | None],
    ],
) -> CampaignRequest:
    """Build the immutable Campaigns request: parse dates, validate range, load configuration."""
    start, end = parse_campaign_dates(start_date, end_date)
    month = validate_campaign_date_range(start, end)
    (
        _config,
        config_error,
        definitions,
        list_error,
        definition,
        definition_error,
    ) = load_campaign_configuration(
        month,
        promotion_key=promotion_key,
        config_loader=config_loader,
        definitions_loader=definitions_loader,
        definition_loader=definition_loader,
    )
    return CampaignRequest(
        start=start,
        end=end,
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        config_error=config_error,
        promotion_definitions=definitions,
        promotion_list_error=list_error,
        promotion_definition=definition,
        promotion_error=definition_error or list_error,
        include_incentive=view != "promo",
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )


__all__ = [
    "CampaignRequest",
    "build_campaign_request",
    "parse_campaign_dates",
]
