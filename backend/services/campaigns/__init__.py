from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from schemas.campaigns import (
    CampaignOverview,
    CampaignProductStat,
    CampaignSnapshot,
    CampaignStoreStat,
    FocusHistoryResponse,
    FocusHistoryPoint,
    PromoTopStore,
    PromoTopAgent,
    IncentiveCategory,
    IncentiveCategoryBreakdown,
    IncentivePeriodStat,
    IncentiveTopAgent,
)
from repositories.campaigns import CampaignsRepository
from services.dashboard.queries import (
    DashboardCampaignContext,
    _fetch_promo_incentive_summary,
    _get_store_incentive_multipliers,
)
from services.campaigns.loader import load_campaign_configuration, load_incentive_campaign
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definitions,
    parse_promotion_definition,
)
from services.incentive_db import get_incentive_campaign
from services.promotion_evaluation import (
    PromotionEvaluation,
    PromotionEvaluationStatus,
    evaluate_promotion,
    scope_promotion_definition_to_interval,
)
from services.campaigns.money import (
    allocate_currency_targets as _allocate_currency_targets,
    allocate_integer_target as _allocate_integer_target,
    money as _money,
    money_float as _money_float,
)
from services.campaigns.range_policy import CampaignDateRangeError, validate_campaign_date_range
from services.campaigns.aggregation import (
    excluded_by_site_item,
    merge_excluded_units,
)
from services.campaigns.promotions import compute_promotion_result
from services.campaigns.incentives import incentive_item_codes
from services.campaigns.context import build_campaign_context
from services.campaigns.response import calculation_status


def _merge_excluded_units(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, units in source.items():
        target[key] = target.get(key, 0) + units


def _excluded_by_site_item(
    excluded_units: dict[tuple[str, str, str], int],
) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for (site_code, _agent, item_code), units in excluded_units.items():
        out[(site_code, item_code)] = out.get((site_code, item_code), 0) + units
    return out


async def _compute_promotion_result(
    conn: asyncpg.Connection,
    *,
    month: str,
    definition: dict[str, Any],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
) -> PromotionEvaluation:
    return await evaluate_promotion(
        conn,
        month=month,
        definition=definition,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )


async def _legacy_build_campaign_context(
    conn: asyncpg.Connection,
    *,
    config_error: str | None,
    promotion_definitions: list[dict[str, Any]],
    promotion_definition: dict[str, Any] | None,
    promotion_error: str | None,
    incentive_campaign: dict[str, Any] | None,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    include_incentive: bool,
    current_scope: bool,
    include_closed_stores: bool,
) -> DashboardCampaignContext:
    definitions_to_evaluate = (
        list(promotion_definitions)
        if include_incentive
        else [promotion_definition] if promotion_definition is not None else []
    )
    if promotion_definition is not None:
        selected_key = promotion_definition.get("key")
        if not any(
            definition.get("key") == selected_key
            for definition in definitions_to_evaluate
        ):
            definitions_to_evaluate.insert(0, promotion_definition)

    promotion_results = []
    promotion_evaluations = []
    promo_excluded_units: dict[tuple[str, str, str], int] = {}
    promo_discount_values: dict[tuple[str, str, str], Decimal] = {}
    promotion_status = (
        PromotionEvaluationStatus.INVALID
        if promotion_error is not None
        else PromotionEvaluationStatus.COMPLETE
    )
    promotion_warnings: list[str] = []

    if promotion_error is None:
        for definition in definitions_to_evaluate:
            evaluation = await _compute_promotion_result(
                conn,
                month=month,
                definition=definition,
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )
            promotion_evaluations.append((definition, evaluation))
            if evaluation.status is PromotionEvaluationStatus.INVALID:
                promotion_status = PromotionEvaluationStatus.INVALID
            elif (
                evaluation.status is PromotionEvaluationStatus.PARTIAL
                and promotion_status is PromotionEvaluationStatus.COMPLETE
            ):
                promotion_status = PromotionEvaluationStatus.PARTIAL
            if evaluation.warning:
                promotion_warnings.append(evaluation.warning)
            if evaluation.result is None:
                continue
            promotion_results.append((definition, evaluation.result))
            _merge_excluded_units(
                promo_excluded_units,
                evaluation.result.excluded_units,
            )
            for key, value in evaluation.result.excluded_discount_values.items():
                promo_discount_values[key] = (
                    promo_discount_values.get(key, Decimal("0")) + value
                )

    return DashboardCampaignContext(
        config_error=config_error,
        promotion_definitions=promotion_definitions,
        promotion_definition=promotion_definition,
        promotion_error=promotion_error,
        incentive_campaign=incentive_campaign,
        promotion_results=promotion_results,
        promo_excluded_units=promo_excluded_units,
        promo_discount_values=promo_discount_values,
        promotion_status=promotion_status,
        promotion_warnings=tuple(dict.fromkeys(promotion_warnings)),
        promotion_evaluations=promotion_evaluations,
    )


# Keep the historical private names stable for the service and publishers while
# making the domain modules the actual implementation boundary.
_merge_excluded_units = merge_excluded_units
_excluded_by_site_item = excluded_by_site_item
_compute_promotion_result = compute_promotion_result


async def _build_campaign_context(conn: asyncpg.Connection, **kwargs: Any) -> DashboardCampaignContext:
    return await build_campaign_context(conn, evaluator=_compute_promotion_result, **kwargs)


class CampaignsService:
    def __init__(self, repo: CampaignsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def get_campaign_overview(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> CampaignSnapshot:
        data = await self.repo.fetch_overview(
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )

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
            products=[CampaignProductStat(**dict(row)) for row in data["products"]],
            stores=[CampaignStoreStat(**dict(row)) for row in data["stores"]],
        )

    async def get_focus_history(
        self,
        month: str,
        months_back: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> FocusHistoryResponse:
        rows = await self.repo.fetch_history(
            month,
            months_back,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        return FocusHistoryResponse(
            history=[FocusHistoryPoint(**dict(row)) for row in rows]
        )

    async def get_promotions_incentives(
        self,
        start_date: date,
        end_date: date,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        promotion_key: str | None = None,
        view: str = "all",
        current_scope: bool = False,
        include_closed_stores: bool = False,
    ) -> dict:
        try:
            start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
            end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date
        except ValueError as exc:
            raise CampaignDateRangeError("invalid_iso_date") from exc
        month = validate_campaign_date_range(start, end)

        (
            config,
            config_error,
            promotion_definitions,
            promotion_list_error,
            promotion_definition,
            promotion_error,
        ) = load_campaign_configuration(
            month,
            promotion_key=promotion_key,
            config_loader=load_special_cards_config,
            definitions_loader=parse_promotion_definitions,
            definition_loader=parse_promotion_definition,
        )
        if promotion_error is None:
            promotion_error = promotion_list_error
        promotion_options = [
            {
                "key": str(definition.get("key") or ""),
                "label": str(definition.get("title") or "Promotie"),
            }
            for definition in promotion_definitions
        ]
        include_incentive = view != "promo"

        # All DB inputs are materialized under one immutable snapshot.  The
        # connection is released before the response aggregation/formatting
        # phase so CPU work does not occupy a pool slot.
        conn = await self.pool.acquire()
        try:
            async with conn.transaction(
                isolation="repeatable_read",
                readonly=True,
            ):
                incentive_campaign = (
                    await load_incentive_campaign(conn, month, loader=get_incentive_campaign)
                    if include_incentive
                    else None
                )
                campaign_context = await _build_campaign_context(
                    conn,
                    config_error=config_error,
                    promotion_definitions=promotion_definitions,
                    promotion_definition=promotion_definition,
                    promotion_error=promotion_error,
                    incentive_campaign=incentive_campaign,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    include_incentive=include_incentive,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                summary = (
                    await _fetch_promo_incentive_summary(
                        conn=conn,
                        month=month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                        campaign_context=campaign_context,
                    )
                    if include_incentive
                    else None
                )
                # Split incentive mechanisms need scoped promo evaluations too;
                # materialize them while the same repeatable-read snapshot is
                # still open so the CPU phase performs no DB I/O.  Summary is
                # intentionally loaded first because it can populate the same
                # request-local evaluation cache.
                if incentive_campaign is not None:
                    snapshot_periods = incentive_campaign.get("periods") or []
                    if not snapshot_periods and incentive_campaign.get("reward_map"):
                        snapshot_periods = [{
                            "valid_from": start,
                            "valid_to": end,
                            "products": [
                                {"item_code": code, "reward_value": reward}
                                for code, reward in incentive_campaign["reward_map"].items()
                            ],
                        }]
                    if len(snapshot_periods) > 1:
                        for period in snapshot_periods:
                            for definition in promotion_definitions:
                                period_start_date = max(
                                    period["valid_from"], definition["start_date"]
                                )
                                period_end_date = min(
                                    period["valid_to"], definition["end_date"]
                                )
                                if period_start_date > period_end_date:
                                    continue
                                cache_key = campaign_context.period_evaluation_key(
                                    definition,
                                    period_start_date,
                                    period_end_date,
                                )
                                if cache_key not in campaign_context.period_evaluations:
                                    campaign_context.period_evaluations[cache_key] = (
                                        await _compute_promotion_result(
                                            conn,
                                            month=month,
                                            definition=scope_promotion_definition_to_interval(
                                                definition,
                                                period_start_date,
                                                period_end_date,
                                            ),
                                            firma=firma,
                                            regional=regional,
                                            asm=asm,
                                            site_code=site_code,
                                            agent=agent,
                                            current_scope=current_scope,
                                            include_closed_stores=include_closed_stores,
                                        )
                                    )
                store_multipliers, store_achievements = (
                    await _get_store_incentive_multipliers(
                        conn,
                        month,
                        firma,
                        regional,
                        asm,
                        site_code,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                    if incentive_campaign is not None
                    else ({}, {})
                )
                has_active_promotion = (
                    promotion_definition is not None and promotion_error is None
                )
                promo_total_row = None
                promo_store_rows: list[Any] = []
                selected_evaluation = campaign_context.selected_promotion_evaluation
                promotion_item_codes = (
                    selected_evaluation.item_codes
                    if selected_evaluation is not None
                    else []
                )
                if has_active_promotion and promotion_item_codes:
                    promo_total_row = await self.repo.fetch_promo_total(
                        start,
                        end,
                        promotion_item_codes,
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                    promo_store_rows = await self.repo.fetch_promo_store_rows(
                        start,
                        end,
                        promotion_item_codes,
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                incentive_codes = incentive_item_codes(incentive_campaign)
                incentive_store_rows: list[Any] = []
                incentive_agent_rows: list[Any] = []
                if incentive_campaign is not None and incentive_codes:
                    incentive_store_rows = await self.repo.fetch_incentive_store_rows(
                        incentive_codes,
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
                    incentive_agent_rows = await self.repo.fetch_incentive_agent_rows(
                        incentive_codes,
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                        current_scope=current_scope,
                        include_closed_stores=include_closed_stores,
                    )
            await self.pool.release(conn)
            conn = None
            promo_title = (
                promotion_definition.get("title", "Promotie")
                if promotion_definition
                else ""
            )
            promo_description = (
                promotion_definition.get("description", "") if promotion_definition else ""
            )

            incentive_title = incentive_campaign["title"] if incentive_campaign else ""
            incentive_description = incentive_campaign["description"] if incentive_campaign else ""
            calculation_warnings: list[str] = []
            promo_calculation_status = calculation_status(
                configured=promotion_definition is not None,
                error=promotion_error,
            )
            incentive_calculation_status = calculation_status(
                configured=incentive_campaign is not None,
                error=None,
            )
            if incentive_campaign is not None and promotion_list_error is not None:
                incentive_calculation_status = "invalid"
                calculation_warnings.append(
                    "Incentive indisponibil: lista promotiilor active nu poate fi validata."
                )

            if (
                incentive_campaign is not None
                and campaign_context.promotion_status
                is not PromotionEvaluationStatus.COMPLETE
            ):
                incentive_calculation_status = "invalid"
                calculation_warnings.extend(
                    campaign_context.promotion_warnings
                )

            if include_incentive and summary is not None:
                promo_qty = summary.promo_qty
                promo_impact = _money(summary.promo_impact)
                incentive_sold_qty = summary.incentive_sold_qty
                incentive_qty = summary.incentive_qty
                incentive_value = (
                    _money(summary.incentive_value)
                    if summary.incentive_value is not None
                    else None
                )
                incentive_qualified_qty = summary.incentive_qualified_qty
                incentive_qualified_stores = summary.incentive_qualified_stores
                incentive_qualified_stores_full = summary.incentive_qualified_stores_full
                incentive_qualified_stores_half = summary.incentive_qualified_stores_half
                incentive_qualified_agents = summary.incentive_qualified_agents
                incentive_qualified_agents_full = summary.incentive_qualified_agents_full
                incentive_qualified_agents_half = summary.incentive_qualified_agents_half
                if summary.calculation_status == "invalid":
                    incentive_calculation_status = "invalid"
                    calculation_warnings.extend(summary.calculation_warnings)
            else:
                promo_qty = 0
                promo_impact = Decimal("0")
                incentive_sold_qty = 0
                incentive_qty = 0
                incentive_value = Decimal("0")
                incentive_qualified_qty = 0
                incentive_qualified_stores = 0
                incentive_qualified_stores_full = 0
                incentive_qualified_stores_half = 0
                incentive_qualified_agents = 0
                incentive_qualified_agents_full = 0
                incentive_qualified_agents_half = 0

            promo_total_qty = 0

            # Regula co-purchase: unitatile reduse (1 per bon calificat) nu se incentiveaza.
            promo_excluded_ag: dict[tuple[str, str, str], int] = {}
            promo_excluded_si: dict[tuple[str, str], int] = {}
            promo_qualifying_bons = 0
            promo_discounted_units = 0
            promo_discount_value = Decimal("0")
            promo_active_stores = 0
            promo_active_agents = 0
            promo_bonuri_by_store: dict[str, int] = {}
            promo_bonuri_by_agent: dict[str, int] = {}
            promo_agent_sites: dict[str, dict[str, int]] = {}
            promotion_item_codes = []
            promotion_rule_type = "selected_item_copurchase"
            incentive_excluded_ag = (
                dict(campaign_context.promo_excluded_units)
                if include_incentive
                else {}
            )
            if has_active_promotion:
                assert promotion_definition is not None
                evaluation = campaign_context.selected_promotion_evaluation
                if evaluation is None:
                    has_active_promotion = False
                    promo_cp = None
                    promo_calculation_status = "invalid"
                    calculation_warnings.append(
                        "Promotia activa nu a putut fi materializata in snapshot."
                    )
                    if include_incentive and incentive_campaign is not None:
                        incentive_calculation_status = "invalid"
                else:
                    promo_cp = evaluation.result
                    promotion_item_codes = evaluation.item_codes
                    promotion_rule_type = evaluation.rule_type
                    promo_calculation_status = evaluation.status.value
                    if not evaluation.is_complete:
                        if evaluation.warning:
                            calculation_warnings.append(evaluation.warning)
                        if include_incentive and incentive_campaign is not None:
                            incentive_calculation_status = "invalid"
                    if evaluation.status is PromotionEvaluationStatus.INVALID:
                        has_active_promotion = False
                        promotion_error = evaluation.warning
                if not has_active_promotion:
                    has_active_promotion = False
                if has_active_promotion and promo_cp is not None:
                    promo_excluded_ag = promo_cp.excluded_units
                    promo_excluded_si = promo_cp.excluded_by_site_item()
                    promo_qualifying_bons = promo_cp.qualifying_bons
                    promo_discounted_units = promo_cp.discounted_units
                    promo_discount_value = promo_cp.discount_value
                    promo_active_stores = promo_cp.active_stores
                    promo_active_agents = promo_cp.active_agents
                    for (site, _ag, _item), units in promo_excluded_ag.items():
                        promo_bonuri_by_store[site] = promo_bonuri_by_store.get(site, 0) + units
                        if _ag and _ag != "-":
                            promo_bonuri_by_agent[_ag] = promo_bonuri_by_agent.get(_ag, 0) + units
                            site_weights = promo_agent_sites.setdefault(_ag, {})
                            site_weights[site] = site_weights.get(site, 0) + units
                if include_incentive:
                    incentive_excluded_si = _excluded_by_site_item(incentive_excluded_ag)
                else:
                    incentive_excluded_si = {}
            else:
                incentive_excluded_si = {}

            if has_active_promotion:
                if promo_total_row:
                    promo_total_qty = int(promo_total_row["total_qty"] or 0)
                store_rows = promo_store_rows
                top_stores = [
                    PromoTopStore(
                        store_name=f"{row['site_code']} - {row['locatie']}",
                        qty=0,
                        total_qty=row["total_qty"],
                        category_qty=0,
                        promo_bons=promo_bonuri_by_store.get(row["site_code"], 0),
                        incentive_value=0.0,
                        incentive_potential=0.0,
                        achievement=store_achievements.get(row["site_code"]),
                        firma=row["firma"] or "",
                    )
                    for row in store_rows
                    if (
                        promotion_rule_type == "selected_item_copurchase"
                        or promo_bonuri_by_store.get(row["site_code"], 0) > 0
                    )
                ]
            else:
                top_stores = []

            store_meta = {
                store.store_name.split(" - ")[0]: (store.store_name, store.firma)
                for store in top_stores
            }
            promo_agent_rows: list[PromoTopAgent] = []
            for agent_name, promo_bons in promo_bonuri_by_agent.items():
                primary_site = max(
                    promo_agent_sites[agent_name],
                    key=lambda site: (promo_agent_sites[agent_name][site], site),
                )
                store_name, firma_val = store_meta.get(primary_site, ("", ""))
                promo_agent_rows.append(
                    PromoTopAgent(
                        agent_name=agent_name,
                        store_name=store_name,
                        firma=firma_val,
                        promo_bons=promo_bons,
                    )
                )
            promo_agents = sorted(
                promo_agent_rows,
                key=lambda item: (-item.promo_bons, item.agent_name),
            )

            top_agents: list[IncentiveTopAgent] = []
            incentive_categories: list[IncentiveCategory] = []
            incentive_periods: list[IncentivePeriodStat] = []
            incentive_category_breakdown: list[IncentiveCategoryBreakdown] = []
            incentive_sold_qty = 0
            incentive_potential: Decimal | None = Decimal("0")
            incentive_product_count = 0

            if incentive_campaign is not None:
                campaign_periods = incentive_campaign.get("periods") or []
                if not campaign_periods and incentive_campaign.get("reward_map"):
                    campaign_periods = [{
                        "valid_from": start,
                        "valid_to": end,
                        "products": [
                            {"item_code": code, "reward_value": reward}
                            for code, reward in incentive_campaign["reward_map"].items()
                        ],
                    }]
                incentive_codes = incentive_item_codes(incentive_campaign)
                incentive_product_count = len(incentive_codes)
                period_excluded_ag: dict[tuple[str, str, str, str, str], int] = {}
                if len(campaign_periods) <= 1:
                    for period in campaign_periods:
                        period_start = period["valid_from"].isoformat()
                        period_end = period["valid_to"].isoformat()
                        for (sc, ag, code), units in incentive_excluded_ag.items():
                            period_excluded_ag[(period_start, period_end, sc, ag, code)] = units
                else:
                    for period in campaign_periods:
                        for definition in promotion_definitions:
                            period_start_date = max(period["valid_from"], definition["start_date"])
                            period_end_date = min(period["valid_to"], definition["end_date"])
                            if period_start_date > period_end_date:
                                continue
                            cache_key = campaign_context.period_evaluation_key(
                                definition,
                                period_start_date,
                                period_end_date,
                            )
                            period_evaluation = (
                                campaign_context.period_evaluations.get(
                                    cache_key
                                )
                            )
                            if period_evaluation is None:
                                incentive_calculation_status = "invalid"
                                calculation_warnings.append(
                                    "Evaluarea promo pentru mecanism nu exista in snapshot."
                                )
                                continue
                            if not period_evaluation.is_complete:
                                incentive_calculation_status = "invalid"
                                calculation_warnings.append(
                                    period_evaluation.warning
                                    or "Excluderile promo nu pot fi alocate complet pe perioade."
                                )
                            period_result = period_evaluation.result
                            if not period_evaluation.is_complete or period_result is None:
                                continue
                            for (sc, ag, code), units in period_result.excluded_units.items():
                                agent_exclusion_key = (
                                    period["valid_from"].isoformat(),
                                    period["valid_to"].isoformat(),
                                    sc,
                                    ag,
                                    code,
                                )
                                period_excluded_ag[agent_exclusion_key] = period_excluded_ag.get(agent_exclusion_key, 0) + units

                period_excluded_si: dict[tuple[str, str, str, str], int] = {}
                for (period_start, period_end, sc, _ag, code), units in period_excluded_ag.items():
                    site_exclusion_key = (period_start, period_end, sc, code)
                    period_excluded_si[site_exclusion_key] = period_excluded_si.get(site_exclusion_key, 0) + units

                if incentive_codes:
                    store_item_rows = incentive_store_rows
                    store_inc: dict[str, list[Any]] = {}
                    store_eligible_by_item: dict[tuple[str, str, str, str], int] = {}
                    store_reward_by_item: dict[tuple[str, str, str, str], Decimal] = {}
                    period_totals: dict[tuple[str, str], list[Any]] = {}
                    category_totals: dict[str, list[Any]] = {}
                    tier_totals: dict[str, list[Any]] = {}
                    incentive_sold_qty = 0
                    incentive_qty = 0
                    incentive_value = Decimal("0")
                    incentive_potential = Decimal("0")
                    incentive_qualified_qty = 0
                    for row in store_item_rows:
                        sc = str(row["site_code"])
                        row_valid_from = row.get("valid_from") or campaign_periods[0]["valid_from"]
                        row_valid_to = row.get("valid_to") or campaign_periods[0]["valid_to"]
                        period_start = row_valid_from.isoformat()
                        period_end = row_valid_to.isoformat()
                        reward_val = _money(
                            row.get("reward_value")
                            or incentive_campaign.get("reward_map", {}).get(row["item_code"], 0)
                        )
                        excluded = period_excluded_si.get((period_start, period_end, sc, str(row["item_code"])), 0)
                        raw_qty = int(row["qty"] or 0)
                        incentive_sold_qty += raw_qty
                        qty = max(0, raw_qty - excluded)
                        item_key = (period_start, period_end, sc, str(row["item_code"]))
                        store_eligible_by_item[item_key] = qty
                        store_reward_by_item[item_key] = reward_val
                        potential = _money(qty * reward_val)
                        value = _money(
                            potential * Decimal(str(store_multipliers.get(sc, 0)))
                        )
                        incentive_qty += qty
                        incentive_potential += potential
                        incentive_value += value
                        if (store_achievements.get(sc) or 0) >= 0.9:
                            incentive_qualified_qty += qty
                        if sc not in store_inc:
                            store_inc[sc] = [row["locatie"], Decimal("0"), row["firma"] or "", 0, Decimal("0")]
                        store_inc[sc][1] += value
                        store_inc[sc][3] += qty
                        store_inc[sc][4] += potential
                        period_total = period_totals.setdefault((period_start, period_end), [0, Decimal("0"), Decimal("0")])
                        period_total[0] += qty
                        period_total[1] += potential
                        period_total[2] += value
                        category = str(row.get("subcategory") or row.get("category") or "Necategorizat")
                        category_total = category_totals.setdefault(category, [0, Decimal("0"), Decimal("0"), 0])
                        category_total[0] += qty
                        category_total[1] += potential
                        category_total[2] += value
                        if (store_achievements.get(sc) or 0) >= 0.9:
                            category_total[3] += qty
                        tier_label = f"{int(reward_val)} RON" if reward_val == int(reward_val) else f"{reward_val} RON"
                        tier_total = tier_totals.setdefault(tier_label, [0, Decimal("0")])
                        tier_total[0] += qty
                        tier_total[1] += potential

                    if has_active_promotion:
                        top_stores = [
                            PromoTopStore(
                                store_name=s.store_name,
                                qty=int(store_inc.get(s.store_name.split(" - ")[0], [None, Decimal("0"), "", 0])[3]),
                                total_qty=s.total_qty,
                                category_qty=s.category_qty,
                                promo_bons=s.promo_bons,
                                incentive_value=_money_float(store_inc.get(s.store_name.split(" - ")[0], [None, Decimal("0")])[1]),
                                incentive_potential=_money_float(store_inc.get(s.store_name.split(" - ")[0], [None, Decimal("0"), "", 0, Decimal("0")])[4]),
                                achievement=s.achievement,
                                firma=s.firma,
                            )
                            for s in top_stores
                        ]
                    else:
                        top_stores = [
                            PromoTopStore(
                                store_name=f"{sc} - {data[0]}", qty=int(data[3]), total_qty=0,
                                category_qty=0, promo_bons=0, incentive_value=_money_float(data[1]),
                                incentive_potential=_money_float(data[4]),
                                achievement=store_achievements.get(sc), firma=str(data[2]),
                            )
                            for sc, data in store_inc.items()
                        ]

                    for index, period in enumerate(campaign_periods):
                        period_start = period["valid_from"].isoformat()
                        period_end = period["valid_to"].isoformat()
                        totals = period_totals.get((period_start, period_end), [0, Decimal("0"), Decimal("0")])
                        label = "Mecanism actualizat" if index == len(campaign_periods) - 1 and len(campaign_periods) > 1 else "Mecanism initial" if len(campaign_periods) > 1 else "Mecanism lunar"
                        incentive_periods.append(IncentivePeriodStat(
                            label=label,
                            start_date=period_start,
                            end_date=period_end,
                            product_count=len(period["products"]),
                            reward_values=sorted({_money_float(product["reward_value"]) for product in period["products"]}),
                            qty=int(totals[0]),
                            potential=_money_float(totals[1]),
                            value=_money_float(totals[2]),
                        ))
                    incentive_category_breakdown = sorted(
                        [IncentiveCategoryBreakdown(
                            label=label,
                            qty=int(values[0]),
                            qualified_qty=int(values[3]),
                            potential=_money_float(values[1]),
                            value=_money_float(values[2]),
                        ) for label, values in category_totals.items() if values[0] > 0],
                        key=lambda item: (-item.qty, item.label),
                    )
                    incentive_categories = sorted(
                        [IncentiveCategory(label=label, qty=int(values[0]), value=_money_float(values[1])) for label, values in tier_totals.items()],
                        key=lambda item: -item.value,
                    )

                    agent_item_rows = incentive_agent_rows
                    agent_item_quantities: dict[
                        tuple[str, str, str, str], dict[str | None, int]
                    ] = {}
                    agent_item_rewards: dict[tuple[str, str, str, str], Decimal] = {}
                    agent_store_meta: dict[str, tuple[str, str]] = {}
                    for row in agent_item_rows:
                        ag = str(row["agent"])
                        sc = str(row["site_code"])
                        loc = str(row["locatie"] or "")
                        firma_val = str(row["firma"] or "")
                        item_code = str(row["item_code"])
                        row_valid_from = row.get("valid_from") or campaign_periods[0]["valid_from"]
                        row_valid_to = row.get("valid_to") or campaign_periods[0]["valid_to"]
                        period_start = row_valid_from.isoformat()
                        period_end = row_valid_to.isoformat()
                        excluded = period_excluded_ag.get((period_start, period_end, sc, ag, item_code), 0)
                        q = max(0, int(row["qty"]) - excluded)
                        reward_value = _money(
                            row.get("reward_value")
                            or incentive_campaign.get("reward_map", {}).get(item_code, 0)
                        )
                        item_key = (period_start, period_end, sc, item_code)
                        quantities = agent_item_quantities.setdefault(item_key, {})
                        quantities[ag] = quantities.get(ag, 0) + q
                        agent_item_rewards[item_key] = reward_value
                        agent_store_meta[sc] = (loc, firma_val)

                    agent_inc: dict[tuple[str, str], Decimal] = {}
                    agent_potential: dict[tuple[str, str], Decimal] = {}
                    agent_qty: dict[tuple[str, str], int] = {}
                    for item_key in sorted(set(store_eligible_by_item) | set(agent_item_quantities)):
                        sc = item_key[2]
                        allocated_quantities = _allocate_integer_target(
                            agent_item_quantities.get(item_key, {}),
                            store_eligible_by_item.get(item_key, 0),
                        )
                        reward_value = agent_item_rewards.get(
                            item_key,
                            store_reward_by_item.get(
                                item_key,
                                _money(
                                    incentive_campaign.get("reward_map", {}).get(item_key[3], 0)
                                ),
                            ),
                        )
                        for allocated_agent, quantity in allocated_quantities.items():
                            label = allocated_agent or "Neatribuit"
                            agent_key = (sc, label)
                            potential = _money(quantity * reward_value)
                            value = _money(
                                potential * Decimal(str(store_multipliers.get(sc, 0)))
                            )
                            agent_qty[agent_key] = agent_qty.get(agent_key, 0) + quantity
                            agent_potential[agent_key] = agent_potential.get(agent_key, Decimal("0")) + potential
                            agent_inc[agent_key] = agent_inc.get(agent_key, Decimal("0")) + value

                    allocated_agent_values = _allocate_currency_targets(
                        agent_inc,
                        {sc: data[1] for sc, data in store_inc.items()},
                    )
                    allocated_agent_potential = _allocate_currency_targets(
                        agent_potential,
                        {sc: data[4] for sc, data in store_inc.items()},
                    )

                    agent_rows: list[IncentiveTopAgent] = []
                    for agent_key in agent_inc:
                        sc, ag = agent_key
                        loc, firma_val = agent_store_meta.get(
                            sc,
                            (
                                str(store_inc.get(sc, ["", Decimal("0"), ""])[0]),
                                str(store_inc.get(sc, ["", Decimal("0"), ""])[2]),
                            ),
                        )
                        store_name = f"{sc} - {loc}" if sc and loc else sc
                        agent_rows.append(
                            IncentiveTopAgent(
                                agent_name=ag,
                                store_name=store_name,
                                firma=firma_val,
                                qty_sold=agent_qty[agent_key],
                                val_incentive=_money_float(allocated_agent_values[agent_key]),
                                incentive_potential=_money_float(allocated_agent_potential[agent_key]),
                                achievement=store_achievements.get(sc),
                            )
                        )

                    top_agents = sorted(
                        agent_rows,
                        key=lambda x: x.val_incentive,
                        reverse=True,
                    )

            if incentive_calculation_status == "invalid":
                incentive_qty = None
                incentive_value = None
                incentive_potential = None
                incentive_qualified_qty = None
                top_agents = []
                incentive_categories = []
                incentive_periods = []
                incentive_category_breakdown = []
                top_stores = []

            return {
                "promotions": promotion_options,
                "selected_promotion_key": promotion_definition.get("key", "") if promotion_definition else "",
                "promo_title": promo_title,
                "promo_description": promotion_error or promo_description,
                "promo_total_qty": promo_total_qty,
                "promo_qty": promo_qty,
                "promo_category_qty": None,
                "promo_impact": _money_float(promo_impact),
                "promo_qualifying_bons": promo_qualifying_bons,
                "promo_discounted_units": promo_discounted_units,
                "promo_discount_value": promo_discount_value,
                "promo_active_stores": promo_active_stores,
                "promo_active_agents": promo_active_agents,
                "has_active_promotion": has_active_promotion,
                "promo_calculation_status": promo_calculation_status,
                "incentive_calculation_status": incentive_calculation_status,
                "calculation_warnings": list(dict.fromkeys(calculation_warnings)),
                "top_stores": top_stores,
                "promo_agents": promo_agents,
                "top_agents": top_agents,
                "incentive_title": incentive_title,
                "incentive_description": incentive_description,
                "incentive_qty": incentive_qty,
                "incentive_sold_qty": incentive_sold_qty,
                "incentive_value": _money_float(incentive_value) if incentive_value is not None else None,
                "incentive_potential": _money_float(incentive_potential) if incentive_potential is not None else None,
                "incentive_qualified_qty": incentive_qualified_qty,
                "incentive_qualified_stores": incentive_qualified_stores,
                "incentive_qualified_stores_full": incentive_qualified_stores_full,
                "incentive_qualified_stores_half": incentive_qualified_stores_half,
                "incentive_qualified_agents": incentive_qualified_agents,
                "incentive_qualified_agents_full": incentive_qualified_agents_full,
                "incentive_qualified_agents_half": incentive_qualified_agents_half,
                "incentive_product_count": incentive_product_count,
                "incentive_categories": incentive_categories,
                "incentive_periods": incentive_periods,
                "incentive_category_breakdown": incentive_category_breakdown,
            }
        finally:
            if conn is not None:
                await self.pool.release(conn)
