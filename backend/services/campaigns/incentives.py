"""Incentive normalization and pure response projection for Campaigns."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from schemas.campaigns import (
    IncentiveCategory,
    IncentiveCategoryBreakdown,
    IncentivePeriodStat,
    IncentiveTopAgent,
    PromoTopStore,
)
from services.campaigns.aggregation import (
    build_incentive_agent_rows,
    excluded_by_period_site_item,
    period_exclusions,
)
from services.campaigns.contracts import (
    CampaignResponseSnapshot,
    IncentiveProjection,
    PromotionProjection,
)
from services.campaigns.money import money, money_float
from services.campaigns.status import calculation_status
from services.promotion_evaluation import PromotionEvaluationStatus


def incentive_item_codes(campaign: dict[str, Any] | None) -> list[str]:
    if campaign is None:
        return []
    codes = [
        str(product["item_code"])
        for period in campaign.get("periods", [])
        for product in period.get("products", [])
    ]
    if codes:
        return sorted(set(codes))
    return sorted(
        {
            str(code)
            for code in campaign.get("item_codes")
            or campaign.get("reward_map", {}).keys()
        }
    )


def normalized_incentive_periods(
    campaign: dict[str, Any] | None,
    *,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    if campaign is None:
        return []
    periods = list(campaign.get("periods") or [])
    if not periods and campaign.get("reward_map"):
        periods = [
            {
                "valid_from": start,
                "valid_to": end,
                "products": [
                    {"item_code": code, "reward_value": reward}
                    for code, reward in campaign["reward_map"].items()
                ],
            }
        ]
    return periods


def project_incentive(
    snapshot: CampaignResponseSnapshot,
    promotion: PromotionProjection,
) -> IncentiveProjection:
    campaign = snapshot.incentive_campaign
    summary = snapshot.summary
    status = calculation_status(configured=campaign is not None, error=None)
    warnings: list[str] = []

    if campaign is not None and snapshot.promotion_list_error is not None:
        status = "invalid"
        warnings.append(
            "Incentive indisponibil: lista promotiilor active nu poate fi validata."
        )
    if (
        campaign is not None
        and snapshot.campaign_context.promotion_status
        is not PromotionEvaluationStatus.COMPLETE
    ):
        status = "invalid"
        warnings.extend(snapshot.campaign_context.promotion_warnings)

    if snapshot.include_incentive and summary is not None:
        qty: int | None = summary.incentive_qty
        value: Decimal | None = (
            money(summary.incentive_value)
            if summary.incentive_value is not None
            else None
        )
        qualified_qty: int | None = summary.incentive_qualified_qty
        qualified_stores = summary.incentive_qualified_stores
        qualified_stores_full = summary.incentive_qualified_stores_full
        qualified_stores_half = summary.incentive_qualified_stores_half
        qualified_agents = summary.incentive_qualified_agents
        qualified_agents_full = summary.incentive_qualified_agents_full
        qualified_agents_half = summary.incentive_qualified_agents_half
        if summary.calculation_status == "invalid":
            status = "invalid"
            warnings.extend(summary.calculation_warnings)
    else:
        qty = 0
        value = Decimal("0")
        qualified_qty = 0
        qualified_stores = 0
        qualified_stores_full = 0
        qualified_stores_half = 0
        qualified_agents = 0
        qualified_agents_full = 0
        qualified_agents_half = 0

    if promotion.invalidates_incentive:
        status = "invalid"
    warnings.extend(promotion.warnings)

    sold_qty = 0
    potential: Decimal | None = Decimal("0")
    product_count = 0
    categories: list[IncentiveCategory] = []
    periods: list[IncentivePeriodStat] = []
    category_breakdown: list[IncentiveCategoryBreakdown] = []
    top_agents: list[IncentiveTopAgent] = []
    top_stores = list(promotion.top_stores)

    if campaign is not None:
        campaign_periods = snapshot.incentive_periods
        codes = incentive_item_codes(campaign)
        product_count = len(codes)
        period_excluded_agent, period_warnings, exclusions_complete = (
            period_exclusions(
                snapshot,
                promotion.incentive_excluded_units,
            )
        )
        warnings.extend(period_warnings)
        if not exclusions_complete:
            status = "invalid"
        period_excluded_site = excluded_by_period_site_item(
            period_excluded_agent
        )

        if codes:
            store_inc: dict[str, list[Any]] = {}
            store_eligible_by_item: dict[
                tuple[str, str, str, str], int
            ] = {}
            store_reward_by_item: dict[
                tuple[str, str, str, str], Decimal
            ] = {}
            period_totals: dict[tuple[str, str], list[Any]] = {}
            category_totals: dict[str, list[Any]] = {}
            tier_totals: dict[str, list[Any]] = {}
            sold_qty = 0
            qty = 0
            value = Decimal("0")
            potential = Decimal("0")
            qualified_qty = 0

            for row in snapshot.incentive_store_rows:
                site_code = str(row["site_code"])
                row_start = (
                    row.get("valid_from")
                    or campaign_periods[0]["valid_from"]
                )
                row_end = (
                    row.get("valid_to")
                    or campaign_periods[0]["valid_to"]
                )
                period_start = row_start.isoformat()
                period_end = row_end.isoformat()
                reward = money(
                    row.get("reward_value")
                    or campaign.get("reward_map", {}).get(
                        row["item_code"],
                        0,
                    )
                )
                item_code = str(row["item_code"])
                excluded = period_excluded_site.get(
                    (period_start, period_end, site_code, item_code),
                    0,
                )
                raw_qty = int(row["qty"] or 0)
                sold_qty += raw_qty
                eligible_qty = max(0, raw_qty - excluded)
                item_key = (
                    period_start,
                    period_end,
                    site_code,
                    item_code,
                )
                store_eligible_by_item[item_key] = eligible_qty
                store_reward_by_item[item_key] = reward
                item_potential = money(eligible_qty * reward)
                item_value = money(
                    item_potential
                    * Decimal(
                        str(snapshot.store_multipliers.get(site_code, 0))
                    )
                )
                qty += eligible_qty
                potential += item_potential
                value += item_value
                achievement = snapshot.store_achievements.get(site_code) or 0
                if achievement >= 0.9:
                    qualified_qty += eligible_qty

                store = store_inc.setdefault(
                    site_code,
                    [
                        row["locatie"],
                        Decimal("0"),
                        row["firma"] or "",
                        0,
                        Decimal("0"),
                    ],
                )
                store[1] += item_value
                store[3] += eligible_qty
                store[4] += item_potential

                period_total = period_totals.setdefault(
                    (period_start, period_end),
                    [0, Decimal("0"), Decimal("0")],
                )
                period_total[0] += eligible_qty
                period_total[1] += item_potential
                period_total[2] += item_value

                category = str(
                    row.get("subcategory")
                    or row.get("category")
                    or "Necategorizat"
                )
                category_total = category_totals.setdefault(
                    category,
                    [0, Decimal("0"), Decimal("0"), 0],
                )
                category_total[0] += eligible_qty
                category_total[1] += item_potential
                category_total[2] += item_value
                if achievement >= 0.9:
                    category_total[3] += eligible_qty

                tier_label = (
                    f"{int(reward)} RON"
                    if reward == int(reward)
                    else f"{reward} RON"
                )
                tier_total = tier_totals.setdefault(
                    tier_label,
                    [0, Decimal("0")],
                )
                tier_total[0] += eligible_qty
                tier_total[1] += item_potential

            if promotion.has_active:
                top_stores = [
                    PromoTopStore(
                        store_name=store.store_name,
                        qty=int(
                            store_inc.get(
                                store.store_name.split(" - ")[0],
                                [None, Decimal("0"), "", 0],
                            )[3]
                        ),
                        total_qty=store.total_qty,
                        category_qty=store.category_qty,
                        promo_bons=store.promo_bons,
                        incentive_value=money_float(
                            store_inc.get(
                                store.store_name.split(" - ")[0],
                                [None, Decimal("0")],
                            )[1]
                        ),
                        incentive_potential=money_float(
                            store_inc.get(
                                store.store_name.split(" - ")[0],
                                [None, Decimal("0"), "", 0, Decimal("0")],
                            )[4]
                        ),
                        achievement=store.achievement,
                        firma=store.firma,
                    )
                    for store in top_stores
                ]
            else:
                top_stores = [
                    PromoTopStore(
                        store_name=f"{site_code} - {data[0]}",
                        qty=int(data[3]),
                        total_qty=0,
                        category_qty=0,
                        promo_bons=0,
                        incentive_value=money_float(data[1]),
                        incentive_potential=money_float(data[4]),
                        achievement=snapshot.store_achievements.get(site_code),
                        firma=str(data[2]),
                    )
                    for site_code, data in store_inc.items()
                ]

            for index, period in enumerate(campaign_periods):
                period_start = period["valid_from"].isoformat()
                period_end = period["valid_to"].isoformat()
                totals = period_totals.get(
                    (period_start, period_end),
                    [0, Decimal("0"), Decimal("0")],
                )
                if len(campaign_periods) == 1:
                    label = "Mecanism lunar"
                elif index == len(campaign_periods) - 1:
                    label = "Mecanism actualizat"
                else:
                    label = "Mecanism initial"
                periods.append(
                    IncentivePeriodStat(
                        label=label,
                        start_date=period_start,
                        end_date=period_end,
                        product_count=len(period["products"]),
                        reward_values=sorted(
                            {
                                money_float(product["reward_value"])
                                for product in period["products"]
                            }
                        ),
                        qty=int(totals[0]),
                        potential=money_float(totals[1]),
                        value=money_float(totals[2]),
                    )
                )

            category_breakdown = sorted(
                [
                    IncentiveCategoryBreakdown(
                        label=label,
                        qty=int(values[0]),
                        qualified_qty=int(values[3]),
                        potential=money_float(values[1]),
                        value=money_float(values[2]),
                    )
                    for label, values in category_totals.items()
                    if values[0] > 0
                ],
                key=lambda item: (-item.qty, item.label),
            )
            categories = sorted(
                [
                    IncentiveCategory(
                        label=label,
                        qty=int(values[0]),
                        value=money_float(values[1]),
                    )
                    for label, values in tier_totals.items()
                ],
                key=lambda item: -item.value,
            )

            top_agents = build_incentive_agent_rows(
                snapshot=snapshot,
                campaign=campaign,
                campaign_periods=campaign_periods,
                period_excluded_agent=period_excluded_agent,
                store_eligible_by_item=store_eligible_by_item,
                store_reward_by_item=store_reward_by_item,
                store_incentives=store_inc,
            )

    if status == "invalid":
        qty = None
        value = None
        potential = None
        qualified_qty = None
        top_agents = []
        categories = []
        periods = []
        category_breakdown = []
        top_stores = []

    return IncentiveProjection(
        title=campaign["title"] if campaign else "",
        description=campaign["description"] if campaign else "",
        calculation_status=status,
        warnings=list(dict.fromkeys(warnings)),
        qty=qty,
        sold_qty=sold_qty,
        value=value,
        potential=potential,
        qualified_qty=qualified_qty,
        qualified_stores=qualified_stores,
        qualified_stores_full=qualified_stores_full,
        qualified_stores_half=qualified_stores_half,
        qualified_agents=qualified_agents,
        qualified_agents_full=qualified_agents_full,
        qualified_agents_half=qualified_agents_half,
        product_count=product_count,
        categories=categories,
        periods=periods,
        category_breakdown=category_breakdown,
        top_stores=top_stores,
        top_agents=top_agents,
    )
