"""Promotion evaluation and pure response projection for Campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import asyncpg

from domain.filter_scope import FilterInput
from schemas.campaigns import PromoTopAgent, PromoTopStore
from services.campaigns.aggregation import promo_receipt_totals
from services.campaigns.contracts import CampaignResponseSnapshot, PromotionProjection
from services.campaigns.money import money
from services.campaigns.status import calculation_status
from services.promotion_evaluation import (
    PromotionEvaluation,
    PromotionEvaluationStatus,
    evaluate_promotion,
)


async def compute_promotion_result(
    conn: asyncpg.Connection,
    *,
    month: str,
    definition: dict[str, Any],
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
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


def promotion_options(
    definitions: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "key": str(definition.get("key") or ""),
            "label": str(definition.get("title") or "Promotie"),
        }
        for definition in definitions
    ]


@dataclass(slots=True)
class _PromotionState:
    definition: dict[str, Any] | None
    error: str | None
    has_active: bool
    status: str
    warnings: list[str]
    invalidates_incentive: bool = False
    promo_result: Any = None
    rule_type: str = "selected_item_copurchase"


def _initial_promotion_state(snapshot: CampaignResponseSnapshot) -> _PromotionState:
    definition = snapshot.promotion_definition
    error = snapshot.promotion_error
    return _PromotionState(
        definition=definition,
        error=error,
        has_active=definition is not None and error is None,
        status=calculation_status(configured=definition is not None, error=error),
        warnings=[],
    )


def _promotion_summary_values(
    snapshot: CampaignResponseSnapshot,
) -> tuple[int | None, Decimal, dict[tuple[str, str, str], int]]:
    qty = (
        snapshot.summary.promo_qty
        if snapshot.include_incentive and snapshot.summary is not None
        else 0
    )
    impact = (
        money(snapshot.summary.promo_impact)
        if snapshot.include_incentive and snapshot.summary is not None
        else Decimal("0")
    )
    incentive_excluded_units = (
        dict(snapshot.campaign_context.promo_excluded_units)
        if snapshot.include_incentive
        else {}
    )
    return qty, impact, incentive_excluded_units


def _apply_selected_evaluation(
    snapshot: CampaignResponseSnapshot,
    state: _PromotionState,
) -> None:
    if not state.has_active:
        return
    evaluation = snapshot.campaign_context.selected_promotion_evaluation
    if evaluation is None:
        state.has_active = False
        state.status = "invalid"
        state.warnings.append(
            "Promotia activa nu a putut fi materializata in snapshot."
        )
        state.invalidates_incentive = (
            snapshot.include_incentive
            and snapshot.incentive_campaign is not None
        )
        return
    state.promo_result = evaluation.result
    state.rule_type = evaluation.rule_type
    state.status = evaluation.status.value
    if not evaluation.is_complete:
        if evaluation.warning:
            state.warnings.append(evaluation.warning)
        state.invalidates_incentive = (
            snapshot.include_incentive
            and snapshot.incentive_campaign is not None
        )
    if evaluation.status is PromotionEvaluationStatus.INVALID:
        state.has_active = False
        state.error = evaluation.warning


def _promotion_metrics(
    state: _PromotionState,
) -> tuple[
    int,
    int,
    Decimal,
    int,
    int,
    dict[str, int],
    dict[str, int],
    dict[str, dict[str, int]],
]:
    if not state.has_active or state.promo_result is None:
        return 0, 0, Decimal("0"), 0, 0, {}, {}, {}
    result = state.promo_result
    by_store, by_agent, agent_sites = promo_receipt_totals(
        result.excluded_units
    )
    return (
        result.qualifying_bons,
        result.discounted_units,
        result.discount_value,
        result.active_stores,
        result.active_agents,
        by_store,
        by_agent,
        agent_sites,
    )


def _promotion_top_stores(
    snapshot: CampaignResponseSnapshot,
    state: _PromotionState,
    by_store: dict[str, int],
) -> list[PromoTopStore]:
    if not state.has_active:
        return []
    return [
        PromoTopStore(
            store_name=f"{row['site_code']} - {row['locatie']}",
            qty=0,
            total_qty=row["total_qty"],
            category_qty=0,
            promo_bons=by_store.get(row["site_code"], 0),
            incentive_value=0.0,
            incentive_potential=0.0,
            achievement=snapshot.store_achievements.get(row["site_code"]),
            firma=row["firma"] or "",
        )
        for row in snapshot.promo_store_rows
        if (
            state.rule_type == "selected_item_copurchase"
            or by_store.get(row["site_code"], 0) > 0
        )
    ]


def _promotion_top_agents(
    top_stores: list[PromoTopStore],
    by_agent: dict[str, int],
    agent_sites: dict[str, dict[str, int]],
) -> list[PromoTopAgent]:
    store_meta = {
        store.store_name.split(" - ")[0]: (store.store_name, store.firma)
        for store in top_stores
    }
    agents: list[PromoTopAgent] = []
    for agent_name, promo_bons in by_agent.items():
        primary_site = max(
            agent_sites[agent_name],
            key=lambda site: (agent_sites[agent_name][site], site),
        )
        store_name, firma = store_meta.get(primary_site, ("", ""))
        agents.append(
            PromoTopAgent(
                agent_name=agent_name,
                store_name=store_name,
                firma=firma,
                promo_bons=promo_bons,
            )
        )
    agents.sort(key=lambda item: (-item.promo_bons, item.agent_name))
    return agents


def project_promotion(snapshot: CampaignResponseSnapshot) -> PromotionProjection:
    state = _initial_promotion_state(snapshot)
    qty, impact, incentive_excluded_units = _promotion_summary_values(snapshot)
    _apply_selected_evaluation(snapshot, state)
    (
        qualifying_bons,
        discounted_units,
        discount_value,
        active_stores,
        active_agents,
        by_store,
        by_agent,
        agent_sites,
    ) = _promotion_metrics(state)
    total_qty = (
        int(snapshot.promo_total_row["total_qty"] or 0)
        if state.has_active and snapshot.promo_total_row
        else 0
    )
    top_stores = _promotion_top_stores(snapshot, state, by_store)
    promo_agents = _promotion_top_agents(top_stores, by_agent, agent_sites)

    return PromotionProjection(
        title=(
            state.definition.get("title", "Promotie")
            if state.definition
            else ""
        ),
        description=(
            state.definition.get("description", "") if state.definition else ""
        ),
        error=state.error,
        has_active=state.has_active,
        calculation_status=state.status,
        warnings=state.warnings,
        invalidates_incentive=state.invalidates_incentive,
        total_qty=total_qty,
        qty=qty,
        impact=impact,
        qualifying_bons=qualifying_bons,
        discounted_units=discounted_units,
        discount_value=discount_value,
        active_stores=active_stores,
        active_agents=active_agents,
        top_stores=top_stores,
        promo_agents=promo_agents,
        incentive_excluded_units=incentive_excluded_units,
    )
