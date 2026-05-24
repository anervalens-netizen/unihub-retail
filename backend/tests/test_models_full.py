"""Tests for Pydantic models validation."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def test_dashboard_all_response_fields():
    from models import DashboardAllResponse, DashboardSummary, PromoIncentiveSummary

    summary = DashboardSummary(
        month="2026-03",
        total_sales=Decimal("150000"),
        total_target=Decimal("200000"),
        target_progress_pct=Decimal("75.0"),
        forecast_sales=None,
        forecast_target_progress_pct=None,
        total_quantity=500,
        total_receipts=45,
        proc_bon2acc=None,
        prc_focus_acc_qty=None,
        total_stores=30,
        total_agents=120,
        working_days=22,
        daily_average=None,
        is_month_final=False,
        last_sale_date=None,
        imported_day_of_month=None,
        days_in_month=None,
        cartele_qty=0,
    )
    response = DashboardAllResponse(
        summary=summary,
        agents=[],
        stores=[],
        daily=[],
        special_cards=[],
        period_comparison=None,
        category_mix=[],
        receipt_bucket_mix=[],
        focus_subcategory_mix=[],
        brand_mix=[],
        promo_incentive=PromoIncentiveSummary(
            promo_qty=0, promo_sales=Decimal("0"), promo_impact=Decimal("0"),
            incentive_qty=0, incentive_value=Decimal("0"),
            incentive_qualified_stores=0, incentive_qualified_agents=0,
        ),
        regionals=[],
        asms=[],
    )
    assert response.summary.total_sales == Decimal("150000")
    assert response.summary.total_stores == 30


def test_dashboard_history_response():
    from models import DashboardHistoryResponse, MonthlyHistoryPoint

    points = [
        MonthlyHistoryPoint(
            month="2026-01",
            total_sales=Decimal("100000"),
            total_target=Decimal("150000"),
            target_progress_pct=Decimal("66.67"),
            total_quantity=300,
            total_receipts=30,
            proc_bon2acc=None,
            prc_focus_acc_qty=None,
            total_stores=25,
            total_agents=100,
            working_days=21,
            daily_average=None,
        )
    ]
    response = DashboardHistoryResponse(history=points)
    assert response.history[0].month == "2026-01"


def test_year_history_response():
    from models import YearHistoryResponse, YearHistoryPoint

    points = [
        YearHistoryPoint(
            label="2026",
            sort_key="2026",
            total_sales=Decimal("1000000"),
            total_target=Decimal("1500000"),
            total_quantity=5000,
            is_aggregate=False,
        )
    ]
    response = YearHistoryResponse(points=points)
    assert response.points[0].total_sales == Decimal("1000000")


def test_agent_stats_model():
    from models import AgentStats

    agent = AgentStats(
        import_month="2026-03",
        agent="POPESCU ION",
        site_code="ST001",
        locatie="Magazin Central",
        firma="Firma 1",
        regional="Regional 1",
        asm="ASM 1",
        acc_qty_realizat=100,
        nr_bonuri=50,
        nr_bon2acc=30,
        proc_bon2acc=Decimal("60"),
        total_vanzari=Decimal("15000"),
        zile_lucrate=22,
        medie_zilnica=Decimal("681"),
        acc_focus_qty=20,
        prc_focus_acc_qty=Decimal("40"),
        target=Decimal("20000"),
        proc_realizare_target=Decimal("75"),
        promo_qty=0,
        incentive_qty=0,
    )
    assert agent.agent == "POPESCU ION"
    assert agent.total_vanzari == Decimal("15000")


def test_store_stats_model():
    from models import StoreStats

    store = StoreStats(
        import_month="2026-03",
        site_code="ST001",
        locatie="Magazin Central",
        firma="Firma 1",
        regional="Regional 1",
        asm="ASM 1",
        total_vanzari=Decimal("50000"),
        qty_total=200,
        nr_bonuri=100,
        nr_agenti=10,
        zile_active=22,
        target=Decimal("60000"),
        proc_realizare_target=Decimal("83.33"),
        promo_qty=0,
        incentive_qty=0,
    )
    assert store.site_code == "ST001"
    assert store.promo_qty == 0


def test_regional_stats_model():
    from models import RegionalStats

    stat = RegionalStats(
        regional="Bucuresti",
        total_vanzari=Decimal("200000"),
        qty_total=800,
        nr_bonuri=400,
        nr_agenti=80,
        zile_active=22,
        target=Decimal("250000"),
        proc_realizare_target=Decimal("80"),
        promo_qty=50,
        incentive_qty=30,
        medie_zilnica=Decimal("9090"),
        proc_bon2acc=Decimal("55"),
        prc_focus_acc_qty=Decimal("35"),
    )
    assert stat.regional == "Bucuresti"


def test_asm_stats_model():
    from models import AsmStats

    stat = AsmStats(
        asm="ASM 1",
        regional="Regional 1",
        total_vanzari=Decimal("100000"),
        qty_total=400,
        nr_bonuri=200,
        nr_agenti=40,
        zile_active=22,
        target=Decimal("120000"),
        proc_realizare_target=Decimal("83.33"),
        promo_qty=20,
        incentive_qty=10,
        medie_zilnica=Decimal("4545"),
        proc_bon2acc=Decimal("50"),
        prc_focus_acc_qty=Decimal("30"),
    )
    assert stat.asm == "ASM 1"


def test_daily_sales_point():
    from models import DailySalesPoint
    from datetime import date

    point = DailySalesPoint(
        sale_date=date(2026, 3, 15),
        total_sales=Decimal("5000"),
        total_quantity=20,
        receipt_count=10,
    )
    assert point.sale_date == date(2026, 3, 15)


def test_category_mix_item():
    from models import CategoryMixItem

    item = CategoryMixItem(
        category="Electronice",
        sales_total=Decimal("30000"),
        quantity_total=100,
        share_pct=Decimal("20"),
    )
    assert item.category == "Electronice"


def test_brand_mix_item():
    from models import BrandMixItem

    item = BrandMixItem(
        brand="Samsung",
        sales_total=Decimal("15000"),
        quantity_total=50,
        share_pct=Decimal("10"),
    )
    assert item.brand == "Samsung"


def test_filter_options_model():
    from models import FilterOptions

    opts = FilterOptions(
        firme=[],
        regionali=[],
        asmi=[],
        magazine=[],
        agenti=[],
    )
    assert opts.firme == []


def test_store_option_model():
    from models import StoreOption

    opt = StoreOption(
        site_code="ST001",
        locatie="Test Store",
        firma="Firma 1",
        regional="Regional 1",
        asm="ASM 1",
    )
    assert opt.site_code == "ST001"


def test_store_target_input():
    from models import StoreTargetInput

    target = StoreTargetInput(
        site_code="ST001",
        import_month="2026-03",
        target_value=Decimal("10000"),
    )
    assert target.target_value == Decimal("10000")


def test_import_response_model():
    from models import ImportResponse

    resp = ImportResponse(
        import_month="2026-03",
        rows_in_file=1000,
        rows_imported=950,
        rows_filtered=50,
        store_count=30,
        agent_count=120,
        snapshot_id=1,
        filename="test.xlsx",
        is_month_final=False,
    )
    assert resp.import_month == "2026-03"


def test_import_job_status_model():
    from models import ImportJobStatus

    status = ImportJobStatus(job_id="abc123", status="queued")
    assert status.job_id == "abc123"


def test_import_history_entry_model():
    from models import ImportHistoryEntry

    entry = ImportHistoryEntry(
        id=1,
        import_month="2026-03",
        filename="test.xlsx",
        upload_date=date.today(),
        is_month_final=False,
        rows_in_file=1000,
        rows_imported=500,
        status="completed",
        error_message=None,
        created_at=datetime.now(),
    )
    assert entry.import_month == "2026-03"


def test_special_card_model():
    from models import DashboardSpecialCard

    card = DashboardSpecialCard(
        key="promotion",
        title="Card Test",
        subtitle=None,
        status="ready",
        status_label="Activ",
        highlight_value="+15%",
        description="Test description",
        coverage_note=None,
        metrics=[],
    )
    assert card.title == "Card Test"


def test_promo_incentive_summary():
    from models import PromoIncentiveSummary
    from decimal import Decimal

    summary = PromoIncentiveSummary(
        promo_qty=500,
        promo_sales=Decimal("50000"),
        promo_impact=Decimal("0"),
        incentive_qty=200,
        incentive_value=Decimal("10000"),
        incentive_qualified_stores=30,
        incentive_qualified_agents=120,
    )
    assert summary.promo_qty == 500
