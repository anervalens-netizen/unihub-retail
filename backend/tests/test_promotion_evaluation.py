from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

import services.promotion_evaluation as evaluation_module
from services.promo_copurchase import PromoActualsError, PromoCoPurchaseResult
from services.promotion_evaluation import (
    PromotionEvaluationStatus,
    evaluate_promotion,
    scope_promotion_definition_to_interval,
)


def _definition() -> dict[str, object]:
    return {
        "key": "promo",
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 31),
        "actuals_source_file": "promo.xlsx",
        "actuals_cutoff_date": "2026-07-15",
    }


def test_partial_period_drops_cumulative_actuals_source() -> None:
    scoped = scope_promotion_definition_to_interval(
        _definition(),
        date(2026, 7, 10),
        date(2026, 7, 31),
    )

    assert scoped["start_date"] == date(2026, 7, 10)
    assert scoped["end_date"] == date(2026, 7, 31)
    assert scoped["actuals_source_file"] is None
    assert scoped["actuals_file"] is None


def test_interval_covering_actuals_window_keeps_corrected_source() -> None:
    scoped = scope_promotion_definition_to_interval(
        _definition(),
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    assert scoped["actuals_source_file"] == "promo.xlsx"


@pytest.mark.asyncio
async def test_corrected_actuals_with_invalid_tail_are_explicitly_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual = PromoCoPurchaseResult(
        qualifying_bons=2,
        discounted_units=2,
        excluded_units={("S1", "Agent", "P1"): 2},
    )
    products = {"item_codes": ["P1"]}
    product_results = iter([(products, None), (None, "missing")])
    monkeypatch.setattr(
        evaluation_module,
        "load_promotion_rule_products",
        lambda _definition: next(product_results),
    )
    monkeypatch.setattr(
        evaluation_module,
        "compute_promo_actuals_from_report",
        AsyncMock(return_value=actual),
    )

    result = await evaluate_promotion(
        AsyncMock(),
        month="2026-07",
        definition=_definition(),
        firma=None,
        regional=None,
        asm=None,
        site_code=None,
        agent=None,
    )

    assert result.status is PromotionEvaluationStatus.PARTIAL
    assert result.result is actual
    assert result.warning == "Calculul promo dupa cutoff este incomplet."


@pytest.mark.asyncio
async def test_invalid_corrected_source_never_falls_back_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation_module,
        "load_promotion_rule_products",
        lambda _definition: ({"item_codes": ["P1"]}, None),
    )
    monkeypatch.setattr(
        evaluation_module,
        "compute_promo_actuals_from_report",
        AsyncMock(side_effect=PromoActualsError("invalid source")),
    )
    fallback = AsyncMock(return_value=PromoCoPurchaseResult())
    monkeypatch.setattr(evaluation_module, "compute_promo_copurchase", fallback)

    result = await evaluate_promotion(
        AsyncMock(),
        month="2026-07",
        definition=_definition(),
        firma=None,
        regional=None,
        asm=None,
        site_code=None,
        agent=None,
    )

    assert result.status is PromotionEvaluationStatus.INVALID
    assert result.result is None
    fallback.assert_not_awaited()
