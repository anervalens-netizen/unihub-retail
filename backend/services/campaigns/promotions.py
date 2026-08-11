"""Promotion evaluation and pure response projection for Campaigns."""

from __future__ import annotations

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


def project_promotion(snapshot: CampaignResponseSnapshot) -> PromotionProjection:
    definition = snapshot.promotion_definition
    error = snapshot.promotion_error
    has_active = definition is not None and error is None
    status = calculation_status(configured=definition is not None, error=error)
    warnings: list[str] = []
    invalidates_incentive = False
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

    promo_result = None
    rule_type = "selected_item_copurchase"
    if has_active:
        evaluation = snapshot.campaign_context.selected_promotion_evaluation
        if evaluation is None:
            has_active = False
            status = "invalid"
            warnings.append(
                "Promotia activa nu a putut fi materializata in snapshot."
            )
            invalidates_incentive = (
                snapshot.include_incentive
                and snapshot.incentive_campaign is not None
            )
        else:
            promo_result = evaluation.result
            rule_type = evaluation.rule_type
            status = evaluation.status.value
            if not evaluation.is_complete:
                if evaluation.warning:
                    warnings.append(evaluation.warning)
                invalidates_incentive = (
                    snapshot.include_incentive
                    and snapshot.incentive_campaign is not None
                )
            if evaluation.status is PromotionEvaluationStatus.INVALID:
                has_active = False
                error = evaluation.warning

    qualifying_bons = 0
    discounted_units = 0
    discount_value = Decimal("0")
    active_stores = 0
    active_agents = 0
    by_store: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    agent_sites: dict[str, dict[str, int]] = {}
    if has_active and promo_result is not None:
        qualifying_bons = promo_result.qualifying_bons
        discounted_units = promo_result.discounted_units
        discount_value = promo_result.discount_value
        active_stores = promo_result.active_stores
        active_agents = promo_result.active_agents
        by_store, by_agent, agent_sites = promo_receipt_totals(
            promo_result.excluded_units
        )

    total_qty = (
        int(snapshot.promo_total_row["total_qty"] or 0)
        if has_active and snapshot.promo_total_row
        else 0
    )
    top_stores = (
        [
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
                rule_type == "selected_item_copurchase"
                or by_store.get(row["site_code"], 0) > 0
            )
        ]
        if has_active
        else []
    )

    store_meta = {
        store.store_name.split(" - ")[0]: (store.store_name, store.firma)
        for store in top_stores
    }
    promo_agents: list[PromoTopAgent] = []
    for agent_name, promo_bons in by_agent.items():
        primary_site = max(
            agent_sites[agent_name],
            key=lambda site: (agent_sites[agent_name][site], site),
        )
        store_name, firma = store_meta.get(primary_site, ("", ""))
        promo_agents.append(
            PromoTopAgent(
                agent_name=agent_name,
                store_name=store_name,
                firma=firma,
                promo_bons=promo_bons,
            )
        )
    promo_agents.sort(key=lambda item: (-item.promo_bons, item.agent_name))

    return PromotionProjection(
        title=definition.get("title", "Promotie") if definition else "",
        description=definition.get("description", "") if definition else "",
        error=error,
        has_active=has_active,
        calculation_status=status,
        warnings=warnings,
        invalidates_incentive=invalidates_incentive,
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
