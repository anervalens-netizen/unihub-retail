"""Canonical Promo/Incentive summary and multiplier queries."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from business_rules import PROMOTION_DISCOUNT_RATE
from domain.filter_scope import FilterInput
from schemas.campaigns import PromoIncentiveSummary
from services.campaigns.contracts import CampaignContext
from services.campaigns.context import load_campaign_context
from services.campaigns.promotions import compute_promotion_result
from services.campaigns.scope import campaign_scope_clauses, campaign_scope_join
from services.dashboard_specials import incentive_multiplier
from services.filters import build_scoped_params
from services.forecast import get_forecast_factor
from services.promotion_evaluation import (
    PromotionEvaluationStatus,
    scope_promotion_definition_to_interval,
)


async def get_store_incentive_multipliers(
    conn: Any,
    month: str,
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    cutoff_date: date | None = None,
) -> tuple[dict[str, float], dict[str, float | None]]:
    """Return incentive multipliers and target achievement by site code."""
    base_params: list[Any] = [month]
    if cutoff_date is not None:
        base_params.append(cutoff_date)
    params, positions = build_scoped_params(
        base_params,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=None,
    )
    clauses = ["ram.import_month = $1"]
    if cutoff_date is not None:
        clauses.append("ram.sale_date <= $2")
    clauses.extend(
        campaign_scope_clauses(
            positions,
            source_alias="ram",
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            month_alias="ram.import_month",
            month_position=1,
        )
    )
    forecast_factor = await get_forecast_factor(
        conn,
        month,
        cutoff_date=cutoff_date,
    )
    source_table = (
        "reporting_agent_day" if cutoff_date is not None else "reporting_agent_month"
    )
    rows = await conn.fetch(
        f"""
        SELECT
            ram.site_code,
            COALESCE(SUM(ram.total_sales), 0) AS store_sales,
            COALESCE(MAX(st.target_value), 0) AS target
        FROM {source_table} ram
        {campaign_scope_join(current_scope, "ram")}
        LEFT JOIN store_targets st
          ON st.site_code = ram.site_code AND st.import_month = $1
        WHERE {" AND ".join(clauses)}
        GROUP BY ram.site_code
        """,
        *params,
    )
    multipliers: dict[str, float] = {}
    achievements: dict[str, float | None] = {}
    for row in rows:
        site = str(row["site_code"])
        target = float(row["target"] or 0)
        sales = float(row["store_sales"] or 0) * forecast_factor
        achievement = sales / target if target > 0 else None
        achievements[site] = achievement
        multipliers[site] = incentive_multiplier(achievement or 0.0)
    return multipliers, achievements


async def _promotion_totals(
    scope: dict[str, Any], context: CampaignContext,
) -> tuple[int, Decimal, Decimal]:
    selected = context.selected_promotion_result
    promo_qty = selected.discounted_units if selected is not None else 0
    promo_impact = selected.discount_value if selected is not None else Decimal("0")
    definition = context.promotion_definition
    if definition is None or context.promotion_error is not None:
        return promo_qty, Decimal("0"), promo_impact
    params, positions = build_scoped_params(
        [scope["month"], definition["start_date"], definition["end_date"], definition["item_codes"]],
        firma=scope["firma"], regional=scope["regional"], asm=scope["asm"],
        site_code=scope["site_code"], agent=scope["agent"],
    )
    clauses = [
        "agg.import_month = $1", "agg.sale_date BETWEEN $2 AND $3", "agg.item_code = ANY($4::TEXT[])",
        *campaign_scope_clauses(
            positions, current_scope=scope["current_scope"],
            include_closed_stores=scope["include_closed_stores"],
        ),
    ]
    row = await scope["conn"].fetchrow(
        f"""
        SELECT COALESCE(SUM(agg.positive_quantity), 0) AS promo_qty,
               COALESCE(SUM(agg.total_sales), 0) AS promo_sales
        FROM reporting_item_day agg
        {campaign_scope_join(scope["current_scope"])}
        WHERE {" AND ".join(clauses)}
        """,
        *params,
    )
    if row and not (promo_qty > 0 or bool(context.promo_excluded_units)):
        promo_qty = int(row["promo_qty"] or 0)
    return promo_qty, (row["promo_sales"] or Decimal("0")) if row else Decimal("0"), promo_impact


def _incentive_periods(
    month: str, campaign: dict[str, Any], cutoff_date: date | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    periods = campaign.get("periods") or []
    if cutoff_date is not None:
        periods = [
            {**period, "valid_to": min(period["valid_to"], cutoff_date)}
            for period in periods if period["valid_from"] <= cutoff_date
        ]
    codes = campaign.get("item_codes") or list(campaign.get("reward_map", {}).keys())
    if not periods and codes:
        year, month_number = (int(value) for value in month.split("-", 1))
        month_start = date(year, month_number, 1)
        month_end = date(
            year + (month_number == 12), 1 if month_number == 12 else month_number + 1, 1,
        ) - timedelta(days=1)
        periods = [{"valid_from": month_start, "valid_to": min(month_end, cutoff_date or month_end)}]
    return periods, codes


def _site_item_exclusions(context: CampaignContext) -> dict[tuple[str, str], int]:
    result: dict[tuple[str, str], int] = {}
    for (site, _agent, item), units in context.promo_excluded_units.items():
        result[(site, item)] = result.get((site, item), 0) + units
    return result


async def _period_exclusions(
    scope: dict[str, Any],
    context: CampaignContext,
    periods: list[dict[str, Any]],
    complete: bool,
    warnings: list[str],
) -> tuple[dict[tuple[str, str, str, str], int], bool]:
    exclusions: dict[tuple[str, str, str, str], int] = {}
    site_item = _site_item_exclusions(context)
    if len(periods) <= 1:
        if periods:
            start, end = periods[0]["valid_from"].isoformat(), periods[0]["valid_to"].isoformat()
            exclusions.update({(start, end, site, item): units for (site, item), units in site_item.items()})
        return exclusions, complete
    for period in periods:
        for definition in context.promotion_definitions:
            range_start = max(period["valid_from"], definition["start_date"])
            range_end = min(period["valid_to"], definition["end_date"])
            if range_start > range_end:
                continue
            key = context.period_evaluation_key(definition, range_start, range_end)
            evaluation = context.period_evaluations.get(key)
            if evaluation is None:
                evaluation = await compute_promotion_result(
                    scope["conn"], month=scope["month"],
                    definition=scope_promotion_definition_to_interval(definition, range_start, range_end),
                    firma=scope["firma"], regional=scope["regional"], asm=scope["asm"],
                    site_code=scope["site_code"], agent=scope["agent"],
                    current_scope=scope["current_scope"],
                    include_closed_stores=scope["include_closed_stores"],
                )
                context.period_evaluations[key] = evaluation
            if not evaluation.is_complete:
                complete = False
                warnings.append(evaluation.warning or "Excluderile promo nu pot fi alocate complet pe perioade.")
            if not evaluation.is_complete or evaluation.result is None:
                continue
            for (site, _agent, item), units in evaluation.result.excluded_units.items():
                exclusion_key = (
                    period["valid_from"].isoformat(), period["valid_to"].isoformat(), site, item,
                )
                exclusions[exclusion_key] = exclusions.get(exclusion_key, 0) + units
    return exclusions, complete


async def _incentive_item_rows(scope: dict[str, Any]) -> list[Any]:
    base_params: list[Any] = [scope["month"]]
    if scope["cutoff_date"] is not None:
        base_params.append(scope["cutoff_date"])
    params, positions = build_scoped_params(
        base_params, firma=scope["firma"], regional=scope["regional"], asm=scope["asm"],
        site_code=scope["site_code"], agent=scope["agent"],
    )
    clauses = ["agg.import_month = $1"]
    if scope["cutoff_date"] is not None:
        clauses.append("agg.sale_date <= $2")
    clauses.extend(campaign_scope_clauses(
        positions, current_scope=scope["current_scope"],
        include_closed_stores=scope["include_closed_stores"],
    ))
    return list(await scope["conn"].fetch(
        f"""
        SELECT agg.site_code, agg.item_code, ip.valid_from, ip.valid_to, ip.reward_value,
               COALESCE(SUM(agg.net_quantity), 0)::INT AS qty,
               COALESCE(SUM(agg.total_sales), 0) AS sales
        FROM reporting_item_day agg
        {campaign_scope_join(scope["current_scope"])}
        JOIN incentive_campaigns ic ON ic.month = agg.import_month
        JOIN incentive_products ip ON ip.campaign_id = ic.id
          AND ip.item_code = agg.item_code AND agg.sale_date BETWEEN ip.valid_from AND ip.valid_to
        WHERE {" AND ".join(clauses)}
        GROUP BY agg.site_code, agg.item_code, ip.valid_from, ip.valid_to, ip.reward_value
        """,
        *params,
    ))


def _eligible_quantity(
    row: Any, periods: list[dict[str, Any]], exclusions: dict[tuple[str, str, str, str], int],
) -> int:
    start = row.get("valid_from") or periods[0]["valid_from"]
    end = row.get("valid_to") or periods[0]["valid_to"]
    excluded = exclusions.get((
        start.isoformat(), end.isoformat(), str(row["site_code"]), str(row["item_code"]),
    ), 0)
    return max(0, int(row["qty"]) - excluded)


async def _count_qualified_agents(scope: dict[str, Any], codes: list[str]) -> int:
    if not codes:
        return 0
    source = "reporting_agent_day" if scope["cutoff_date"] is not None else "reporting_agent_month"
    cutoff_clause = "AND sale_date <= $3" if scope["cutoff_date"] is not None else ""
    params: list[Any] = [scope["month"], codes]
    if scope["cutoff_date"] is not None:
        params.append(scope["cutoff_date"])
    row = await scope["conn"].fetchrow(
        f"""
        SELECT COUNT(DISTINCT agent) AS cnt FROM {source}
        WHERE import_month = $1 AND site_code = ANY($2)
          AND agent IS NOT NULL AND agent != '-' {cutoff_clause}
        """,
        *params,
    )
    return int(row["cnt"] or 0) if row else 0


def _qualified_store_codes(
    achievements: dict[str, float | None],
) -> tuple[list[str], list[str], list[str]]:
    qualified = [site for site, value in achievements.items() if value is not None and value >= 0.9]
    full = [site for site, value in achievements.items() if value is not None and value >= 1.0]
    half = [site for site, value in achievements.items() if value is not None and 0.9 <= value < 1.0]
    return qualified, full, half


async def _incentive_values(
    scope: dict[str, Any], context: CampaignContext, complete: bool, warnings: list[str],
) -> tuple[dict[str, Any], bool]:
    empty = {
        "incentive_sold_qty": 0, "incentive_sales": Decimal("0"),
        "incentive_qty": 0 if complete else None, "incentive_potential": Decimal("0") if complete else None,
        "incentive_value": Decimal("0") if complete else None,
        "incentive_qualified_qty": 0 if complete else None,
        "incentive_qualified_stores": 0, "incentive_qualified_stores_full": 0,
        "incentive_qualified_stores_half": 0, "incentive_qualified_agents": 0,
        "incentive_qualified_agents_full": 0, "incentive_qualified_agents_half": 0,
    }
    campaign = context.incentive_campaign
    if campaign is None:
        return empty, complete
    periods, codes = _incentive_periods(scope["month"], campaign, scope["cutoff_date"])
    if not codes:
        return empty, complete
    exclusions, complete = await _period_exclusions(scope, context, periods, complete, warnings)
    rows = await _incentive_item_rows(scope)
    multipliers, achievements = await get_store_incentive_multipliers(
        scope["conn"], scope["month"], scope["firma"], scope["regional"], scope["asm"],
        scope["site_code"], current_scope=scope["current_scope"],
        include_closed_stores=scope["include_closed_stores"], cutoff_date=scope["cutoff_date"],
    )
    eligible = lambda row: _eligible_quantity(row, periods, exclusions)
    empty["incentive_sold_qty"] = sum(int(row["qty"] or 0) for row in rows)
    empty["incentive_sales"] = sum((Decimal(row.get("sales") or 0) for row in rows), Decimal("0"))
    if complete:
        empty["incentive_qty"] = sum(eligible(row) for row in rows)
        empty["incentive_potential"] = sum((
            Decimal(eligible(row)) * Decimal(str(row.get("reward_value") or campaign.get("reward_map", {}).get(row["item_code"], 0)))
            for row in rows
        ), Decimal("0"))
        empty["incentive_value"] = sum((
            Decimal(eligible(row)) * Decimal(str(row.get("reward_value") or campaign.get("reward_map", {}).get(row["item_code"], 0)))
            * Decimal(str(multipliers.get(row["site_code"], 0))) for row in rows
        ), Decimal("0"))
    else:
        empty.update({
            "incentive_qty": None, "incentive_potential": None,
            "incentive_value": None, "incentive_qualified_qty": None,
        })
    qualified, full, half = _qualified_store_codes(achievements)
    empty.update({
        "incentive_qualified_stores": len(qualified),
        "incentive_qualified_stores_full": len(full), "incentive_qualified_stores_half": len(half),
        "incentive_qualified_agents_full": await _count_qualified_agents(scope, full),
        "incentive_qualified_agents_half": await _count_qualified_agents(scope, half),
        "incentive_qualified_agents": await _count_qualified_agents(scope, qualified),
    })
    if complete:
        qualified_set = set(qualified)
        empty["incentive_qualified_qty"] = sum(eligible(row) for row in rows if row["site_code"] in qualified_set)
    return empty, complete


async def fetch_promo_incentive_summary(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    campaign_context: CampaignContext | None = None,
    cutoff_date: date | None = None,
) -> PromoIncentiveSummary:
    """Compute the canonical Promo/Incentive summary on one DB snapshot."""
    scope = {
        "conn": conn, "month": month, "firma": firma, "regional": regional, "asm": asm,
        "site_code": site_code, "agent": agent, "current_scope": current_scope,
        "include_closed_stores": include_closed_stores, "cutoff_date": cutoff_date,
    }
    if campaign_context is None:
        campaign_context = await load_campaign_context(
            conn, month, firma, regional, asm, site_code, agent,
            current_scope=current_scope, include_closed_stores=include_closed_stores,
            cutoff_date=cutoff_date,
        )
    complete = not (
        campaign_context.incentive_campaign is not None
        and campaign_context.promotion_status is not PromotionEvaluationStatus.COMPLETE
    )
    warnings = list(campaign_context.promotion_warnings)
    if not complete and not warnings:
        warnings.append("Excluderile promo nu pot fi validate complet pentru calculul Incentive.")
    promo_qty, promo_sales, promo_impact = await _promotion_totals(scope, campaign_context)
    incentive, complete = await _incentive_values(scope, campaign_context, complete, warnings)
    if campaign_context.selected_promotion_result is None:
        promo_impact = promo_sales * PROMOTION_DISCOUNT_RATE
    return PromoIncentiveSummary(
        promo_qty=promo_qty, promo_sales=promo_sales, promo_impact=promo_impact,
        calculation_status="complete" if complete else "invalid",
        calculation_warnings=list(dict.fromkeys(warnings)),
        **incentive,
    )
