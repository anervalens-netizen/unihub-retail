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
