from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

import services.exports as exports_module
import services.promotion_evaluation as promotion_evaluation_module
from services.exports import ExportValidationError, ExportsService
from services.promo_copurchase import PromoCoPurchaseResult
from services.promotion_evaluation import (
    PromotionEvaluation,
    PromotionEvaluationStatus,
)


class AcquireContext:
    def __init__(self, connection: object = "conn") -> None:
        self.connection = connection

    async def __aenter__(self) -> object:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakePool:
    def acquire(self) -> AcquireContext:
        return AcquireContext()


class IncentiveRepo:
    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.pool = FakePool()
        self.records = records or []
        self.calls: list[dict[str, Any]] = []

    async def fetch_incentive_product_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        return self.records


@pytest.mark.asyncio
async def test_incentive_export_requires_repository_pool() -> None:
    service = ExportsService(SimpleNamespace())  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="conexiune la baza de date"):
        await service.build_report(
            {
                "dataset": "incentive_products",
                "months": ["2026-06"],
            }
        )


@pytest.mark.asyncio
async def test_incentive_export_handles_missing_campaign_multiple_periods_and_unpaid_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [
        {
            "site_code": "S3",
            "item_code": "P1",
            "item_name": "Produs 1",
            "category": "Accesorii",
            "subcategory": "Capace",
            "reward_value": Decimal("5"),
            "valid_from": date(2026, 6, 1),
            "net_quantity": 3,
            "positive_quantity": 4,
            "return_quantity": -1,
        },
        {
            "site_code": "S4",
            "item_code": "P2",
            "item_name": "Produs 2",
            "category": "Accesorii",
            "subcategory": "Cabluri",
            "reward_value": Decimal("2"),
            "valid_from": date(2026, 6, 11),
            "net_quantity": -2,
            "positive_quantity": 0,
            "return_quantity": -2,
        },
    ]
    repo = IncentiveRepo(records)
    service = ExportsService(repo)  # type: ignore[arg-type]

    periods = [
        {"valid_from": date(2026, 6, 1), "valid_to": date(2026, 6, 10)},
        {"valid_from": date(2026, 6, 11), "valid_to": date(2026, 6, 25)},
        {"valid_from": date(2026, 6, 26), "valid_to": date(2026, 6, 30)},
    ]

    async def campaign(_conn: object, month: str) -> dict[str, Any] | None:
        if month == "2026-05":
            return None
        return {"id": 1, "periods": periods}

    exclusion_calls: list[list[int] | None] = []

    async def exclusions(
        _months: list[str],
        _filters: dict[str, list[str]],
        selected_days: list[int] | None = None,
    ) -> dict[str, dict[tuple[str, str, str], int]]:
        exclusion_calls.append(selected_days)
        if selected_days == [1]:
            return {"2026-06": {("S3", "Agent 1", "P1"): 1}}
        if selected_days == [20]:
            return {"2026-06": {("S4", "Agent 2", "P2"): 7}}
        return {}

    monkeypatch.setattr(service, "_campaign_exclusions_by_month", exclusions)
    monkeypatch.setattr(exports_module, "get_incentive_campaign", campaign)
    monkeypatch.setattr(
        exports_module,
        "_get_store_incentive_multipliers",
        AsyncMock(
            return_value=(
                {"S3": 0.0, "S4": 0.0},
                {"S3": None, "S4": None},
            )
        ),
    )

    result = await service.build_report(
        {
            "dataset": "incentive_products",
            "months": ["2026-05", "2026-06"],
            "filters": {
                "firma": ["Mobiup", ""],
                "regional": ["RM 1"],
                "asm": [],
                "site_code": ["S3", "S4"],
            },
            "selected_days": [1, 20],
            "include_closed_stores": True,
        }
    )

    assert exclusion_calls == [[1], [20]]
    assert repo.calls == [
        {
            "month": "2026-06",
            "filters": {
                "site_code": ["S3", "S4"],
            },
            "include_closed_stores": True,
            "selected_days": [1, 20],
        }
    ]
    assert result["rows"] == [
        {
            "month": "2026-06",
            "category": "Accesorii",
            "subcategory": "Cabluri",
            "item_code": "P2",
            "item_name": "Produs 2",
            "reward_value": 2.0,
            "positive_quantity": 0,
            "return_quantity": -2,
            "net_quantity": -2,
            "promo_excluded_quantity": 0,
            "eligible_quantity": 0,
            "paid_quantity": 0,
            "paid_full_quantity": 0,
            "paid_half_quantity": 0,
            "unpaid_quantity": 0,
            "qualified_ui_quantity": 0,
            "potential_value": 0.0,
            "paid_value": 0.0,
        },
        {
            "month": "2026-06",
            "category": "Accesorii",
            "subcategory": "Capace",
            "item_code": "P1",
            "item_name": "Produs 1",
            "reward_value": 5.0,
            "positive_quantity": 4,
            "return_quantity": -1,
            "net_quantity": 3,
            "promo_excluded_quantity": 1,
            "eligible_quantity": 2,
            "paid_quantity": 0,
            "paid_full_quantity": 0,
            "paid_half_quantity": 0,
            "unpaid_quantity": 2,
            "qualified_ui_quantity": 0,
            "potential_value": 10.0,
            "paid_value": 0.0,
        },
    ]


@pytest.mark.asyncio
async def test_selected_day_campaign_exclusions_split_ranges_and_control_actuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = SimpleNamespace(pool=FakePool())
    service = ExportsService(repo)  # type: ignore[arg-type]

    active_definition = {
        "key": "active",
        "start_date": date(2026, 2, 1),
        "end_date": date(2026, 2, 5),
        "actuals_source_file": "promo.xlsx",
        "actuals_file": "legacy.xlsx",
    }
    outside_definition = {
        "key": "outside",
        "start_date": date(2026, 2, 10),
        "end_date": date(2026, 2, 12),
    }

    monkeypatch.setattr(exports_module, "load_special_cards_config", lambda: ({"promotions": []}, None))

    def definitions(
        _config: dict[str, Any],
        month: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        return [outside_definition, active_definition], None

    monkeypatch.setattr(exports_module, "parse_promotion_definitions", definitions)
    monkeypatch.setattr(
        promotion_evaluation_module,
        "promo_actuals_cutoff_date",
        lambda _definition: date(2026, 2, 3),
    )

    calls: list[dict[str, Any]] = []

    async def compute(
        _conn: object,
        *,
        month: str,
        definition: dict[str, Any],
        **filters: Any,
    ) -> PromotionEvaluation:
        calls.append({"month": month, "definition": definition, **filters})
        return PromotionEvaluation(
            result=PromoCoPurchaseResult(
                excluded_units={("S1", "Agent 1", "P1"): 2}
            ),
            item_codes=["P1"],
            rule_type="selected_item_copurchase",
            status=PromotionEvaluationStatus.COMPLETE,
        )

    monkeypatch.setattr(exports_module, "_compute_dashboard_promotion_result", compute)

    result = await service._campaign_exclusions_by_month(
        ["2026-02"],
        {
            "firma": ["Mobiup", ""],
            "regional": ["RM 1"],
            "asm": ["ASM 1"],
            "site_code": ["S1"],
            "agent": ["Agent 1"],
        },
        selected_days=[2, 4, 31],
    )

    assert result == {"2026-02": {("S1", "Agent 1", "P1"): 4}}
    assert len(calls) == 2
    first = calls[0]
    assert first["definition"]["start_date"] == date(2026, 2, 2)
    assert first["definition"]["end_date"] == date(2026, 2, 2)
    assert first["definition"]["actuals_source_file"] is None
    assert first["definition"]["actuals_file"] is None
    second = calls[1]
    assert second["definition"]["start_date"] == date(2026, 2, 4)
    assert second["definition"]["end_date"] == date(2026, 2, 4)
    assert second["definition"]["actuals_source_file"] == "promo.xlsx"
    assert second["definition"]["actuals_file"] == "legacy.xlsx"
    assert first["firma"] is None
    assert first["regional"] is None
    assert first["asm"] is None
    assert first["site_code"] == "S1"
    assert first["agent"] == "Agent 1"


@pytest.mark.asyncio
async def test_selected_day_campaign_exclusions_fail_closed_on_config_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ExportsService(SimpleNamespace(pool=FakePool()))  # type: ignore[arg-type]
    monkeypatch.setattr(exports_module, "load_special_cards_config", lambda: ({}, "bad config"))
    monkeypatch.setattr(
        exports_module,
        "parse_promotion_definitions",
        lambda _config, _month: ([], None),
    )

    with pytest.raises(ExportValidationError, match="configuratia Promo"):
        await service._campaign_exclusions_by_month(
            ["2026-06"],
            {},
            selected_days=[1],
        )


@pytest.mark.asyncio
async def test_campaign_exclusions_without_pool_returns_empty() -> None:
    service = ExportsService(SimpleNamespace())  # type: ignore[arg-type]
    assert await service._campaign_exclusions_by_month(["2026-06"], {}) == {}


def test_selected_days_validation_and_long_filename_suffix() -> None:
    service = ExportsService(SimpleNamespace())  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="Selectia zilelor este invalida"):
        service._selected_days({"selected_days": [object()]})
    with pytest.raises(ExportValidationError, match="intre 1 si 31"):
        service._selected_days({"selected_days": [0, 32]})

    assert service._selected_days({"selected_days": list(range(1, 32))}) is None
    assert service._days_filename_suffix(list(range(1, 12))) == "_zile_11selectate"
