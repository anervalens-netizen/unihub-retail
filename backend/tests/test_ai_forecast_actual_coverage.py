from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from repositories.ai_forecast import AiForecastRepository


class Connection:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.cutoff_query = ""
        self.daily_query = ""

    async def fetchval(self, query: str, month: str) -> date:
        self.cutoff_query = query
        assert month == "2026-08"
        return date(2026, 8, 2)

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        if self.fetch_calls == 1:
            return [
                {
                    "site_code": "S1",
                    "locatie": "Store 1",
                    "firma": "Mobiup",
                    "regional": "R1",
                    "asm": "A1",
                    "forecast_sales": Decimal("30"),
                    "expected_sales_to_date": Decimal("22"),
                    "actual_sales": Decimal("-3"),
                }
            ]
        self.daily_query = query
        return [
            {
                "forecast_date": date(2026, 8, 1),
                "forecast_sales": Decimal("10"),
                "actual_sales": Decimal("0"),
                "has_actual": True,
            },
            {
                "forecast_date": date(2026, 8, 2),
                "forecast_sales": Decimal("12"),
                "actual_sales": Decimal("-3"),
                "has_actual": True,
            },
            {
                "forecast_date": date(2026, 8, 3),
                "forecast_sales": Decimal("8"),
                "actual_sales": Decimal("0"),
                "has_actual": False,
            },
        ]


class Pool:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    @asynccontextmanager
    async def acquire(self):
        yield self.connection


def test_actual_coverage_uses_official_cutoff_not_positive_sales() -> None:
    async def scenario() -> None:
        connection = Connection()
        repository = AiForecastRepository(Pool(connection))  # type: ignore[arg-type]

        result = await repository.fetch_response_rows(
            run_id=7,
            forecast_month="2026-08",
            metric="sales_value",
            firma=None,
            regional=None,
            asm=None,
            site_code=None,
        )

        assert result is not None
        assert result["actual_last_date"] == date(2026, 8, 2)
        assert [point["has_actual"] for point in result["daily"]] == [True, True, False]
        assert result["daily"][0]["actual_sales"] == Decimal("0")
        assert result["daily"][1]["actual_sales"] == Decimal("-3")
        assert "reporting_sales_cutoff_v1" in connection.cutoff_query
        assert "sales_generation_heads" not in connection.cutoff_query
        assert "fd.forecast_date <=" in connection.daily_query

    asyncio.run(scenario())


def test_ai_forecast_repeated_store_scope_dominates_hierarchy() -> None:
    clause, params = AiForecastRepository._filter_clause(
        firma="Wrong company",
        regional="Wrong manager",
        asm="Wrong ASM",
        site_code=["B, Nord", "B, Nord", "C"],
    )

    assert params == [["B, Nord", "C"]]
    assert clause == "s.locatie NOT ILIKE 'TR %' AND s.site_code = ANY($1::TEXT[])"


def test_cutoff_read_model_preserves_authority_and_web_least_privilege() -> None:
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "backend/db/migrations/064_ai_forecast_cutoff_read_model.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE OR REPLACE VIEW reporting_sales_cutoff_v1" in migration
    assert "sales_generation_heads AS head" in migration
    assert "head.snapshot_id" in migration
    assert "COALESCE(snapshot.cutoff_date, MAX(transaction.sale_date))" in migration
    assert "GRANT SELECT ON TABLE reporting_sales_cutoff_v1 TO unihub_web_read" in migration
    assert "GRANT SELECT ON TABLE sales_generation_heads TO unihub_web_read" not in migration
