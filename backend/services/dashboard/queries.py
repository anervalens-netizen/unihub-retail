"""Compatibility exports for typed Dashboard query modules."""
from typing import Any

from repositories.dashboard_cutoffs import (
    fetch_period_comparison_cutoff_day as _fetch_period_comparison_cutoff_day,
)
from services.dashboard import query_agents, query_managers, query_stores
from services.dashboard.query_agents import _fetch_agent_stats_rows as _agent_rows_impl
from services.dashboard.query_common import (
    apply_current_promo_metrics,
    _scope_clauses,
    _scope_join,
    _store_field,
)
from services.dashboard.query_comparison import (
    _fetch_daily_last_year_for_current_cohort,
    _fetch_period_comparison,
)
from services.dashboard.query_managers import (
    _fetch_asm_stats as _asm_stats_impl,
    _fetch_regional_stats as _regional_stats_impl,
)
from services.dashboard.query_mix import (
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_focus_subcategory_mix,
    _fetch_receipt_bucket_mix,
)
from services.dashboard.query_stores import (
    _enrich_store_stats_with_campaign as _enrich_store_stats_impl,
    _fetch_store_stats_rows,
)
from services.dashboard_specials import load_special_cards_config, parse_promotion_definition
from services.incentive_db import get_incentive_campaign


def _sync_campaign_ports(module: Any) -> None:
    """Keep the historical monkeypatch boundary while queries live by domain."""
    module.get_incentive_campaign = get_incentive_campaign
    module.load_special_cards_config = load_special_cards_config
    module.parse_promotion_definition = parse_promotion_definition


async def _fetch_agent_stats_rows(*args: Any, **kwargs: Any) -> list[Any]:
    _sync_campaign_ports(query_agents)
    return await _agent_rows_impl(*args, **kwargs)


async def _enrich_store_stats_with_campaign(*args: Any, **kwargs: Any) -> list[Any]:
    _sync_campaign_ports(query_stores)
    return await _enrich_store_stats_impl(*args, **kwargs)


async def _fetch_regional_stats(*args: Any, **kwargs: Any) -> list[Any]:
    _sync_campaign_ports(query_managers)
    return await _regional_stats_impl(*args, **kwargs)


async def _fetch_asm_stats(*args: Any, **kwargs: Any) -> list[Any]:
    _sync_campaign_ports(query_managers)
    return await _asm_stats_impl(*args, **kwargs)

__all__ = [
    "apply_current_promo_metrics",
    "_fetch_agent_stats_rows",
    "_fetch_asm_stats",
    "_fetch_brand_mix",
    "_fetch_category_mix",
    "_fetch_daily_last_year_for_current_cohort",
    "_fetch_focus_subcategory_mix",
    "_fetch_period_comparison",
    "_fetch_period_comparison_cutoff_day",
    "_fetch_receipt_bucket_mix",
    "_fetch_regional_stats",
    "_fetch_store_stats_rows",
]
