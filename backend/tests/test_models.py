from __future__ import annotations

from decimal import Decimal

from models import StoreStats


def test_store_stats_has_promo_qty():
    stat = StoreStats(
        import_month="2026-03",
        site_code="TST01",
        locatie="Test Store",
        firma="Mobiup",
        regional="RM1",
        asm="ASM1",
        total_vanzari=Decimal("1000.00"),
        qty_total=10,
        nr_bonuri=5,
        nr_agenti=2,
        zile_active=20,
        target=Decimal("900.00"),
        proc_realizare_target=Decimal("111.11"),
    )
    assert stat.promo_qty == 0
    assert stat.incentive_qty == 0


def test_store_stats_accepts_incentive_qty():
    stat = StoreStats(
        import_month="2026-03",
        site_code="TST01",
        locatie="Test Store",
        firma="Mobiup",
        regional="RM1",
        asm="ASM1",
        total_vanzari=Decimal("1000.00"),
        qty_total=10,
        nr_bonuri=5,
        nr_agenti=2,
        zile_active=20,
        target=Decimal("900.00"),
        proc_realizare_target=Decimal("111.11"),
        promo_qty=3,
        incentive_qty=7,
    )
    assert stat.promo_qty == 3
    assert stat.incentive_qty == 7
