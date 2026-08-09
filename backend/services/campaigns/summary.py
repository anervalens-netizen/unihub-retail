"""Canonical Promo/Incentive summary and multiplier queries."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal

from business_rules import PROMOTION_DISCOUNT_RATE
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
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
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


async def fetch_promo_incentive_summary(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    campaign_context: CampaignContext | None = None,
    cutoff_date: date | None = None,
) -> PromoIncentiveSummary:
    """Compute the canonical Promo/Incentive summary on one DB snapshot."""
    if campaign_context is None:
        campaign_context = await load_campaign_context(
            conn,
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            cutoff_date=cutoff_date,
        )
    promotion_definition = campaign_context.promotion_definition
    promotion_error = campaign_context.promotion_error
    incentive_campaign = campaign_context.incentive_campaign
    calculation_status: Literal["complete", "invalid"] = (
        "invalid"
        if incentive_campaign is not None
        and campaign_context.promotion_status is not PromotionEvaluationStatus.COMPLETE
        else "complete"
    )
    calculation_warnings = list(campaign_context.promotion_warnings)
    if calculation_status == "invalid" and not calculation_warnings:
        calculation_warnings.append(
            "Excluderile promo nu pot fi validate complet pentru calculul Incentive."
        )

    promo_qty = 0
    promo_sales = Decimal("0")
    promo_impact = Decimal("0")
    incentive_sold_qty = 0
    incentive_sales = Decimal("0")
    incentive_qty: int | None = 0 if calculation_status == "complete" else None
    incentive_potential: Decimal | None = (
        Decimal("0") if calculation_status == "complete" else None
    )
    incentive_value: Decimal | None = (
        Decimal("0") if calculation_status == "complete" else None
    )
    incentive_qualified_qty: int | None = (
        0 if calculation_status == "complete" else None
    )
    qualified_stores = qualified_stores_full = qualified_stores_half = 0
    qualified_agents = qualified_agents_full = qualified_agents_half = 0

    promo_excluded_units = campaign_context.promo_excluded_units
    selected_result = campaign_context.selected_promotion_result
    if selected_result is not None:
        promo_qty = selected_result.discounted_units
        promo_impact = selected_result.discount_value

    corrected_qty = promo_qty > 0 or bool(promo_excluded_units)
    if promotion_definition is not None and promotion_error is None:
        promo_params, promo_positions = build_scoped_params(
            [
                month,
                promotion_definition["start_date"],
                promotion_definition["end_date"],
                promotion_definition["item_codes"],
            ],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        promo_clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            "agg.item_code = ANY($4::TEXT[])",
            *campaign_scope_clauses(
                promo_positions,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            ),
        ]
        promo_row = await conn.fetchrow(
            f"""
            SELECT
                COALESCE(SUM(agg.positive_quantity), 0) AS promo_qty,
                COALESCE(SUM(agg.total_sales), 0) AS promo_sales
            FROM reporting_item_day agg
            {campaign_scope_join(current_scope)}
            WHERE {" AND ".join(promo_clauses)}
            """,
            *promo_params,
        )
        if promo_row:
            if not corrected_qty:
                promo_qty = int(promo_row["promo_qty"] or 0)
            promo_sales = promo_row["promo_sales"] or Decimal("0")

    excluded_by_site_item: dict[tuple[str, str], int] = {}
    for (site, _agent, item), units in promo_excluded_units.items():
        site_item_key = (site, item)
        excluded_by_site_item[site_item_key] = (
            excluded_by_site_item.get(site_item_key, 0) + units
        )

    if incentive_campaign is not None:
        periods = incentive_campaign.get("periods") or []
        if cutoff_date is not None:
            periods = [
                {**period, "valid_to": min(period["valid_to"], cutoff_date)}
                for period in periods
                if period["valid_from"] <= cutoff_date
            ]
        incentive_codes = incentive_campaign.get("item_codes") or list(
            incentive_campaign.get("reward_map", {}).keys()
        )
        if not periods and incentive_codes:
            year, month_number = (int(value) for value in month.split("-", 1))
            month_start = date(year, month_number, 1)
            month_end = date(
                year + (month_number == 12),
                1 if month_number == 12 else month_number + 1,
                1,
            ) - timedelta(days=1)
            periods = [{"valid_from": month_start, "valid_to": month_end}]
            if cutoff_date is not None:
                periods[0]["valid_to"] = min(month_end, cutoff_date)

        if incentive_codes:
            period_excluded: dict[tuple[str, str, str, str], int] = {}
            if len(periods) <= 1:
                if periods:
                    period_start = periods[0]["valid_from"].isoformat()
                    period_end = periods[0]["valid_to"].isoformat()
                    for (site, item), units in excluded_by_site_item.items():
                        period_excluded[(period_start, period_end, site, item)] = units
            else:
                for period in periods:
                    for definition in campaign_context.promotion_definitions:
                        range_start = max(period["valid_from"], definition["start_date"])
                        range_end = min(period["valid_to"], definition["end_date"])
                        if range_start > range_end:
                            continue
                        evaluation_key = campaign_context.period_evaluation_key(
                            definition,
                            range_start,
                            range_end,
                        )
                        evaluation = campaign_context.period_evaluations.get(
                            evaluation_key
                        )
                        if evaluation is None:
                            evaluation = await compute_promotion_result(
                                conn,
                                month=month,
                                definition=scope_promotion_definition_to_interval(
                                    definition,
                                    range_start,
                                    range_end,
                                ),
                                firma=firma,
                                regional=regional,
                                asm=asm,
                                site_code=site_code,
                                agent=agent,
                                current_scope=current_scope,
                                include_closed_stores=include_closed_stores,
                            )
                            campaign_context.period_evaluations[
                                evaluation_key
                            ] = evaluation
                        if not evaluation.is_complete:
                            calculation_status = "invalid"
                            calculation_warnings.append(
                                evaluation.warning
                                or "Excluderile promo nu pot fi alocate complet pe perioade."
                            )
                            incentive_qty = None
                            incentive_potential = None
                            incentive_value = None
                            incentive_qualified_qty = None
                        result = evaluation.result
                        if not evaluation.is_complete or result is None:
                            continue
                        for (site, _agent, item), units in result.excluded_units.items():
                            exclusion_key = (
                                period["valid_from"].isoformat(),
                                period["valid_to"].isoformat(),
                                site,
                                item,
                            )
                            period_excluded[exclusion_key] = (
                                period_excluded.get(exclusion_key, 0) + units
                            )

            base_params: list[Any] = [month]
            if cutoff_date is not None:
                base_params.append(cutoff_date)
            incentive_params, incentive_positions = build_scoped_params(
                base_params,
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
            )
            incentive_clauses = ["agg.import_month = $1"]
            if cutoff_date is not None:
                incentive_clauses.append("agg.sale_date <= $2")
            incentive_clauses.extend(
                campaign_scope_clauses(
                    incentive_positions,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
            )
            item_rows = await conn.fetch(
                f"""
                SELECT agg.site_code, agg.item_code,
                       ip.valid_from, ip.valid_to, ip.reward_value,
                       COALESCE(SUM(agg.net_quantity), 0)::INT AS qty,
                       COALESCE(SUM(agg.total_sales), 0) AS sales
                FROM reporting_item_day agg
                {campaign_scope_join(current_scope)}
                JOIN incentive_campaigns ic ON ic.month = agg.import_month
                JOIN incentive_products ip
                  ON ip.campaign_id = ic.id
                 AND ip.item_code = agg.item_code
                 AND agg.sale_date BETWEEN ip.valid_from AND ip.valid_to
                WHERE {" AND ".join(incentive_clauses)}
                GROUP BY agg.site_code, agg.item_code,
                         ip.valid_from, ip.valid_to, ip.reward_value
                """,
                *incentive_params,
            )
            multipliers, achievements = await get_store_incentive_multipliers(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                cutoff_date=cutoff_date,
            )

            def eligible_qty(row: Any) -> int:
                row_start = row.get("valid_from") or periods[0]["valid_from"]
                row_end = row.get("valid_to") or periods[0]["valid_to"]
                excluded = period_excluded.get(
                    (
                        row_start.isoformat(),
                        row_end.isoformat(),
                        str(row["site_code"]),
                        str(row["item_code"]),
                    ),
                    0,
                )
                return max(0, int(row["qty"]) - excluded)

            incentive_sold_qty = sum(int(row["qty"] or 0) for row in item_rows)
            incentive_sales = sum(
                (Decimal(row.get("sales") or 0) for row in item_rows),
                Decimal("0"),
            )
            if calculation_status == "complete":
                incentive_qty = sum(eligible_qty(row) for row in item_rows)
                incentive_potential = sum(
                    (
                        Decimal(eligible_qty(row))
                        * Decimal(
                            str(
                                row.get("reward_value")
                                or incentive_campaign.get("reward_map", {}).get(
                                    row["item_code"], 0
                                )
                            )
                        )
                        for row in item_rows
                    ),
                    Decimal("0"),
                )
                incentive_value = sum(
                    (
                        Decimal(eligible_qty(row))
                        * Decimal(
                            str(
                                row.get("reward_value")
                                or incentive_campaign.get("reward_map", {}).get(
                                    row["item_code"], 0
                                )
                            )
                        )
                        * Decimal(str(multipliers.get(row["site_code"], 0)))
                        for row in item_rows
                    ),
                    Decimal("0"),
                )

            qualified_codes = [
                site for site, value in achievements.items()
                if value is not None and value >= 0.9
            ]
            qualified_full_codes = [
                site for site, value in achievements.items()
                if value is not None and value >= 1.0
            ]
            qualified_half_codes = [
                site for site, value in achievements.items()
                if value is not None and 0.9 <= value < 1.0
            ]
            qualified_stores = len(qualified_codes)
            qualified_stores_full = len(qualified_full_codes)
            qualified_stores_half = len(qualified_half_codes)
            if calculation_status == "complete":
                qualified_set = set(qualified_codes)
                incentive_qualified_qty = sum(
                    eligible_qty(row)
                    for row in item_rows
                    if row["site_code"] in qualified_set
                )

            agent_source = (
                "reporting_agent_day"
                if cutoff_date is not None
                else "reporting_agent_month"
            )
            agent_cutoff = "AND sale_date <= $3" if cutoff_date is not None else ""

            async def count_agents(codes: list[str]) -> int:
                if not codes:
                    return 0
                params: list[Any] = [month, codes]
                if cutoff_date is not None:
                    params.append(cutoff_date)
                row = await conn.fetchrow(
                    f"""
                    SELECT COUNT(DISTINCT agent) AS cnt
                    FROM {agent_source}
                    WHERE import_month = $1
                      AND site_code = ANY($2)
                      AND agent IS NOT NULL AND agent != '-'
                      {agent_cutoff}
                    """,
                    *params,
                )
                return int(row["cnt"] or 0) if row else 0

            qualified_agents_full = await count_agents(qualified_full_codes)
            qualified_agents_half = await count_agents(qualified_half_codes)
            qualified_agents = await count_agents(qualified_codes)

    if selected_result is None:
        promo_impact = promo_sales * PROMOTION_DISCOUNT_RATE
    return PromoIncentiveSummary(
        promo_qty=promo_qty,
        promo_sales=promo_sales,
        promo_impact=promo_impact,
        incentive_sold_qty=incentive_sold_qty,
        incentive_sales=incentive_sales,
        incentive_qty=incentive_qty,
        incentive_potential=incentive_potential,
        incentive_value=incentive_value,
        incentive_qualified_qty=incentive_qualified_qty,
        incentive_qualified_stores=qualified_stores,
        incentive_qualified_stores_full=qualified_stores_full,
        incentive_qualified_stores_half=qualified_stores_half,
        incentive_qualified_agents=qualified_agents,
        incentive_qualified_agents_full=qualified_agents_full,
        incentive_qualified_agents_half=qualified_agents_half,
        calculation_status=calculation_status,
        calculation_warnings=list(dict.fromkeys(calculation_warnings)),
    )
