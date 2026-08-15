"""Heavy lifting for dashboard: stats + mix + period comparison + promo/incentive summary."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from repositories.dashboard_cutoffs import (
    fetch_period_comparison_cutoff_day as _fetch_period_comparison_cutoff_day,
    resolve_period_comparison_cutoff_day,
)
from schemas.dashboard import (
    BrandMixItem,
    CategoryMixItem,
    PeriodComparisonPayload,
    PeriodComparisonPoint,
    ReceiptBucketItem,
)
from services.campaigns import CampaignContext
from services.dashboard.utils import (
    _expand_current_manager_scope,
    _month_day_range,
    _shift_month,
)
from services.dashboard_specials import load_special_cards_config, parse_promotion_definition
from services.filters import FilterInput, build_scoped_params, scoped_clauses
from services.forecast import business_forecast_factor_ctes
from services.incentive_db import get_incentive_campaign
from services.receipt_identity import canonical_receipt_identity_sql


def apply_current_promo_metrics(
    rows: list[dict[str, Any]],
    campaign_context: CampaignContext,
    *,
    level: Literal["agent", "store", "regional"],
    site_regionals: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach official promo units and discount value to dashboard rows."""
    qty_by_key: dict[Any, int] = {}
    value_by_key: dict[Any, Decimal] = {}

    for (site, agent_name, item), units in campaign_context.promo_excluded_units.items():
        if level == "agent":
            key: Any = (site, agent_name)
        elif level == "store":
            key = site
        else:
            key = (site_regionals or {}).get(site)
            if key is None:
                continue
        qty_by_key[key] = qty_by_key.get(key, 0) + units
        value_key = (site, agent_name, item)
        value_by_key[key] = (
            value_by_key.get(key, Decimal("0"))
            + campaign_context.promo_discount_values.get(value_key, Decimal("0"))
        )

    for row in rows:
        if level == "agent":
            row_key: Any = (str(row["site_code"]), str(row["agent"]))
        elif level == "store":
            row_key = str(row["site_code"])
        else:
            row_key = str(row["regional"])
        row["promo_qty"] = qty_by_key.get(row_key, 0)
        row["promo_discount_value"] = value_by_key.get(row_key, Decimal("0"))
    return rows


def _scope_join(current_scope: bool, source_alias: str = "agg") -> str:
    return f"JOIN stores s ON s.site_code = {source_alias}.site_code" if current_scope else ""


def _scope_clauses(
    positions: dict[str, int],
    *,
    current_scope: bool,
    include_closed_stores: bool,
    source_alias: str = "agg",
    month_alias: str | None = None,
    month_position: int | None = None,
) -> list[str]:
    clauses = scoped_clauses(
        positions,
        site_alias=source_alias,
        store_alias="s" if current_scope else source_alias,
        agent_alias=source_alias,
        month_alias=month_alias,
        month_position=month_position,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    return clauses


def _store_field(field: str, current_scope: bool, source_alias: str = "agg") -> str:
    return f"s.{field}" if current_scope else f"{source_alias}.{field}"


