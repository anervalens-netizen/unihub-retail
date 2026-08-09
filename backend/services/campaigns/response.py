"""Stable response mapping for Campaigns."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from schemas.campaigns import (
    CampaignOverview,
    CampaignProductStat,
    CampaignSnapshot,
    CampaignStoreStat,
    FocusHistoryPoint,
    FocusHistoryResponse,
)
from services.campaigns.contracts import CampaignResponseSnapshot
from services.campaigns.money import money_float
from services.campaigns.status import calculation_status


def map_campaign_overview(
    month: str,
    data: dict[str, Any],
) -> CampaignSnapshot:
    overview = (
        CampaignOverview(**dict(data["overview"]))
        if data["overview"]
        else CampaignOverview(
            month=month,
            total_focus_sales=Decimal(0),
            total_focus_qty=0,
            focus_share_pct=None,
            active_focus_products=0,
            active_focus_stores=0,
        )
    )
    return CampaignSnapshot(
        overview=overview,
        products=[
            CampaignProductStat(**dict(row))
            for row in data["products"]
        ],
        stores=[
            CampaignStoreStat(**dict(row))
            for row in data["stores"]
        ],
    )


def map_focus_history(rows: list[Any]) -> FocusHistoryResponse:
    return FocusHistoryResponse(
        history=[FocusHistoryPoint(**dict(row)) for row in rows]
    )


def build_promotions_incentives_response(
    snapshot: CampaignResponseSnapshot,
) -> dict[str, Any]:
    # Local imports keep the mapping boundary independent of evaluator modules.
    from services.campaigns.incentives import project_incentive
    from services.campaigns.promotions import (
        project_promotion,
        promotion_options,
    )

    promotion = project_promotion(snapshot)
    incentive = project_incentive(snapshot, promotion)
    definition = snapshot.promotion_definition
    return {
        "promotions": promotion_options(snapshot.promotion_definitions),
        "selected_promotion_key": (
            definition.get("key", "") if definition else ""
        ),
        "promo_title": promotion.title,
        "promo_description": promotion.error or promotion.description,
        "promo_total_qty": promotion.total_qty,
        "promo_qty": promotion.qty,
        "promo_category_qty": None,
        "promo_impact": money_float(promotion.impact),
        "promo_qualifying_bons": promotion.qualifying_bons,
        "promo_discounted_units": promotion.discounted_units,
        "promo_discount_value": promotion.discount_value,
        "promo_active_stores": promotion.active_stores,
        "promo_active_agents": promotion.active_agents,
        "has_active_promotion": promotion.has_active,
        "promo_calculation_status": promotion.calculation_status,
        "incentive_calculation_status": incentive.calculation_status,
        "calculation_warnings": incentive.warnings,
        "top_stores": incentive.top_stores,
        "promo_agents": promotion.promo_agents,
        "top_agents": incentive.top_agents,
        "incentive_title": incentive.title,
        "incentive_description": incentive.description,
        "incentive_qty": incentive.qty,
        "incentive_sold_qty": incentive.sold_qty,
        "incentive_value": (
            money_float(incentive.value)
            if incentive.value is not None
            else None
        ),
        "incentive_potential": (
            money_float(incentive.potential)
            if incentive.potential is not None
            else None
        ),
        "incentive_qualified_qty": incentive.qualified_qty,
        "incentive_qualified_stores": incentive.qualified_stores,
        "incentive_qualified_stores_full": incentive.qualified_stores_full,
        "incentive_qualified_stores_half": incentive.qualified_stores_half,
        "incentive_qualified_agents": incentive.qualified_agents,
        "incentive_qualified_agents_full": incentive.qualified_agents_full,
        "incentive_qualified_agents_half": incentive.qualified_agents_half,
        "incentive_product_count": incentive.product_count,
        "incentive_categories": incentive.categories,
        "incentive_periods": incentive.periods,
        "incentive_category_breakdown": incentive.category_breakdown,
    }
