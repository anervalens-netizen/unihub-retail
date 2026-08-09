"""Immutable inputs and promotion evaluations from one Campaigns DB snapshot."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from services.campaigns.aggregation import merge_excluded_units
from services.campaigns.loader import load_campaign_configuration, load_incentive_campaign
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_promotion_definitions,
)
from services.incentive_db import get_incentive_campaign
from services.campaigns.contracts import CampaignContext, CampaignResponseSnapshot
from services.promotion_evaluation import (
    PromotionEvaluationStatus,
    evaluate_promotion,
    scope_promotion_definition_to_interval,
)


async def build_campaign_context(
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
    evaluator: Any = evaluate_promotion,
) -> CampaignContext:
    definitions_to_evaluate = (
        list(promotion_definitions)
        if include_incentive
        else [promotion_definition] if promotion_definition is not None else []
    )
    if promotion_definition is not None and not any(
        item.get("key") == promotion_definition.get("key")
        for item in definitions_to_evaluate
    ):
        definitions_to_evaluate.insert(0, promotion_definition)

    promotion_results = []
    promotion_evaluations = []
    excluded_units: dict[tuple[str, str, str], int] = {}
    discount_values: dict[tuple[str, str, str], Decimal] = {}
    status = (
        PromotionEvaluationStatus.INVALID
        if promotion_error is not None
        else PromotionEvaluationStatus.COMPLETE
    )
    warnings: list[str] = []
    if promotion_error is None:
        for definition in definitions_to_evaluate:
            evaluation = await evaluator(
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
                status = PromotionEvaluationStatus.INVALID
            elif (
                evaluation.status is PromotionEvaluationStatus.PARTIAL
                and status is PromotionEvaluationStatus.COMPLETE
            ):
                status = PromotionEvaluationStatus.PARTIAL
            if evaluation.warning:
                warnings.append(evaluation.warning)
            if evaluation.result is None:
                continue
            promotion_results.append((definition, evaluation.result))
            merge_excluded_units(excluded_units, evaluation.result.excluded_units)
            for key, value in evaluation.result.excluded_discount_values.items():
                discount_values[key] = (
                    discount_values.get(key, Decimal("0")) + value
                )

    return CampaignContext(
        config_error=config_error,
        promotion_definitions=promotion_definitions,
        promotion_definition=promotion_definition,
        promotion_error=promotion_error,
        incentive_campaign=incentive_campaign,
        promotion_results=promotion_results,
        promo_excluded_units=excluded_units,
        promo_discount_values=discount_values,
        promotion_status=status,
        promotion_warnings=tuple(dict.fromkeys(warnings)),
        promotion_evaluations=promotion_evaluations,
    )


async def materialize_period_evaluations(
    conn: asyncpg.Connection,
    *,
    campaign_context: CampaignContext,
    periods: list[dict[str, Any]],
    promotion_definitions: list[dict[str, Any]],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool,
    include_closed_stores: bool,
    evaluator: Any,
) -> None:
    """Populate split-period evaluations inside the authoritative DB snapshot."""
    if len(periods) <= 1:
        return
    for period in periods:
        for definition in promotion_definitions:
            period_start = max(period["valid_from"], definition["start_date"])
            period_end = min(period["valid_to"], definition["end_date"])
            if period_start > period_end:
                continue
            cache_key = campaign_context.period_evaluation_key(
                definition,
                period_start,
                period_end,
            )
            if cache_key in campaign_context.period_evaluations:
                continue
            campaign_context.period_evaluations[cache_key] = await evaluator(
                conn,
                month=month,
                definition=scope_promotion_definition_to_interval(
                    definition,
                    period_start,
                    period_end,
                ),
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )


async def load_campaign_context(
    conn: asyncpg.Connection,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    cutoff_date: date | None = None,
) -> CampaignContext:
    """Load and evaluate one canonical Campaign context on the supplied snapshot."""
    (
        _config,
        config_error,
        promotion_definitions,
        promotion_list_error,
        promotion_definition,
        promotion_error,
    ) = load_campaign_configuration(
        month,
        promotion_key=None,
        config_loader=load_special_cards_config,
        definitions_loader=parse_promotion_definitions,
        definition_loader=parse_promotion_definition,
    )
    if promotion_error is None:
        promotion_error = promotion_list_error
    incentive_campaign = await load_incentive_campaign(
        conn,
        month,
        loader=get_incentive_campaign,
    )

    if cutoff_date is not None:
        selected_key = (
            promotion_definition.get("key")
            if promotion_definition is not None
            else None
        )
        promotion_definitions = [
            {**definition, "end_date": min(definition["end_date"], cutoff_date)}
            for definition in promotion_definitions
            if definition["start_date"] <= cutoff_date
        ]
        promotion_definition = next(
            (
                definition
                for definition in promotion_definitions
                if definition.get("key") == selected_key
            ),
            None,
        )

    return await build_campaign_context(
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
        include_incentive=True,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        evaluator=evaluate_promotion,
    )
