"""Unit tests for campaign repository clause building and service helpers."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from repositories.campaigns import (
    _incentive_scope,
    _promo_scope,
    build_campaign_clauses,
    build_campaign_history_clauses,
)


class FakeRow(dict):
    """Dict subclass that mimics asyncpg Record for dict(row) calls."""
    def __getattr__(self, name: str):
        return self[name]


def test_campaign_clauses_no_filters():
    clauses, params = build_campaign_clauses("2026-05", None, None, None, None, None, alias="agg")
    assert clauses == ["agg.locatie NOT ILIKE 'TR %'", "agg.import_month = $1"]
    assert params == ["2026-05"]


def test_campaign_clauses_all_filters():
    clauses, params = build_campaign_clauses(
        "2026-05", "FirmaA", "RegionalB", "AsmC", "SITE01", "Agent1", alias="t"
    )
    assert len(clauses) == 4
    assert params == ["2026-05", "SITE01", "Agent1"]
    assert not any("t.firma" in clause for clause in clauses)
    assert not any("t.regional" in clause for clause in clauses)
    assert "t.site_code = ANY(string_to_array($2::TEXT, ','))" in clauses
    assert "t.agent = ANY(string_to_array($3::TEXT, ','))" in clauses


def test_campaign_clauses_skips_toate():
    clauses, params = build_campaign_clauses(
        "2026-05", "Toate", None, "Toti", None, None, alias="x"
    )
    assert clauses == ["x.locatie NOT ILIKE 'TR %'", "x.import_month = $1"]
    assert params == ["2026-05"]


def test_campaign_clauses_partial_filters():
    clauses, params = build_campaign_clauses(
        "2026-04", None, "Regional1", None, "SITE99", None, alias="agg"
    )
    assert len(clauses) == 3
    assert params == ["2026-04", "SITE99"]
    assert not any("agg.regional" in clause for clause in clauses)
    assert "agg.site_code = ANY(string_to_array($2::TEXT, ','))" in clauses


def test_campaign_history_clauses_site_code_scope_supports_comma_lists():
    focus_clauses, totals_clauses, params = build_campaign_history_clauses(
        "2026-06", 12, None, None, None, "CCTCIT,CTAUCH,CTCITYPRK", None
    )
    assert params == ["2026-06", 12, "CCTCIT,CTAUCH,CTCITYPRK"]
    assert "agg.site_code = ANY(string_to_array($3::TEXT, ','))" in focus_clauses
    assert "tot.site_code = ANY(string_to_array($3::TEXT, ','))" in totals_clauses


def test_current_promo_scope_uses_active_store_fields() -> None:
    clauses, params, store_join = _promo_scope(
        date(2026, 7, 1),
        date(2026, 7, 31),
        ["P1"],
        "2026-07",
        firma=None,
        regional="RM 1",
        asm=None,
        site_code=None,
        agent=None,
        current_scope=True,
        include_closed_stores=False,
    )

    assert params == [
        date(2026, 7, 1),
        date(2026, 7, 31),
        ["P1"],
        "2026-07",
        "RM 1",
    ]
    assert store_join == "JOIN stores s ON s.site_code = agg.site_code"
    assert "s.regional = ANY(string_to_array($5::TEXT, ','))" in clauses
    assert "s.is_active = TRUE" in clauses


def test_current_incentive_scope_can_include_closed_stores() -> None:
    clauses, _params, store_join = _incentive_scope(
        ["I1"],
        "2026-07",
        firma=None,
        regional=None,
        asm=None,
        site_code=None,
        agent=None,
        current_scope=True,
        include_closed_stores=True,
    )

    assert store_join == "JOIN stores s ON s.site_code = agg.site_code"
    assert "s.is_active = TRUE" not in clauses


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

    @pytest.mark.asyncio
    async def test_history_site_code_scope_supports_comma_lists(self, service):
        await service.get_focus_history(
            "2026-06", 12, None, None, None, "CCTCIT,CTAUCH,CTCITYPRK", None
        )
        assert service.repo.fetch_history.call_args.args == ("2026-06", 12)
        assert service.repo.fetch_history.call_args.kwargs == {
            "firma": None,
            "regional": None,
            "asm": None,
            "site_code": "CCTCIT,CTAUCH,CTCITYPRK",
            "agent": None,
        }
