from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any

import pytest
from openpyxl import load_workbook

from services.exports import ExportValidationError, ExportsService


class FakeRepo:
    def __init__(self) -> None:
        self.report_calls: list[dict[str, Any]] = []
        self.daily_comparison_calls: list[dict[str, Any]] = []

    async def fetch_report_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.report_calls.append(kwargs)
        period = kwargs.get("period")
        if period == "month":
            return [
                row(period_key=month, total_sales=amount)
                for month, amount in [("2026-05", "1000"), ("2026-06", "1500")]
            ]
        if period == "day":
            return [
                row(period_key="2026-06-01", total_sales="500", total_quantity=5, total_receipts=2),
                row(period_key="2026-06-02", total_sales="700", total_quantity=7, total_receipts=3),
            ]
        return [row(total_sales="2500", total_quantity=25, total_receipts=10)]

    async def fetch_daily_evolution_rows(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def fetch_daily_comparison_rows(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.daily_comparison_calls.append(kwargs)
        return [
            row(import_month="2026-05", day_of_month=1, total_sales="100", total_quantity=10, total_receipts=5),
            row(import_month="2026-06", day_of_month=1, total_sales="150", total_quantity=15, total_receipts=6),
        ]


def row(**overrides: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "agent": "Agent 1",
        "site_code": "S001",
        "locatie": "Magazin 1",
        "firma": "Firma 1",
        "regional": "RM 1",
        "asm": "ASM 1",
        "period_key": "2026-06",
        "import_month": "2026-06",
        "day_of_month": 1,
        "total_sales": Decimal("1000"),
        "total_quantity": 10,
        "total_receipts": 5,
        "receipt_2plus_count": 2,
        "focus_quantity": 1,
        "target": Decimal("2000"),
        "working_days": 2,
        "store_count": 1,
        "agent_count": 1,
    }
    defaults.update(overrides)
    for key in ("total_sales", "target"):
        defaults[key] = Decimal(str(defaults[key]))
    return defaults


@pytest.mark.asyncio
async def test_preview_builds_monthly_and_daily_columns_without_db() -> None:
    repo = FakeRepo()
    service = ExportsService(repo)  # type: ignore[arg-type]

    result = await service.preview(
        {
            "dataset": "agents",
            "months": ["2026-06", "2026-05"],
            "dimensions": ["agent", "site_code"],
            "metrics": ["total_sales", "target_progress_pct", "avg_receipt_value"],
            "monthly_metrics": ["total_sales"],
            "daily_metrics": ["total_sales"],
            "preview_limit": 10,
        }
    )

    keys = [column["key"] for column in result["columns"]]
    assert keys[:5] == ["agent", "site_code", "total_sales", "target_progress_pct", "avg_receipt_value"]
    assert "month:2026-05:total_sales" in keys
    assert "month:2026-06:total_sales" in keys
    assert "day:2026-06-01:total_sales" in keys
    assert result["total_rows"] == 1
    assert result["rows"][0]["total_sales"] == 2500.0
    assert result["rows"][0]["target_progress_pct"] == 125.0
    assert result["rows"][0]["avg_receipt_value"] == 250.0
    assert repo.report_calls[0]["months"] == ["2026-05", "2026-06"]


@pytest.mark.asyncio
async def test_preview_rejects_invalid_or_too_wide_requests() -> None:
    service = ExportsService(FakeRepo())  # type: ignore[arg-type]

    with pytest.raises(ExportValidationError, match="Dataset invalid"):
        await service.preview({"dataset": "bad", "months": ["2026-06"]})

    with pytest.raises(ExportValidationError, match="Evolutia zilnica este limitata"):
        await service.preview(
            {
                "dataset": "stores",
                "months": ["2026-03", "2026-04", "2026-05", "2026-06"],
                "daily_metrics": ["total_sales"],
            }
        )

    with pytest.raises(ExportValidationError, match="Selectie invalida pentru metrici"):
        await service.preview({"dataset": "stores", "months": ["2026-06"], "metrics": ["unknown"]})


@pytest.mark.asyncio
async def test_daily_comparison_preview_computes_delta_rows() -> None:
    repo = FakeRepo()
    service = ExportsService(repo)  # type: ignore[arg-type]

    result = await service.preview(
        {
            "export_mode": "daily_comparison",
            "dataset": "stores",
            "months": ["2026-05", "2026-06"],
            "daily_metrics": ["total_sales"],
            "comparison_levels": ["general"],
            "preview_limit": 2,
        }
    )

    keys = [column["key"] for column in result["columns"]]
    assert keys == [
        "day_of_month",
        "2026-05:total_sales",
        "2026-06:total_sales",
        "delta:total_sales",
        "delta_pct:total_sales",
    ]
    assert result["total_rows"] == 31
    assert result["truncated"] is True
    assert result["rows"][0]["day_of_month"] == 1
    assert result["rows"][0]["2026-05:total_sales"] == 100.0
    assert result["rows"][0]["2026-06:total_sales"] == 150.0
    assert result["rows"][0]["delta:total_sales"] == 50.0
    assert result["rows"][0]["delta_pct:total_sales"] == 50.0
    assert repo.daily_comparison_calls[0]["level"] == "general"


@pytest.mark.asyncio
async def test_build_xlsx_sanitizes_filename_and_writes_config_sheet() -> None:
    service = ExportsService(FakeRepo())  # type: ignore[arg-type]

    content, filename = await service.build_xlsx(
        {
            "dataset": "stores",
            "months": ["2026-06"],
            "dimensions": ["site_code", "locatie"],
            "metrics": ["total_sales"],
            "filename": "../raport retail final",
        }
    )

    assert filename == "raport_retail_final.xlsx"
    wb = load_workbook(BytesIO(content), read_only=True)
    assert wb.sheetnames == ["Raport", "Configuratie"]
    config = wb["Configuratie"]
    assert config["A2"].value == "Dataset"
    assert config["B2"].value == "Magazine"
