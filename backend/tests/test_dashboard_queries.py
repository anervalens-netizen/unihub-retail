"""Unit tests for services/dashboard/queries.py — mock conn, test param assembly and call patterns."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from services.dashboard.queries import (
    _enrich_store_stats_with_campaign,
    _fetch_agent_stats_rows,
    _fetch_asm_stats,
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_focus_subcategory_mix,
    _fetch_period_comparison,
    _fetch_period_comparison_cutoff_day,
    _fetch_promo_incentive_summary,
    _fetch_receipt_bucket_mix,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
    _get_store_incentive_multipliers,
)


class FakeRow(dict):
    def __getattr__(self, name: str):
        return self[name]


@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    return conn


class TestStoreIncentiveMultipliers:
    @pytest.mark.asyncio
    async def test_no_rows(self, mock_conn):
        mock_conn.fetchrow.return_value = FakeRow(is_final=True, last_sale_day=None, days_in_month=31)
        mock_conn.fetch.return_value = []
        mults, achs = await _get_store_incentive_multipliers(mock_conn, "2026-05", None, None, None, None)
        assert mults == {}
        assert achs == {}

    @pytest.mark.asyncio
    async def test_with_stores(self, mock_conn):
        mock_conn.fetchrow.return_value = FakeRow(is_final=True, last_sale_day=15, days_in_month=31)
        mock_conn.fetch.return_value = [
            FakeRow(site_code="S1", store_sales=Decimal("50000"), target=Decimal("60000")),
            FakeRow(site_code="S2", store_sales=Decimal("10000"), target=Decimal("0")),
        ]
        mults, achs = await _get_store_incentive_multipliers(mock_conn, "2026-05", None, None, None, None)
        assert "S1" in mults
        assert "S2" in mults
        assert achs["S2"] is None

    @pytest.mark.asyncio
    async def test_forecast_factor(self, mock_conn):
        mock_conn.fetchrow.return_value = FakeRow(is_final=False, last_sale_day=15, days_in_month=30)
        mock_conn.fetch.return_value = [
            FakeRow(site_code="S1", store_sales=Decimal("30000"), target=Decimal("60000")),
        ]
        mults, achs = await _get_store_incentive_multipliers(mock_conn, "2026-05", None, None, None, None)
        assert achs["S1"] is not None
        assert achs["S1"] == pytest.approx(1.0, abs=0.1)


class TestFetchStoreStatsRows:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_store_stats_rows(mock_conn, "2026-05", None, None, None, None, None)
        assert result == []
        mock_conn.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_filters(self, mock_conn):
        await _fetch_store_stats_rows(mock_conn, "2026-05", "FirmaA", "R1", None, "SITE01", None)
        call = mock_conn.fetch.call_args
        assert len(call[0]) >= 2
        sql = call[0][0]
        assert "firma" in sql.lower() or "$2" in sql


class TestFetchAgentStatsRows:
    @pytest.mark.asyncio
    async def test_empty_returns_empty(self, mock_conn):
        result = await _fetch_agent_stats_rows(mock_conn, "2026-05", None, None, None, None, None)
        assert result == []

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition", return_value=(None, None))
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_with_rows_no_campaign(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(
                import_month="2026-05", agent="A1", site_code="S1", locatie="Store 1",
                firma="F1", regional="R1", asm="ASM1",
                acc_qty_realizat=50, nr_bonuri=30, nr_bon2acc=10,
                proc_bon2acc=Decimal("33.3"), total_vanzari=Decimal("5000"),
                zile_lucrate=22, medie_zilnica=Decimal("227.3"),
                acc_focus_qty=10, prc_focus_acc_qty=Decimal("20.0"),
                target=Decimal("6000"), proc_realizare_target=Decimal("83.3"),
            ),
        ]
        result = await _fetch_agent_stats_rows(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["agent"] == "A1"


class TestFetchAgentStatsWithCampaign:
    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition")
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_agent_stats_with_promo(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_promo.return_value = ({"item_codes": ["P1"]}, None)
        base_row = FakeRow(
            import_month="2026-05", agent="A1", site_code="S1", locatie="Store 1",
            firma="F1", regional="R1", asm="ASM1",
            acc_qty_realizat=50, nr_bonuri=30, nr_bon2acc=10,
            proc_bon2acc=Decimal("33.3"), total_vanzari=Decimal("5000"),
            zile_lucrate=22, medie_zilnica=Decimal("227.3"),
            acc_focus_qty=10, prc_focus_acc_qty=Decimal("20.0"),
            target=Decimal("6000"), proc_realizare_target=Decimal("83.3"),
        )
        metric_row = FakeRow(import_month="2026-05", site_code="S1", agent="A1", promo_qty=12, incentive_qty=0)
        mock_conn.fetch.side_effect = [[base_row], [metric_row]]
        result = await _fetch_agent_stats_rows(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["promo_qty"] == 12


class TestEnrichStoreStatsWithCampaign:
    @pytest.mark.asyncio
    async def test_empty_rows(self, mock_conn):
        result = await _enrich_store_stats_with_campaign(mock_conn, [], "2026-05", None, None, None, None, None)
        assert result == []

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition", return_value=(None, None))
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_no_campaign_data(self, mock_inc, mock_promo, mock_config, mock_conn):
        rows = [
            {"import_month": "2026-05", "site_code": "S1", "total_vanzari": Decimal("5000")},
        ]
        result = await _enrich_store_stats_with_campaign(mock_conn, rows, "2026-05", None, None, None, None, None)
        assert result[0]["promo_qty"] == 0
        assert result[0]["incentive_qty"] == 0

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition")
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_with_promo_campaign(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_promo.return_value = ({"item_codes": ["P1"]}, None)
        mock_conn.fetch.return_value = [
            FakeRow(import_month="2026-05", site_code="S1", promo_qty=15, incentive_qty=0),
        ]
        rows = [
            {"import_month": "2026-05", "site_code": "S1", "total_vanzari": Decimal("5000")},
        ]
        result = await _enrich_store_stats_with_campaign(mock_conn, rows, "2026-05", None, None, None, None, None)
        assert result[0]["promo_qty"] == 15


class TestFetchRegionalStats:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_regional_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert result == []
        mock_conn.fetch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_with_data(self, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(
                regional="R1", total_vanzari=Decimal("50000"), qty_total=500,
                nr_bonuri=300, nr_agenti=10, zile_active=22, target=Decimal("60000"),
                proc_realizare_target=Decimal("83.3"), promo_qty=20, incentive_qty=15,
                medie_zilnica=Decimal("2272"), proc_bon2acc=Decimal("60.0"),
                prc_focus_acc_qty=Decimal("25.0"),
            ),
        ]
        result = await _fetch_regional_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["regional"] == "R1"


class TestFetchAsmStats:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_asm_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert result == []


class TestFetchPeriodComparison:
    @pytest.mark.asyncio
    async def test_cutoff_uses_last_sale_day_for_partial_month(self, mock_conn):
        mock_conn.fetchrow.return_value = FakeRow(
            is_final=False,
            last_sale_day=6,
            days_in_month=31,
        )
        result = await _fetch_period_comparison_cutoff_day(mock_conn, "2026-05")
        assert result == 6

    @pytest.mark.asyncio
    async def test_cutoff_uses_full_month_for_final_month(self, mock_conn):
        mock_conn.fetchrow.return_value = FakeRow(
            is_final=True,
            last_sale_day=6,
            days_in_month=31,
        )
        result = await _fetch_period_comparison_cutoff_day(mock_conn, "2026-05")
        assert result == 31

    @pytest.mark.asyncio
    async def test_no_data_returns_default(self, mock_conn):
        result = await _fetch_period_comparison(mock_conn, target_metric="sales",
                                                 month="2026-05", firma=None, regional=None,
                                                 asm=None, site_code=None, agent=None,
                                                 cutoff_day=31)
        assert result is not None
        assert result.current.total_sales == Decimal(0)
        assert result.previous.month == "2026-04"
        assert result.year_over_year.month == "2025-05"

    @pytest.mark.asyncio
    async def test_with_data(self, mock_conn):
        row = FakeRow(
            total_sales=Decimal("100000"), total_quantity=500, total_receipts=300,
            cartele_qty=12,
            working_days=22, daily_average=Decimal("4545"), avg_receipt_value=Decimal("333"),
            medie_produs=Decimal("200"),
            proc_bon2acc=Decimal("60.0"), prc_focus_acc_qty=Decimal("25.0"),
        )
        mock_conn.fetchrow.return_value = row
        result = await _fetch_period_comparison(mock_conn, target_metric="sales",
                                                 month="2026-05", firma=None, regional=None,
                                                 asm=None, site_code=None, agent=None,
                                                 cutoff_day=31)
        assert result is not None

    @pytest.mark.asyncio
    async def test_partial_month_limits_previous_periods_to_same_day_range(self, mock_conn):
        meta_row = FakeRow(is_final=False, last_sale_day=6, days_in_month=31)
        data_row = FakeRow(
            total_sales=Decimal("100000"), total_quantity=500, total_receipts=300,
            cartele_qty=12,
            working_days=6, daily_average=Decimal("16666.67"), avg_receipt_value=Decimal("333.33"),
            medie_produs=Decimal("200"),
            proc_bon2acc=Decimal("60.0"), prc_focus_acc_qty=Decimal("25.0"),
        )
        mock_conn.fetchrow.side_effect = [meta_row, data_row, data_row, data_row]

        result = await _fetch_period_comparison(mock_conn, target_metric="sales",
                                                month="2026-05", firma=None, regional=None,
                                                asm=None, site_code=None, agent=None)

        assert result.current.day_range == "01-06"
        assert result.previous.day_range == "01-06"
        assert result.year_over_year.day_range == "01-06"
        assert result.current.cartele_qty == 12

    @pytest.mark.asyncio
    async def test_historical_periods_are_limited_to_current_store_cohort(self, mock_conn):
        data_row = FakeRow(
            total_sales=Decimal("100000"), total_quantity=500, total_receipts=300,
            cartele_qty=12,
            working_days=22, daily_average=Decimal("4545"), avg_receipt_value=Decimal("333"),
            medie_produs=Decimal("200"),
            proc_bon2acc=Decimal("60.0"), prc_focus_acc_qty=Decimal("25.0"),
        )
        mock_conn.fetch.return_value = [FakeRow(site_code="OPEN01"), FakeRow(site_code="OPEN02")]
        mock_conn.fetchrow.return_value = data_row

        await _fetch_period_comparison(mock_conn, target_metric="sales",
                                       month="2026-05", firma=None, regional=None,
                                       asm=None, site_code=None, agent=None,
                                       cutoff_day=26)

        previous_call = mock_conn.fetchrow.call_args_list[1]
        yoy_call = mock_conn.fetchrow.call_args_list[2]
        assert "agg.site_code = ANY($4::TEXT[])" in previous_call.args[0]
        assert "c.site_code = ANY($4::TEXT[])" in previous_call.args[0]
        assert previous_call.args[4] == ["OPEN01", "OPEN02"]
        assert yoy_call.args[4] == ["OPEN01", "OPEN02"]

    @pytest.mark.asyncio
    async def test_historical_cohort_does_not_reapply_current_regional_scope(self, mock_conn):
        data_row = FakeRow(
            total_sales=Decimal("100000"), total_quantity=500, total_receipts=300,
            cartele_qty=12,
            working_days=22, daily_average=Decimal("4545"), avg_receipt_value=Decimal("333"),
            medie_produs=Decimal("200"),
            proc_bon2acc=Decimal("60.0"), prc_focus_acc_qty=Decimal("25.0"),
        )
        mock_conn.fetch.return_value = [FakeRow(site_code="MOVED01")]
        mock_conn.fetchrow.return_value = data_row

        await _fetch_period_comparison(mock_conn, target_metric="sales",
                                       month="2026-05", firma="Retail", regional="RM curent",
                                       asm=None, site_code=None, agent="AG01",
                                       cutoff_day=26)

        current_sql = mock_conn.fetchrow.call_args_list[0].args[0]
        previous_call = mock_conn.fetchrow.call_args_list[1]
        previous_sql = previous_call.args[0]
        assert "agg.regional = ANY" in current_sql
        assert "agg.regional = ANY" not in previous_sql
        assert "agg.firma = ANY" not in previous_sql
        assert "agg.agent = ANY" in previous_sql
        assert previous_call.args[4:] == ("AG01", ["MOVED01"])


class TestFetchCategoryMix:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_category_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                           asm=None, site_code=None, agent=None)
        assert result == []


class TestFetchReceiptBucketMix:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_receipt_bucket_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                                 asm=None, site_code=None, agent=None)
        assert result == []


class TestFetchFocusSubcategoryMix:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_focus_subcategory_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                                    asm=None, site_code=None, agent=None)
        assert result == []


class TestFetchBrandMix:
    @pytest.mark.asyncio
    async def test_empty(self, mock_conn):
        result = await _fetch_brand_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                        asm=None, site_code=None, agent=None)
        assert result == []


class TestFetchRegionalStatsWithCampaign:
    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition", return_value=(None, None))
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_regional_with_rows_no_campaign(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(import_month="2026-05", regional="R1", total_vanzari=Decimal("50000"),
                    qty_total=500, nr_bonuri=300, nr_agenti=10, zile_active=22,
                    target=Decimal("60000"), proc_realizare_target=Decimal("83.3"),
                    medie_zilnica=Decimal("2272"), proc_bon2acc=Decimal("60.0"),
                    prc_focus_acc_qty=Decimal("25.0")),
        ]
        result = await _fetch_regional_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["promo_qty"] == 0

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition")
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_regional_with_promo(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_promo.return_value = ({"item_codes": ["P1"]}, None)
        base_row = FakeRow(import_month="2026-05", regional="R1", total_vanzari=Decimal("50000"),
                    qty_total=500, nr_bonuri=300, nr_agenti=10, zile_active=22,
                    target=Decimal("60000"), proc_realizare_target=Decimal("83.3"),
                    medie_zilnica=Decimal("2272"), proc_bon2acc=Decimal("60.0"),
                    prc_focus_acc_qty=Decimal("25.0"))
        metric_row = FakeRow(import_month="2026-05", regional="R1", promo_qty=25, incentive_qty=0)
        mock_conn.fetch.side_effect = [[base_row], [metric_row]]
        result = await _fetch_regional_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["promo_qty"] == 25


class TestFetchAsmStatsWithCampaign:
    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition", return_value=(None, None))
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_asm_with_rows_no_campaign(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(import_month="2026-05", asm="ASM1", regional="R1",
                    total_vanzari=Decimal("30000"), qty_total=300,
                    nr_bonuri=200, nr_agenti=5, zile_active=22,
                    target=Decimal("40000"), proc_realizare_target=Decimal("75.0"),
                    medie_zilnica=Decimal("1363"), proc_bon2acc=Decimal("55.0"),
                    prc_focus_acc_qty=Decimal("20.0")),
        ]
        result = await _fetch_asm_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["promo_qty"] == 0

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition")
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_asm_with_promo(self, mock_inc, mock_promo, mock_config, mock_conn):
        mock_promo.return_value = ({"item_codes": ["P1"]}, None)
        base_row = FakeRow(import_month="2026-05", asm="ASM1", regional="R1",
                    total_vanzari=Decimal("30000"), qty_total=300,
                    nr_bonuri=200, nr_agenti=5, zile_active=22,
                    target=Decimal("40000"), proc_realizare_target=Decimal("75.0"),
                    medie_zilnica=Decimal("1363"), proc_bon2acc=Decimal("55.0"),
                    prc_focus_acc_qty=Decimal("20.0"))
        metric_row = FakeRow(import_month="2026-05", regional="R1", asm="ASM1", promo_qty=30, incentive_qty=5)
        mock_conn.fetch.side_effect = [[base_row], [metric_row]]
        result = await _fetch_asm_stats(mock_conn, "2026-05", None, None, None, None, None)
        assert len(result) == 1
        assert result[0]["promo_qty"] == 30


class TestFetchCategoryMixWithData:
    @pytest.mark.asyncio
    async def test_with_rows(self, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(category="Huse", sales_total=Decimal("30000"), quantity_total=300, share_pct=Decimal("60.0")),
            FakeRow(category="Folii", sales_total=Decimal("20000"), quantity_total=200, share_pct=Decimal("40.0")),
        ]
        result = await _fetch_category_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                           asm=None, site_code=None, agent=None)
        assert len(result) == 2
        assert result[0].category == "Huse"


class TestFetchReceiptBucketMixWithData:
    @pytest.mark.asyncio
    async def test_with_rows(self, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(bucket="1", receipt_count=100, share_pct=Decimal("50.0")),
            FakeRow(bucket="2", receipt_count=80, share_pct=Decimal("40.0")),
            FakeRow(bucket=">3", receipt_count=20, share_pct=Decimal("10.0")),
        ]
        result = await _fetch_receipt_bucket_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                                 asm=None, site_code=None, agent=None)
        assert len(result) == 3
        assert result[0].bucket == "1"


class TestFetchFocusSubcategoryMixWithData:
    @pytest.mark.asyncio
    async def test_with_rows(self, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(category="Sub1", sales_total=Decimal("10000"), quantity_total=100, share_pct=Decimal("100.0")),
        ]
        result = await _fetch_focus_subcategory_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                                    asm=None, site_code=None, agent=None)
        assert len(result) == 1


class TestFetchBrandMixWithData:
    @pytest.mark.asyncio
    async def test_with_rows(self, mock_conn):
        mock_conn.fetch.return_value = [
            FakeRow(brand="BrandA", sales_total=Decimal("20000"), quantity_total=200, share_pct=Decimal("66.7")),
            FakeRow(brand="BrandB", sales_total=Decimal("10000"), quantity_total=100, share_pct=Decimal("33.3")),
        ]
        result = await _fetch_brand_mix(mock_conn, month="2026-05", firma=None, regional=None,
                                        asm=None, site_code=None, agent=None)
        assert len(result) == 2
        assert result[0].brand == "BrandA"


class TestFetchPromoIncentiveSummary:
    @pytest.mark.asyncio
    async def test_no_data(self, mock_conn):
        result = await _fetch_promo_incentive_summary(mock_conn, month="2026-05", firma=None, regional=None,
                                                       asm=None, site_code=None, agent=None)
        assert result.promo_qty == 0
        assert result.incentive_qty == 0

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition")
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock, return_value=None)
    async def test_with_promo_data(self, mock_inc, mock_promo, mock_config, mock_conn):
        from datetime import date
        mock_promo.return_value = (
            {"item_codes": ["C1", "C2"], "start_date": date(2026, 5, 1), "end_date": date(2026, 5, 31)},
            None,
        )
        mock_conn.fetchrow.return_value = FakeRow(promo_qty=50, promo_sales=Decimal("5000"))
        result = await _fetch_promo_incentive_summary(mock_conn, month="2026-05", firma=None, regional=None,
                                                       asm=None, site_code=None, agent=None)
        assert result.promo_qty == 50
        assert result.promo_sales == Decimal("5000")
        assert result.promo_impact == Decimal("1000.0")

    @pytest.mark.asyncio
    @patch("services.dashboard.queries.load_special_cards_config", return_value=({}, None))
    @patch("services.dashboard.queries.parse_promotion_definition", return_value=(None, None))
    @patch("services.dashboard.queries.get_incentive_campaign", new_callable=AsyncMock)
    @patch("services.dashboard.queries._get_store_incentive_multipliers", new_callable=AsyncMock)
    async def test_with_incentive_data(self, mock_mults, mock_inc, mock_promo, mock_config, mock_conn):
        mock_inc.return_value = {"reward_map": {"C1": 10.0, "C2": 5.0}, "title": "Test"}
        mock_mults.return_value = ({"S1": 1.0}, {"S1": 1.1})
        mock_conn.fetch.return_value = [
            FakeRow(site_code="S1", item_code="C1", qty=20),
            FakeRow(site_code="S1", item_code="C2", qty=10),
        ]
        mock_conn.fetchrow.return_value = FakeRow(cnt=5)
        result = await _fetch_promo_incentive_summary(mock_conn, month="2026-05", firma=None, regional=None,
                                                       asm=None, site_code=None, agent=None)
        assert result.incentive_qty == 30
        assert result.incentive_value > 0
        assert result.incentive_qualified_stores == 1
        assert result.incentive_qualified_agents == 5
