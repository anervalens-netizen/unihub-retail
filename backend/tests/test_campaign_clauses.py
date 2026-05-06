"""Unit tests for campaign clause building and service helpers."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.campaigns import _campaign_clauses


class FakeRow(dict):
    """Dict subclass that mimics asyncpg Record for dict(row) calls."""
    def __getattr__(self, name: str):
        return self[name]


def test_campaign_clauses_no_filters():
    clauses, params = _campaign_clauses("2026-05", None, None, None, None, None, alias="agg")
    assert clauses == ["agg.import_month = $1"]
    assert params == ["2026-05"]


def test_campaign_clauses_all_filters():
    clauses, params = _campaign_clauses(
        "2026-05", "FirmaA", "RegionalB", "AsmC", "SITE01", "Agent1", alias="t"
    )
    assert len(clauses) == 6
    assert params == ["2026-05", "FirmaA", "RegionalB", "AsmC", "SITE01", "Agent1"]
    assert "t.firma = $2" in clauses
    assert "t.agent = $6" in clauses


def test_campaign_clauses_skips_toate():
    clauses, params = _campaign_clauses(
        "2026-05", "Toate", None, "Toti", None, None, alias="x"
    )
    assert clauses == ["x.import_month = $1"]
    assert params == ["2026-05"]


def test_campaign_clauses_partial_filters():
    clauses, params = _campaign_clauses(
        "2026-04", None, "Regional1", None, "SITE99", None, alias="agg"
    )
    assert len(clauses) == 3
    assert params == ["2026-04", "Regional1", "SITE99"]


class TestCampaignsServiceOverview:
    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock()
        repo.fetch_overview = AsyncMock()
        return repo

    @pytest.fixture
    def mock_pool(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo, mock_pool):
        from services.campaigns import CampaignsService
        return CampaignsService(mock_repo, mock_pool)

    @pytest.mark.asyncio
    async def test_overview_empty(self, service, mock_repo):
        mock_repo.fetch_overview.return_value = {
            "overview": None,
            "products": [],
            "stores": [],
        }
        result = await service.get_campaign_overview("2026-05", None, None, None, None, None)
        assert result.overview.month == "2026-05"
        assert result.overview.total_focus_sales == Decimal(0)
        assert result.products == []
        assert result.stores == []

    @pytest.mark.asyncio
    async def test_overview_with_data(self, service, mock_repo):
        overview_row = FakeRow(
            month="2026-05",
            total_focus_sales=Decimal("12345.67"),
            total_focus_qty=100,
            focus_share_pct=Decimal("15.5"),
            active_focus_products=42,
            active_focus_stores=10,
        )
        product_row = FakeRow(
            item_code="CL001",
            item_name="Product A",
            qty_total=50,
            sales_total=Decimal("5000"),
            store_count=5,
        )
        mock_repo.fetch_overview.return_value = {
            "overview": overview_row,
            "products": [product_row],
            "stores": [],
        }
        result = await service.get_campaign_overview("2026-05", None, None, None, None, None)
        assert result.overview.total_focus_sales == Decimal("12345.67")
        assert len(result.products) == 1
        assert result.products[0].item_code == "CL001"


class TestCampaignsServiceHistory:
    @pytest.fixture
    def service(self):
        from services.campaigns import CampaignsService
        repo = MagicMock()
        repo.fetch_history = AsyncMock(return_value=[])
        return CampaignsService(repo, MagicMock())

    @pytest.mark.asyncio
    async def test_history_empty(self, service):
        result = await service.get_focus_history("2026-05", 12, None, None, None, None, None)
        assert result.history == []

    @pytest.mark.asyncio
    async def test_history_with_filters(self, service):
        row = FakeRow(
            month="2026-04",
            total_focus_sales=Decimal("1000"),
            total_focus_qty=10,
            focus_share_pct=Decimal("5.0"),
            active_focus_products=5,
            active_focus_stores=3,
        )
        service.repo.fetch_history.return_value = [row]
        result = await service.get_focus_history(
            "2026-05", 6, "FirmaX", None, None, None, None
        )
        assert len(result.history) == 1
        assert result.history[0].month == "2026-04"
