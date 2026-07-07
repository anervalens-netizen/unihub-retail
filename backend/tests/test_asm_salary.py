"""Unit tests pentru grila de salarizare ASM (fără DB)."""
from __future__ import annotations

from services.asm_salary import (
    ASM_FIXED_SALARY,
    HOMOGENEITY_COMMISSION,
    acc_focus_commission,
    compute_asm_salary,
    island_target_commission,
    zone_target_commission,
)


def _store(site_code, locatie, firma, target, sales, fq=0, tq=0):
    return {
        "site_code": site_code,
        "locatie": locatie,
        "firma": firma,
        "target_value": target,
        "total_sales": sales,
        "focus_quantity": fq,
        "total_quantity": tq,
    }


# ── tier pur ─────────────────────────────────────────────────────────

def test_zone_tiers_use_thresholds_as_written_no_extra_grace():
    # pragurile afișate sunt deja „1% sub prag", deci 78% nu mai primește 79→700
    assert zone_target_commission(78.9) == 0
    assert zone_target_commission(79) == 700
    assert zone_target_commission(83.99) == 700
    assert zone_target_commission(84) == 800
    assert zone_target_commission(88.99) == 800
    assert zone_target_commission(89) == 1000
    assert zone_target_commission(93.99) == 1000
    assert zone_target_commission(94) == 1200
    assert zone_target_commission(98.99) == 1200
    assert zone_target_commission(99) == 1400
    assert zone_target_commission(108.99) == 1400
    assert zone_target_commission(109) == 1500
    assert zone_target_commission(150) == 1500
    assert zone_target_commission(None) == 0


def test_island_tiers():
    assert island_target_commission(78.9) == 0
    assert island_target_commission(79) == 100
    assert island_target_commission(88.99) == 100
    assert island_target_commission(89) == 150
    assert island_target_commission(98.99) == 150
    assert island_target_commission(99) == 200
    assert island_target_commission(108.99) == 200
    assert island_target_commission(109) == 250


def test_acc_focus_tiers():
    assert acc_focus_commission(4.9) == 0
    assert acc_focus_commission(5) == 200
    assert acc_focus_commission(5.4) == 200
    assert acc_focus_commission(5.5) == 300
    assert acc_focus_commission(5.9) == 300
    assert acc_focus_commission(6) == 400
    assert acc_focus_commission(6.4) == 400
    assert acc_focus_commission(6.5) == 500
    assert acc_focus_commission(6.9) == 500
    assert acc_focus_commission(7) == 600
    assert acc_focus_commission(8) == 600


# ── compute_asm_salary ───────────────────────────────────────────────

def test_final_month_full_attainment_homogeneity_and_acc_focus():
    # 2 insule, ambele 100% target → omogenitate, fiecare 200 (99-108.99)
    stores = [
        _store("A", "Loc A", "Mobiup", 10000, 10000, fq=6, tq=100),
        _store("B", "Loc B", "MobiCell", 10000, 10000, fq=6, tq=100),
    ]
    res = compute_asm_salary(stores, forecast_factor=1.0)
    assert res["is_forecast"] is False
    assert res["fixed_salary"] == ASM_FIXED_SALARY
    # zonă 100% → 1400; 2 insule * 200 = 400; omogenitate 500; acc focus 6% → 400
    assert res["zone"]["pct_used"] == 100.0
    assert res["zone"]["commission"] == 1400
    assert res["islands_commission"] == 400
    assert res["homogeneity"]["eligible"] is True
    assert res["homogeneity"]["commission"] == HOMOGENEITY_COMMISSION
    assert res["acc_focus"]["pct"] == 6.0
    assert res["acc_focus"]["commission"] == 400
    assert res["total_salary"] == 4000 + 1400 + 400 + 500 + 400


def test_homogeneity_requires_strictly_more_than_half():
    # 4 insule, 2 la 99% (exactly half) → NU omogenitate (peste 50% = >2)
    stores = [
        _store("A", "A", "f", 100, 99, fq=0, tq=10),   # 99% → califică
        _store("B", "B", "f", 100, 99, fq=0, tq=10),   # 99% → califică
        _store("C", "C", "f", 100, 50, fq=0, tq=10),   # 50% → nu
        _store("D", "D", "f", 100, 50, fq=0, tq=10),   # 50% → nu
    ]
    res = compute_asm_salary(stores, 1.0)
    assert res["homogeneity"]["qualifying_count"] == 2
    assert res["homogeneity"]["islands_count"] == 4
    assert res["homogeneity"]["eligible"] is False
    assert res["homogeneity"]["commission"] == 0
    # 3 califică din 5 → 0.6 > 0.5 → eligible
    stores.append(_store("E", "E", "f", 100, 99, fq=0, tq=10))
    res2 = compute_asm_salary(stores, 1.0)
    assert res2["homogeneity"]["qualifying_count"] == 3
    assert res2["homogeneity"]["eligible"] is True


def test_forecast_month_uses_forecasted_pct():
    # 1 insulă: target 100, vânzări 50, forecast_factor 2.0 → prognozat 100%
    stores = [_store("A", "A", "f", 100, 50)]
    res = compute_asm_salary(stores, forecast_factor=2.0)
    assert res["is_forecast"] is True
    assert res["zone"]["target_pct"] == 50.0          # actual la zi
    assert res["zone"]["forecast_target_pct"] == 100.0
    assert res["zone"]["pct_used"] == 100.0           # folosește prognoza
    assert res["zone"]["commission"] == 1400          # 99-108.99
    # comisionul pe insulă folosește tot prognoza: 100% → 200
    assert res["islands"][0]["commission"] == 200
    # omogenitate: 1/1 la 100% ≥ 99 → eligible
    assert res["homogeneity"]["eligible"] is True


def test_forecast_below_threshold_uses_forecast_not_actual():
    # actual 40%, prognozat 80% → comision pe 80% (79-88.99 → 700 zonă, 100 insulă)
    stores = [_store("A", "A", "f", 100, 40)]
    res = compute_asm_salary(stores, forecast_factor=2.0)
    assert res["zone"]["pct_used"] == 80.0
    assert res["zone"]["commission"] == 700
    assert res["islands"][0]["commission"] == 100


def test_acc_focus_below_5_is_zero_even_if_close():
    # 4.9% acc focus → 0 comision (pragul 5% e fix, fără gratie suplimentara)
    stores = [_store("A", "A", "f", 100, 100, fq=49, tq=1000)]
    res = compute_asm_salary(stores, 1.0)
    assert res["acc_focus"]["pct"] == 4.9
    assert res["acc_focus"]["commission"] == 0


def test_empty_stores_no_crash():
    res = compute_asm_salary([], 1.0)
    assert res["total_salary"] == ASM_FIXED_SALARY
    assert res["homogeneity"]["eligible"] is False
    assert res["zone"]["target_pct"] is None
    assert res["zone"]["commission"] == 0


def test_zero_target_island_excluded_from_homogeneity_and_no_commission():
    # insulă fără target → pct None, nu califică omogenitate, comision 0
    stores = [_store("A", "A", "f", 0, 0)]
    res = compute_asm_salary(stores, 1.0)
    assert res["islands"][0]["target_pct"] is None
    assert res["islands"][0]["commission"] == 0
    assert res["homogeneity"]["eligible"] is False


def test_total_formula_sums_all_components():
    stores = [
        _store("A", "A", "f", 100, 110, fq=7, tq=100),  # 110% → zonă≥109? cu 1 insulă și 110 → insulă 250
        _store("B", "B", "f", 100, 110, fq=7, tq=100),  # 110% → insulă 250
    ]
    res = compute_asm_salary(stores, 1.0)
    # zonă 110% → 1500; insule 2*250=500; omogenitate 2/2→500; acc 7%→600
    assert res["zone"]["commission"] == 1500
    assert res["islands_commission"] == 500
    assert res["homogeneity"]["commission"] == 500
    assert res["acc_focus"]["commission"] == 600
    assert res["total_salary"] == 4000 + 1500 + 500 + 500 + 600
