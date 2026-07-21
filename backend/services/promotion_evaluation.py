from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Any

from services.dashboard_specials import load_promotion_rule_products
from services.promo_copurchase import (
    PromoActualsError,
    PromoCoPurchaseResult,
    compute_promo_actuals_from_report,
    compute_promo_copurchase,
    compute_promo_same_model_pair,
    compute_promo_trigger_discounted,
    merge_promo_results,
    promo_actuals_cutoff_date,
)


class PromotionEvaluationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INVALID = "invalid"


@dataclass(frozen=True)
class PromotionEvaluation:
    result: PromoCoPurchaseResult | None
    item_codes: list[str]
    rule_type: str
    status: PromotionEvaluationStatus
    warning: str | None = None

    @property
    def is_complete(self) -> bool:
        return self.status is PromotionEvaluationStatus.COMPLETE


async def evaluate_promotion(
    conn: Any,
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
    """Evaluate one promotion without converting missing inputs into zero.

    A corrected POS source can cover only the interval through its cutoff.  If
    the remaining interval cannot be evaluated, the corrected part is retained
    for informational promo display, but the result is explicitly partial and
    must never be used for Incentive payout or official exports.
    """
    products, products_error = load_promotion_rule_products(definition)
    rule_type = definition.get("rule_type") or "selected_item_copurchase"
    if products_error is not None or products is None:
        return PromotionEvaluation(
            result=None,
            item_codes=[],
            rule_type=rule_type,
            status=PromotionEvaluationStatus.INVALID,
            warning="Definitia produselor promo nu poate fi validata.",
        )

    if rule_type in {"same_model_screen_camera", "trigger_discounted"}:
        item_codes = list(products["discounted_codes"])
    else:
        item_codes = list(products["item_codes"])

    try:
        actual_result = await compute_promo_actuals_from_report(
            conn,
            month=month,
            definition=definition,
            item_codes=item_codes,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        )
    except PromoActualsError:
        return PromotionEvaluation(
            result=None,
            item_codes=item_codes,
            rule_type=rule_type,
            status=PromotionEvaluationStatus.INVALID,
            warning="Sursa POS corectiva pentru promo nu poate fi validata.",
        )

    if actual_result is not None:
        cutoff_date = promo_actuals_cutoff_date(definition)
        if cutoff_date is None:
            return PromotionEvaluation(
                actual_result, item_codes, rule_type, PromotionEvaluationStatus.COMPLETE
            )
        tail_start = max(definition["start_date"], cutoff_date + timedelta(days=1))
        if tail_start > definition["end_date"]:
            return PromotionEvaluation(
                actual_result, item_codes, rule_type, PromotionEvaluationStatus.COMPLETE
            )
        tail = await evaluate_promotion(
            conn,
            month=month,
            definition={
                **definition,
                "start_date": tail_start,
                "actuals_source_file": None,
                "actuals_file": None,
            },
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        )
        if not tail.is_complete or tail.result is None:
            return PromotionEvaluation(
                result=actual_result,
                item_codes=item_codes,
                rule_type=rule_type,
                status=PromotionEvaluationStatus.PARTIAL,
                warning="Calculul promo dupa cutoff este incomplet.",
            )
        return PromotionEvaluation(
            result=merge_promo_results(actual_result, tail.result),
            item_codes=item_codes,
            rule_type=rule_type,
            status=PromotionEvaluationStatus.COMPLETE,
        )

    common = {
        "month": month,
        "start_date": definition["start_date"],
        "end_date": definition["end_date"],
        "firma": firma,
        "regional": regional,
        "asm": asm,
        "site_code": site_code,
        "agent": agent,
        "current_scope": current_scope,
        "include_closed_stores": include_closed_stores,
    }
    if rule_type == "same_model_screen_camera":
        result = await compute_promo_same_model_pair(
            conn,
            screen_code_models=products["trigger_code_models"],
            camera_code_models=products["discounted_code_models"],
            **common,
        )
    elif rule_type == "trigger_discounted":
        result = await compute_promo_trigger_discounted(
            conn,
            trigger_codes=products["trigger_codes"],
            discounted_codes=products["discounted_codes"],
            **common,
        )
    else:
        result = await compute_promo_copurchase(conn, item_codes=item_codes, **common)
    return PromotionEvaluation(
        result=result,
        item_codes=item_codes,
        rule_type=rule_type,
        status=PromotionEvaluationStatus.COMPLETE,
    )
