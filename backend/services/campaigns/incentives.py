"""Incentive normalization and pure response projection for Campaigns."""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(slots=True)
class _IncentiveState:
    status: Any
    warnings: list[str]
    qty: Any
    value: Decimal | None
    qualified_qty: Any
    qualified_stores: Any
    qualified_stores_full: Any
    qualified_stores_half: Any
    qualified_agents: Any
    qualified_agents_full: Any
    qualified_agents_half: Any
    sold_qty: int = 0
    potential: Decimal | None = Decimal("0")
    product_count: int = 0
    categories: list[IncentiveCategory] = field(default_factory=list)
    periods: list[IncentivePeriodStat] = field(default_factory=list)
    category_breakdown: list[IncentiveCategoryBreakdown] = field(
        default_factory=list
    )
    top_agents: list[IncentiveTopAgent] = field(default_factory=list)
    top_stores: list[PromoTopStore] = field(default_factory=list)


@dataclass(slots=True)
class _IncentiveAccumulator:
    store_incentives: dict[str, list[Any]] = field(default_factory=dict)
    store_eligible_by_item: dict[tuple[str, str, str, str], int] = field(
        default_factory=dict
    )
    store_reward_by_item: dict[tuple[str, str, str, str], Decimal] = field(
        default_factory=dict
    )
    period_totals: dict[tuple[str, str], list[Any]] = field(default_factory=dict)
    category_totals: dict[str, list[Any]] = field(default_factory=dict)
    tier_totals: dict[str, list[Any]] = field(default_factory=dict)
    sold_qty: int = 0
    qty: int = 0
    value: Decimal = Decimal("0")
    potential: Decimal = Decimal("0")
    qualified_qty: int = 0


def _initial_incentive_state(
    snapshot: CampaignResponseSnapshot,
    promotion: PromotionProjection,
) -> _IncentiveState:
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
        qty = summary.incentive_qty
        value = (
            money(summary.incentive_value)
            if summary.incentive_value is not None
            else None
        )
        counters = (
            summary.incentive_qualified_qty,
            summary.incentive_qualified_stores,
            summary.incentive_qualified_stores_full,
            summary.incentive_qualified_stores_half,
            summary.incentive_qualified_agents,
            summary.incentive_qualified_agents_full,
            summary.incentive_qualified_agents_half,
        )
        if summary.calculation_status == "invalid":
            status = "invalid"
            warnings.extend(summary.calculation_warnings)
    else:
        qty, value = 0, Decimal("0")
        counters = (0, 0, 0, 0, 0, 0, 0)
    if promotion.invalidates_incentive:
        status = "invalid"
    warnings.extend(promotion.warnings)
    return _IncentiveState(
        status=status,
        warnings=warnings,
        qty=qty,
        value=value,
        qualified_qty=counters[0],
        qualified_stores=counters[1],
        qualified_stores_full=counters[2],
        qualified_stores_half=counters[3],
        qualified_agents=counters[4],
        qualified_agents_full=counters[5],
        qualified_agents_half=counters[6],
        top_stores=list(promotion.top_stores),
    )


def _incentive_period_bounds(
    row: Any,
    campaign_periods: list[dict[str, Any]],
) -> tuple[str, str]:
    row_start = row.get("valid_from") or campaign_periods[0]["valid_from"]
    row_end = row.get("valid_to") or campaign_periods[0]["valid_to"]
    return row_start.isoformat(), row_end.isoformat()


def _incentive_reward(row: Any, campaign: dict[str, Any]) -> Decimal:
    return money(
        row.get("reward_value")
        or campaign.get("reward_map", {}).get(row["item_code"], 0)
    )


def _accumulate_incentive_store_row(
    accumulator: _IncentiveAccumulator,
    *,
    snapshot: CampaignResponseSnapshot,
    campaign: dict[str, Any],
    campaign_periods: list[dict[str, Any]],
    excluded_by_site: dict[tuple[str, str, str, str], int],
    row: Any,
) -> None:
    site_code = str(row["site_code"])
    period_start, period_end = _incentive_period_bounds(row, campaign_periods)
    reward = _incentive_reward(row, campaign)
    item_code = str(row["item_code"])
    item_key = (period_start, period_end, site_code, item_code)
    raw_qty = int(row["qty"] or 0)
    excluded = excluded_by_site.get(item_key, 0)
    eligible_qty = max(0, raw_qty - excluded)
    accumulator.sold_qty += raw_qty
    accumulator.store_eligible_by_item[item_key] = eligible_qty
    accumulator.store_reward_by_item[item_key] = reward
    item_potential = money(eligible_qty * reward)
    multiplier = Decimal(str(snapshot.store_multipliers.get(site_code, 0)))
    item_value = money(item_potential * multiplier)
    accumulator.qty += eligible_qty
    accumulator.potential += item_potential
    accumulator.value += item_value
    achievement = snapshot.store_achievements.get(site_code) or 0
    if achievement >= 0.9:
        accumulator.qualified_qty += eligible_qty

    store = accumulator.store_incentives.setdefault(
        site_code,
        [row["locatie"], Decimal("0"), row["firma"] or "", 0, Decimal("0")],
    )
    store[1] += item_value
    store[3] += eligible_qty
    store[4] += item_potential
    period_total = accumulator.period_totals.setdefault(
        (period_start, period_end),
        [0, Decimal("0"), Decimal("0")],
    )
    period_total[0] += eligible_qty
    period_total[1] += item_potential
    period_total[2] += item_value

    category = str(
        row.get("subcategory") or row.get("category") or "Necategorizat"
    )
    category_total = accumulator.category_totals.setdefault(
        category,
        [0, Decimal("0"), Decimal("0"), 0],
    )
    category_total[0] += eligible_qty
    category_total[1] += item_potential
    category_total[2] += item_value
    if achievement >= 0.9:
        category_total[3] += eligible_qty
    tier_label = f"{int(reward)} RON" if reward == int(reward) else f"{reward} RON"
    tier_total = accumulator.tier_totals.setdefault(
        tier_label,
        [0, Decimal("0")],
    )
    tier_total[0] += eligible_qty
    tier_total[1] += item_potential


def _build_incentive_accumulator(
    snapshot: CampaignResponseSnapshot,
    campaign: dict[str, Any],
    campaign_periods: list[dict[str, Any]],
    excluded_by_site: dict[tuple[str, str, str, str], int],
) -> _IncentiveAccumulator:
    accumulator = _IncentiveAccumulator()
    for row in snapshot.incentive_store_rows:
        _accumulate_incentive_store_row(
            accumulator,
            snapshot=snapshot,
            campaign=campaign,
            campaign_periods=campaign_periods,
            excluded_by_site=excluded_by_site,
            row=row,
        )
    return accumulator


def _incentive_top_stores(
    snapshot: CampaignResponseSnapshot,
    promotion: PromotionProjection,
    accumulator: _IncentiveAccumulator,
) -> list[PromoTopStore]:
    if not promotion.has_active:
        return [
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
            for site_code, data in accumulator.store_incentives.items()
        ]
    rows: list[PromoTopStore] = []
    for store in promotion.top_stores:
        site_code = store.store_name.split(" - ")[0]
        data = accumulator.store_incentives.get(
            site_code,
            [None, Decimal("0"), "", 0, Decimal("0")],
        )
        rows.append(
            PromoTopStore(
                store_name=store.store_name,
                qty=int(data[3]),
                total_qty=store.total_qty,
                category_qty=store.category_qty,
                promo_bons=store.promo_bons,
                incentive_value=money_float(data[1]),
                incentive_potential=money_float(data[4]),
                achievement=store.achievement,
                firma=store.firma,
            )
        )
    return rows


def _incentive_period_stats(
    campaign_periods: list[dict[str, Any]],
    period_totals: dict[tuple[str, str], list[Any]],
) -> list[IncentivePeriodStat]:
    rows: list[IncentivePeriodStat] = []
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
        rows.append(
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
    return rows


def _incentive_category_outputs(
    accumulator: _IncentiveAccumulator,
) -> tuple[list[IncentiveCategoryBreakdown], list[IncentiveCategory]]:
    breakdown = sorted(
        [
            IncentiveCategoryBreakdown(
                label=label,
                qty=int(values[0]),
                qualified_qty=int(values[3]),
                potential=money_float(values[1]),
                value=money_float(values[2]),
            )
            for label, values in accumulator.category_totals.items()
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
            for label, values in accumulator.tier_totals.items()
        ],
        key=lambda item: -item.value,
    )
    return breakdown, categories


def _apply_campaign_incentive(
    snapshot: CampaignResponseSnapshot,
    promotion: PromotionProjection,
    state: _IncentiveState,
) -> None:
    campaign = snapshot.incentive_campaign
    if campaign is None:
        return
    campaign_periods = snapshot.incentive_periods
    codes = incentive_item_codes(campaign)
    state.product_count = len(codes)
    excluded_by_agent, exclusion_warnings, exclusions_complete = period_exclusions(
        snapshot,
        promotion.incentive_excluded_units,
    )
    state.warnings.extend(exclusion_warnings)
    if not exclusions_complete:
        state.status = "invalid"
    if not codes:
        return
    accumulator = _build_incentive_accumulator(
        snapshot,
        campaign,
        campaign_periods,
        excluded_by_period_site_item(excluded_by_agent),
    )
    state.sold_qty = accumulator.sold_qty
    state.qty = accumulator.qty
    state.value = accumulator.value
    state.potential = accumulator.potential
    state.qualified_qty = accumulator.qualified_qty
    state.top_stores = _incentive_top_stores(snapshot, promotion, accumulator)
    state.periods = _incentive_period_stats(
        campaign_periods,
        accumulator.period_totals,
    )
    state.category_breakdown, state.categories = _incentive_category_outputs(
        accumulator
    )
    state.top_agents = build_incentive_agent_rows(
        snapshot=snapshot,
        campaign=campaign,
        campaign_periods=campaign_periods,
        period_excluded_agent=excluded_by_agent,
        store_eligible_by_item=accumulator.store_eligible_by_item,
        store_reward_by_item=accumulator.store_reward_by_item,
        store_incentives=accumulator.store_incentives,
    )


def _invalidate_incentive_state(state: _IncentiveState) -> None:
    if state.status != "invalid":
        return
    state.qty = None
    state.value = None
    state.potential = None
    state.qualified_qty = None
    state.top_agents = []
    state.categories = []
    state.periods = []
    state.category_breakdown = []
    state.top_stores = []


def project_incentive(
    snapshot: CampaignResponseSnapshot,
    promotion: PromotionProjection,
) -> IncentiveProjection:
    campaign = snapshot.incentive_campaign
    state = _initial_incentive_state(snapshot, promotion)
    _apply_campaign_incentive(snapshot, promotion, state)
    _invalidate_incentive_state(state)
    return IncentiveProjection(
        title=campaign["title"] if campaign else "",
        description=campaign["description"] if campaign else "",
        calculation_status=state.status,
        warnings=list(dict.fromkeys(state.warnings)),
        qty=state.qty,
        sold_qty=state.sold_qty,
        value=state.value,
        potential=state.potential,
        qualified_qty=state.qualified_qty,
        qualified_stores=state.qualified_stores,
        qualified_stores_full=state.qualified_stores_full,
        qualified_stores_half=state.qualified_stores_half,
        qualified_agents=state.qualified_agents,
        qualified_agents_full=state.qualified_agents_full,
        qualified_agents_half=state.qualified_agents_half,
        product_count=state.product_count,
        categories=state.categories,
        periods=state.periods,
        category_breakdown=state.category_breakdown,
        top_stores=state.top_stores,
        top_agents=state.top_agents,
    )
