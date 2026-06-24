"""Unit tests for DashboardService — mock-based, no DB needed."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import DashboardSummary, DailySalesPoint, PremiumGlassAnalysis, PremiumGlassSummary
from services.dashboard.queries import DashboardCampaignContext
from services.dashboard_service import DashboardService


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


def _make_summary_row(**overrides) -> FakeRow:
    defaults = dict(
        month="2026-05",
        total_sales=Decimal("100000"),
        total_target=Decimal("120000"),
        target_progress_pct=Decimal("83.3"),
        forecast_sales=Decimal("110000"),
        forecast_target_progress_pct=Decimal("91.7"),
        total_quantity=500,
        total_receipts=300,
        proc_bon2acc=Decimal("60.0"),
        prc_focus_acc_qty=Decimal("25.0"),
        total_stores=15,
        total_agents=20,
        working_days=22,
        daily_average=Decimal("4545.45"),
        is_month_final=False,
        last_sale_date=date(2026, 5, 6),
        imported_day_of_month=6,
        days_in_month=31,
        cartele_qty=10,
    )
    defaults.update(overrides)
    return FakeRow(**defaults)


def _empty_premium_glass(month: str = "2026-05") -> PremiumGlassAnalysis:
    return PremiumGlassAnalysis(summary=PremiumGlassSummary(month=month))


def _empty_campaign_context() -> DashboardCampaignContext:
    return DashboardCampaignContext(
        config_error=None,
        promotion_definitions=[],
        promotion_definition=None,
        promotion_error=None,
        incentive_campaign=None,
        promotion_results=[],
        promo_excluded_units={},
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.fetch_summary = AsyncMock(return_value=None)
    repo.fetch_daily_sales = AsyncMock(return_value=[])
    repo.fetch_monthly_history = AsyncMock(return_value=[])
    repo.fetch_year_history_agg = AsyncMock(return_value=None)
    repo.fetch_year_history_monthly = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


@pytest.fixture
def service(mock_repo, mock_pool):
    return DashboardService(mock_repo, mock_pool)


class TestGetSummary:
    @pytest.mark.asyncio
    async def test_summary_empty(self, service, mock_repo):
        mock_repo.fetch_summary.return_value = None
        result = await service.get_summary("2026-05", None, None, None, None, None)
        assert isinstance(result, DashboardSummary)
        assert result.total_sales == Decimal(0)
        assert result.total_target == Decimal(0)
        assert result.month == "2026-05"
        assert result.is_month_final is True

    @pytest.mark.asyncio
    async def test_summary_with_data(self, service, mock_repo):
        mock_repo.fetch_summary.return_value = _make_summary_row()
        result = await service.get_summary("2026-05", None, None, None, None, None)
        assert result.total_sales == Decimal("100000")
        assert result.total_agents == 20
        assert result.cartele_qty == 10

    @pytest.mark.asyncio
    async def test_summary_with_filters(self, service, mock_repo):
        mock_repo.fetch_summary.return_value = _make_summary_row(total_sales=Decimal("5000"))
        result = await service.get_summary("2026-05", "FirmaA", "R1", "A1", "SITE01", "Agent1")
        assert result.total_sales == Decimal("5000")
        call = mock_repo.fetch_summary.call_args
        assert call[0][1] == ["2026-05", "SITE01", "Agent1"]


class TestGetDailySales:
    @pytest.mark.asyncio
    async def test_daily_empty(self, service, mock_repo):
        result = await service.get_daily_sales("2026-05", None, None, None, None, None)
        assert result == []

    @pytest.mark.asyncio
    async def test_daily_with_data(self, service, mock_repo):
        mock_repo.fetch_daily_sales.return_value = [
            FakeRow(sale_date=date(2026, 5, 1), total_sales=Decimal("5000"), total_quantity=50, receipt_count=30),
            FakeRow(sale_date=date(2026, 5, 2), total_sales=Decimal("6000"), total_quantity=60, receipt_count=35),
        ]
        result = await service.get_daily_sales("2026-05", None, None, None, None, None)
        assert len(result) == 2
        assert isinstance(result[0], DailySalesPoint)
        assert result[0].total_sales == Decimal("5000")


class TestGetMonthlyHistory:
    @pytest.mark.asyncio
    async def test_history_empty(self, service, mock_repo):
        result = await service.get_monthly_history("2026-05", 12, None, None, None, None, None)
        assert result.history == []

    @pytest.mark.asyncio
    async def test_history_with_data(self, service, mock_repo):
        mock_repo.fetch_monthly_history.return_value = [
            FakeRow(
                month="2026-04", total_sales=Decimal("90000"), total_target=Decimal("100000"),
                target_progress_pct=Decimal("90.0"), total_quantity=450, total_receipts=280,
                proc_bon2acc=Decimal("62.0"), prc_focus_acc_qty=Decimal("22.0"),
                total_stores=14, total_agents=19, working_days=21, daily_average=Decimal("4285.71"),
            ),
        ]
        result = await service.get_monthly_history("2026-05", 12, None, None, None, None, None)
        assert len(result.history) == 1
        assert result.history[0].month == "2026-04"

    @pytest.mark.asyncio
    async def test_history_with_filters(self, service, mock_repo):
        mock_repo.fetch_monthly_history.return_value = []
        result = await service.get_monthly_history("2026-05", 6, "FirmaA", "R1", None, None, None)
        assert result.history == []
        call = mock_repo.fetch_monthly_history.call_args
        assert len(call[0][1]) >= 4

    @pytest.mark.asyncio
    async def test_history_with_site_filter_ignores_parent_scope(self, service, mock_repo):
        mock_repo.fetch_monthly_history.return_value = []
        result = await service.get_monthly_history("2026-05", 12, "FirmaA", "R1", None, "SITE01", None)
        assert result.history == []
        call = mock_repo.fetch_monthly_history.call_args
        assert call[0][1] == ["2026-05", 12, "SITE01"]

    @pytest.mark.asyncio
    async def test_current_scope_regional_filter_matches_current_manager(self, service, mock_repo):
        mock_repo.fetch_monthly_history.return_value = []
        result = await service.get_monthly_history(
            "2026-05", 12, None, "Manager1", None, None, None, current_scope=True
        )
        assert result.history == []
        clauses = mock_repo.fetch_monthly_history.call_args[0][0]
        assert "(s.regional = ANY(string_to_array($3::TEXT, ',')) OR s.asm = ANY(string_to_array($3::TEXT, ',')))" in clauses
        assert "s.regional = ANY(string_to_array($3::TEXT, ','))" not in [
            clause for clause in clauses if not clause.startswith("(")
        ]

    @pytest.mark.asyncio
    async def test_current_scope_explicit_asm_stays_strict(self, service, mock_repo):
        mock_repo.fetch_monthly_history.return_value = []
        result = await service.get_monthly_history(
            "2026-05", 12, None, "Regional1", "Asm1", None, None, current_scope=True
        )
        assert result.history == []
        clauses = mock_repo.fetch_monthly_history.call_args[0][0]
        assert "s.regional = ANY(string_to_array($3::TEXT, ','))" in clauses
        assert "s.asm = ANY(string_to_array($4::TEXT, ','))" in clauses
        assert not any(clause.startswith("(s.regional") for clause in clauses)


class TestGetHistoryByYear:
    @pytest.mark.asyncio
    async def test_year_2024_no_data(self, service, mock_repo):
        result = await service.get_history_by_year(2024, None, None, None, None, None)
        assert result.points == []

    @pytest.mark.asyncio
    async def test_year_2024_with_monthly(self, service, mock_repo):
        mock_repo.fetch_year_history_monthly.return_value = [
            FakeRow(import_month="2024-09", total_sales=Decimal("80000"), total_target=Decimal("90000"), total_quantity=400),
            FakeRow(import_month="2024-10", total_sales=Decimal("85000"), total_target=Decimal("90000"), total_quantity=420),
        ]
        result = await service.get_history_by_year(2024, None, None, None, None, None)
        assert len(result.points) == 2
        assert result.points[0].label == "Sep"
        assert result.points[1].label == "Oct"

    @pytest.mark.asyncio
    async def test_year_2023_with_aggregate(self, service, mock_repo):
        mock_repo.fetch_year_history_agg.return_value = FakeRow(
            total_sales=Decimal("500000"), total_quantity=5000,
        )
        mock_repo.fetch_year_history_monthly.return_value = [
            FakeRow(import_month="2023-09", total_sales=Decimal("70000"), total_target=Decimal("80000"), total_quantity=350),
        ]
        result = await service.get_history_by_year(2023, None, None, None, None, None)
        assert len(result.points) == 2
        assert result.points[0].is_aggregate is True
        assert result.points[0].label == "Ian–Aug"
        assert result.points[1].is_aggregate is False

    @pytest.mark.asyncio
    async def test_year_2022_aggregate(self, service, mock_repo):
        mock_repo.fetch_year_history_agg.return_value = FakeRow(
            total_sales=Decimal("600000"), total_quantity=6000,
        )
        mock_repo.fetch_year_history_monthly.return_value = []
        result = await service.get_history_by_year(2022, None, None, None, None, None)
        assert len(result.points) == 1
        assert result.points[0].label == "2022"

    @pytest.mark.asyncio
    async def test_year_with_agent_skips_aggregate(self, service, mock_repo):
        mock_repo.fetch_year_history_monthly.return_value = []
        result = await service.get_history_by_year(2023, None, None, None, None, "Agent1")
        mock_repo.fetch_year_history_agg.assert_not_awaited()
        assert result.points == []

    @pytest.mark.asyncio
    async def test_year_with_filters(self, service, mock_repo):
        mock_repo.fetch_year_history_monthly.return_value = [
            FakeRow(import_month="2025-03", total_sales=Decimal("40000"), total_target=Decimal("50000"), total_quantity=200),
        ]
        result = await service.get_history_by_year(2025, "FirmaA", "R1", None, None, None)
        assert len(result.points) == 1
        assert result.points[0].label == "Mar"


class TestGetSpecialCards:
    @pytest.mark.asyncio
    async def test_special_cards(self, service):
        with (
            patch("services.dashboard_service._get_special_cards_data", new_callable=AsyncMock) as mock_fn,
            patch(
                "services.dashboard_service.get_premium_glass_analysis",
                new_callable=AsyncMock,
                return_value=_empty_premium_glass(),
            ),
        ):
            mock_fn.return_value = []
            result = await service.get_special_cards("2026-05", None, None, None, None, None)
            assert [card.key for card in result.cards] == ["premium_glass"]
            mock_fn.assert_awaited_once()


class TestGetDashboardAll:
    @pytest.mark.asyncio
    @patch("services.dashboard_service._get_special_cards_data", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_agent_stats_rows", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_store_stats_rows", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._enrich_store_stats_with_campaign", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_period_comparison", new_callable=AsyncMock, return_value=None)
    @patch("services.dashboard_service._fetch_category_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_receipt_bucket_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_focus_subcategory_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_brand_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.dashboard_service._fetch_regional_stats", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_asm_stats", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service.get_premium_glass_analysis", new_callable=AsyncMock, return_value=_empty_premium_glass())
    async def test_dashboard_all_empty(
        self, mock_premium, mock_asm, mock_regional, mock_promo, mock_brand, mock_focus_sub,
        mock_receipt, mock_cat, mock_period, mock_enrich, mock_stores,
        mock_agents, mock_specials, service, mock_repo
    ):
        from models import PromoIncentiveSummary
        mock_promo.return_value = PromoIncentiveSummary()
        mock_repo.fetch_summary.return_value = None

        campaign_context = _empty_campaign_context()
        with patch(
            "services.dashboard_service._load_dashboard_campaign_context",
            new_callable=AsyncMock,
            return_value=campaign_context,
        ) as mock_load_context:
            result = await service.get_dashboard_all(
                "2026-05", None, None, None, None, None
            )
        assert result.summary.total_sales == Decimal(0)
        assert result.agents == []
        assert result.stores == []
        assert result.daily == []
        assert [card.key for card in result.special_cards] == ["premium_glass"]
        assert result.premium_glass is not None
        assert result.regionals == []
        assert result.asms == []
        mock_load_context.assert_awaited_once()
        assert mock_promo.await_args.kwargs["campaign_context"] is campaign_context
        assert mock_specials.await_args.kwargs["campaign_context"] is campaign_context

    @pytest.mark.asyncio
    @patch("services.dashboard_service._get_special_cards_data", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_agent_stats_rows", new_callable=AsyncMock)
    @patch("services.dashboard_service._fetch_store_stats_rows", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._enrich_store_stats_with_campaign", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_period_comparison", new_callable=AsyncMock, return_value=None)
    @patch("services.dashboard_service._fetch_category_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_receipt_bucket_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_focus_subcategory_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_brand_mix", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_promo_incentive_summary", new_callable=AsyncMock)
    @patch("services.dashboard_service._fetch_regional_stats", new_callable=AsyncMock, return_value=[])
    @patch("services.dashboard_service._fetch_asm_stats", new_callable=AsyncMock, return_value=[])
    async def test_dashboard_all_with_agent_data(
        self, mock_asm, mock_regional, mock_promo, mock_brand, mock_focus_sub,
        mock_receipt, mock_cat, mock_period, mock_enrich, mock_stores,
        mock_agents, mock_specials, service, mock_repo
    ):
        from models import PromoIncentiveSummary
        mock_promo.return_value = PromoIncentiveSummary()
        mock_repo.fetch_summary.return_value = _make_summary_row()
        mock_agents.return_value = [
            FakeRow(
                import_month="2026-05", agent="A1", site_code="S1", locatie="Store 1",
                firma="F1", regional="R1", asm="ASM1", acc_qty_realizat=50,
                nr_bonuri=30, nr_bon2acc=10, proc_bon2acc=Decimal("33.3"),
                total_vanzari=Decimal("5000"), zile_lucrate=22,
                medie_zilnica=Decimal("227.3"), acc_focus_qty=10,
                prc_focus_acc_qty=Decimal("20.0"), target=Decimal("6000"),
                proc_realizare_target=Decimal("83.3"),
                promo_qty=5, incentive_qty=3,
            ),
        ]

        result = await service.get_dashboard_all("2026-05", None, None, None, None, None)
        assert result.summary.total_sales == Decimal("100000")
        assert len(result.agents) == 1
        assert result.agents[0].agent == "A1"
