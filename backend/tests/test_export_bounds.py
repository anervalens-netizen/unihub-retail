from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

import services.exports as exports_module
from services.exports import ExportValidationError, ExportsService


def report_row(site_code: str) -> dict[str, Any]:
    return {
        "site_code": site_code,
        "locatie": f"Magazin {site_code}",
        "firma": "Firma 1",
        "regional": "RM 1",
        "asm": "ASM 1",
        "agent": "Agent 1",
        "total_sales": Decimal("100"),
        "total_quantity": 1,
        "total_receipts": 1,
        "receipt_2plus_count": 0,
        "focus_quantity": 0,
        "target": Decimal("100"),
        "working_days": 1,
        "store_count": 1,
        "agent_count": 1,
        "incentive_sales": Decimal("0"),
        "incentive_quantity": 0,
        "incentive_bonus": Decimal("0"),
        "promo_sales": Decimal("0"),
        "promo_quantity": 0,
    }


class BoundedRepo:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []

    async def fetch_report_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(kwargs)
        if kwargs.get("period"):
            return []
        return self.rows


@pytest.mark.asyncio
async def test_preview_fetches_only_bounded_rows_and_does_not_build_full_report() -> None:
    repo = BoundedRepo([report_row(f"S{index:03d}") for index in range(5)])
    service = ExportsService(repo)  # type: ignore[arg-type]
    service.build_report = AsyncMock(side_effect=AssertionError("preview must stay bounded"))  # type: ignore[method-assign]

    result = await service.preview(
        {"dataset": "stores", "months": ["2026-06"], "preview_limit": 3}
    )

    assert repo.calls[0]["limit"] == 4
    assert repo.calls[0]["include_total_count"] is True
    assert len(result["rows"]) == 3
    assert result["total_rows"] == 5
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_report_rejects_row_cap_before_period_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exports_module, "EXPORT_MAX_ROWS", 2)
    repo = BoundedRepo([report_row("S001"), report_row("S002"), report_row("S003")])
    service = ExportsService(repo)  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="limita.*randuri"):
        await service.build_report({"dataset": "stores", "months": ["2026-06"]})

    assert len(repo.calls) == 1


@pytest.mark.asyncio
async def test_report_rejects_cell_cap_before_period_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exports_module, "EXPORT_MAX_CELLS", 1)
    repo = BoundedRepo([report_row("S001")])
    service = ExportsService(repo)  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="celule"):
        await service.build_xlsx_artifact({"dataset": "stores", "months": ["2026-06"]})

    assert len(repo.calls) == 1


@pytest.mark.asyncio
async def test_report_rejects_estimated_byte_cap_before_xlsx_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(exports_module, "EXPORT_MAX_OUTPUT_BYTES", 4096)
    repo = BoundedRepo([report_row("S001")])
    service = ExportsService(repo)  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="dimensiune estimata"):
        await service.build_xlsx_artifact({"dataset": "stores", "months": ["2026-06"]})

    assert len(repo.calls) == 1
