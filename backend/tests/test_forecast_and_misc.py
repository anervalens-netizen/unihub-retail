"""Tests for forecast.py, visits_report.py, and misc coverage gaps."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.forecast import get_forecast_factor


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


class TestForecastFactor:
    @pytest.mark.asyncio
    async def test_no_meta(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await get_forecast_factor(conn, "2026-05")
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_final_month(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = FakeRow(is_final=True, last_sale_day=31, days_in_month=31)
        result = await get_forecast_factor(conn, "2026-05")
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_partial_month(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = FakeRow(is_final=False, last_sale_day=15, days_in_month=30)
        result = await get_forecast_factor(conn, "2026-05")
        assert result == 2.0

    @pytest.mark.asyncio
    async def test_no_last_sale_day(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = FakeRow(is_final=False, last_sale_day=None, days_in_month=31)
        result = await get_forecast_factor(conn, "2026-05")
        assert result == 1.0

    @pytest.mark.asyncio
    async def test_zero_last_sale_day(self):
        conn = AsyncMock()
        conn.fetchrow.return_value = FakeRow(is_final=False, last_sale_day=0, days_in_month=31)
        result = await get_forecast_factor(conn, "2026-05")
        assert result == 1.0


class TestVisitsReportImport:
    def test_imports(self):
        from services.visits_report import VisitsReportService
        assert VisitsReportService is not None

    @pytest.mark.asyncio
    async def test_undated_visit_is_returned_in_explicit_bucket(self):
        from services.visits_report import VisitsReportService

        repo = MagicMock()
        repo.db_exists.return_value = True
        repo.query_tree.return_value = [
            {
                "id": "visit-1",
                "team_leader_name": "TL",
                "data_raport": None,
                "magazin": "Magazin",
                "locatie": "Bucuresti",
                "ora_trimitere": None,
                "completion_pct": 0,
                "firma": "Firma",
                "foto1": None,
                "foto2": None,
                "foto3": None,
                "foto4": None,
            }
        ]
        service = VisitsReportService(repo)
        service._resolve_store_scope = AsyncMock(return_value=({}, None))

        result = await service.get_visits_tree(None, None, None, None)

        assert result.team_leaders[0].months[0].month == "—"
        assert result.team_leaders[0].months[0].days[0].date == "—"
        assert result.team_leaders[0].months[0].nr_vizite == 1


class TestProductListsImport:
    def test_imports(self):
        from services.product_lists import get_data_dir, get_repo_root
        assert get_data_dir is not None
        assert get_repo_root is not None
