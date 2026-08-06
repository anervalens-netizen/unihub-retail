"""Immutable campaign evaluation context assembled from one DB snapshot."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import asyncpg

from services.dashboard.queries import DashboardCampaignContext
from services.promotion_evaluation import PromotionEvaluationStatus
from services.campaigns.aggregation import merge_excluded_units
from services.campaigns.promotions import compute_promotion_result


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
    evaluator=compute_promotion_result,
) -> DashboardCampaignContext:
    definitions_to_evaluate = list(promotion_definitions) if include_incentive else [promotion_definition] if promotion_definition is not None else []
    if promotion_definition is not None and not any(item.get("key") == promotion_definition.get("key") for item in definitions_to_evaluate):
        definitions_to_evaluate.insert(0, promotion_definition)
    promotion_results = []
    promotion_evaluations = []
    excluded_units: dict[tuple[str, str, str], int] = {}
    discount_values: dict[tuple[str, str, str], Decimal] = {}
    status = PromotionEvaluationStatus.INVALID if promotion_error is not None else PromotionEvaluationStatus.COMPLETE
    warnings: list[str] = []
    if promotion_error is None:
        for definition in definitions_to_evaluate:
            evaluation = await evaluator(conn, month=month, definition=definition, firma=firma, regional=regional, asm=asm, site_code=site_code, agent=agent, current_scope=current_scope, include_closed_stores=include_closed_stores)
            promotion_evaluations.append((definition, evaluation))
            if evaluation.status is PromotionEvaluationStatus.INVALID:
                status = PromotionEvaluationStatus.INVALID
            elif evaluation.status is PromotionEvaluationStatus.PARTIAL and status is PromotionEvaluationStatus.COMPLETE:
                status = PromotionEvaluationStatus.PARTIAL
            if evaluation.warning:
                warnings.append(evaluation.warning)
            if evaluation.result is None:
                continue
            promotion_results.append((definition, evaluation.result))
            merge_excluded_units(excluded_units, evaluation.result.excluded_units)
            for key, value in evaluation.result.excluded_discount_values.items():
                discount_values[key] = discount_values.get(key, Decimal("0")) + value
    return DashboardCampaignContext(
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
