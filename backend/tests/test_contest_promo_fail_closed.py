from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.contests as contests_module
from services.contests import ContestsService
from services.promo_copurchase import PromoActualsError, PromoCoPurchaseResult


@pytest.mark.asyncio
async def test_invalid_configured_promo_actuals_never_fall_back_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ContestsService(MagicMock(), MagicMock())
    actuals = AsyncMock(side_effect=PromoActualsError("invalid source"))
    fallback = AsyncMock(return_value=PromoCoPurchaseResult())
    monkeypatch.setattr(contests_module, "compute_promo_actuals_from_report", actuals)
    monkeypatch.setattr(contests_module, "compute_promo_copurchase", fallback)

    definition = {
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 31),
        "actuals_source_file": "promo.xlsx",
        "actuals_cutoff_date": "2026-07-15",
    }
    scope_kwargs = {
        "firma": None,
        "regional": None,
        "asm": None,
        "site_code": None,
        "agent": None,
    }

    with pytest.raises(PromoActualsError, match="invalid source"):
        await service._promo_with_tail(
            AsyncMock(),
            month="2026-07",
            definition=definition,
            products={"item_codes": ["P1"]},
            rule_type="selected_item_copurchase",
            item_codes=["P1"],
            scope_kwargs=scope_kwargs,
        )

    actuals.assert_awaited_once()
    fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_promo_config_loader_never_scores_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ContestsService(MagicMock(), MagicMock())
    parser = MagicMock()
    monkeypatch.setattr(
        contests_module,
        "load_special_cards_config",
        lambda: ({}, "Configul generației promo nu corespunde hashului aprobat."),
    )
    monkeypatch.setattr(contests_module, "parse_promotion_definition", parser)

    with pytest.raises(RuntimeError, match="Configurația promo"):
        await service._contest_promo_units(
            MagicMock(scope={}),
            "2026-07",
            enabled=True,
        )

    parser.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_active_promo_definition_never_scores_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ContestsService(MagicMock(), MagicMock())
    products_loader = MagicMock()
    monkeypatch.setattr(
        contests_module,
        "load_special_cards_config",
        lambda: ({"promotions": [{}]}, None),
    )
    monkeypatch.setattr(
        contests_module,
        "parse_promotion_definition",
        lambda _config, _month: (None, "Promoția activă este invalidă."),
    )
    monkeypatch.setattr(contests_module, "load_promotion_rule_products", products_loader)

    with pytest.raises(RuntimeError, match="Configurația promo"):
        await service._contest_promo_units(
            MagicMock(scope={}),
            "2026-07",
            enabled=True,
        )

    products_loader.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_active_promo_master_never_scores_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ContestsService(MagicMock(), MagicMock())
    definition = {
        "rule_type": "trigger_discounted",
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 31),
    }
    monkeypatch.setattr(
        contests_module,
        "load_special_cards_config",
        lambda: ({"promotions": [{}]}, None),
    )
    monkeypatch.setattr(
        contests_module,
        "parse_promotion_definition",
        lambda _config, _month: (definition, None),
    )
    monkeypatch.setattr(
        contests_module,
        "load_promotion_rule_products",
        lambda _definition: (None, "Masterul promo lipsește."),
    )

    with pytest.raises(RuntimeError, match="Masterul promo"):
        await service._contest_promo_units(
            MagicMock(scope={}),
            "2026-07",
            enabled=True,
        )


@pytest.mark.asyncio
async def test_no_active_promo_still_means_zero_promo_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ContestsService(MagicMock(), MagicMock())
    products_loader = MagicMock()
    monkeypatch.setattr(
        contests_module,
        "load_special_cards_config",
        lambda: ({"promotions": []}, None),
    )
    monkeypatch.setattr(
        contests_module,
        "parse_promotion_definition",
        lambda _config, _month: (None, None),
    )
    monkeypatch.setattr(contests_module, "load_promotion_rule_products", products_loader)

    result = await service._contest_promo_units(
        MagicMock(scope={}),
        "2026-07",
        enabled=True,
    )

    assert result == {}
    products_loader.assert_not_called()
