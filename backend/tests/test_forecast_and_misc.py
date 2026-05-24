"""Tests for forecast.py, visits_report.py, and misc coverage gaps."""
from __future__ import annotations

from unittest.mock import AsyncMock

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


class TestProductListsImport:
    def test_imports(self):
        from services.product_lists import get_data_dir, get_repo_root
        assert get_data_dir is not None
        assert get_repo_root is not None
