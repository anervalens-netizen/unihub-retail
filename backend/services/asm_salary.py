"""Calcularea salariului ASM după grila de comisionare.

Modul pur (fără DB și fără I/O) pentru a putea fi testat unitar.
Tabelele de comision sunt date explicite, ușor de ajustat.

Regula „cu excepție de 1% sub prag" este deja inclusă în pragurile
afiliate în grilă (ex. 79 = 80 − 1, 99 = 100 − 1, pragul Acc Focus 5%
= 6 − 1), deci se folosesc exact ca atare, fără o altă toleranță
suplimentară. Astfel:

  Zonă:    ≥109→1500  ≥99→1400  ≥94→1200  ≥89→1000  ≥84→800  ≥79→700  altfel 0
  Insulă:  ≥109→250   ≥99→200   ≥89→150   ≥79→100   altfel 0
  Omogenitate: >50% insule cu ≥99% realizare → 500, altfel 0
  Acc Focus: ≥7→600  ≥6.5→500  ≥6→400  ≥5.5→300  ≥5→200  altfel 0

Pentru luna curentă parțială, commissionele se calculează pe baza
procentului prognozat la final de lună (vânzări * forecast_factor).
Pentru luni finalizate (forecast_factor ≈ 1.0) se folosesc valorile
actuale. Acc Focus % este un raport de cantități, deci nu se scalează
cu forecast_factor — se folosește raportul lunii (aproape constant).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

ASM_FIXED_SALARY = 4000

# (minim inclusiv, comision). Evaluate descrescător; prima potrivire câștigă.
ZONE_TARGET_TIERS: tuple[tuple[float, int], ...] = (
    (109, 1500),
    (99, 1400),
    (94, 1200),
    (89, 1000),
    (84, 800),
    (79, 700),
)
ISLAND_TARGET_TIERS: tuple[tuple[float, int], ...] = (
    (109, 250),
    (99, 200),
    (89, 150),
    (79, 100),
)
ACC_FOCUS_TIERS: tuple[tuple[float, int], ...] = (
    (7.0, 600),
    (6.5, 500),
    (6.0, 400),
    (5.5, 300),
    (5.0, 200),
)

HOMOGENEITY_MIN_PCT = 99.0
HOMOGENEITY_COMMISSION = 500


def commission_for_tier(pct: float | None, tiers: Iterable[tuple[float, int]]) -> int:
    """Returnează comisionul pentru primul prag atins (descrescător)."""
    if pct is None:
        return 0
    for threshold, amount in tiers:
        if pct >= threshold:
            return amount
    return 0


def zone_target_commission(pct: float | None) -> int:
    return commission_for_tier(pct, ZONE_TARGET_TIERS)


def island_target_commission(pct: float | None) -> int:
    return commission_for_tier(pct, ISLAND_TARGET_TIERS)


def acc_focus_commission(pct: float | None) -> int:
    return commission_for_tier(pct, ACC_FOCUS_TIERS)


def _pct(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def compute_asm_salary(
    stores: list[Mapping[str, Any]],
    forecast_factor: float,
) -> dict[str, Any]:
    """Calculează defalcarea salarială ASM din datele pe magazin.

    ``stores``: listă de dict-uri cu cheile ``site_code``, ``locatie``,
    ``firma``, ``target_value``, ``total_sales``, ``focus_quantity``,
    ``total_quantity`` (ultimele patru numerice).
    ``forecast_factor``: extrapolarea la final de lună
    (zile_lună / ultima_zi_vânzări); 1.0 pentru luni finalizate.
    """
    is_partial = forecast_factor > 1.001

    zone_sales = sum(float(s.get("total_sales") or 0) for s in stores)
    zone_target = sum(float(s.get("target_value") or 0) for s in stores)
    zone_focus_qty = sum(float(s.get("focus_quantity") or 0) for s in stores)
    zone_total_qty = sum(float(s.get("total_quantity") or 0) for s in stores)

    zone_target_pct = _pct(zone_sales, zone_target)
    zone_forecast_sales = zone_sales * forecast_factor
    zone_forecast_target_pct = _pct(zone_forecast_sales, zone_target)
    zone_focus_pct = _pct(zone_focus_qty, zone_total_qty)
    zone_focus_pct_used = zone_focus_pct if zone_focus_pct is not None else 0.0

    zone_pct_used = zone_forecast_target_pct if is_partial else zone_target_pct
    zone_commission = zone_target_commission(zone_pct_used)

    islands: list[dict[str, Any]] = []
    qualifying = 0
    for s in stores:
        sales = float(s.get("total_sales") or 0)
        target = float(s.get("target_value") or 0)
        tgt_pct = _pct(sales, target)
        fc_sales = sales * forecast_factor
        fc_tgt_pct = _pct(fc_sales, target)
        pct_used = fc_tgt_pct if is_partial else tgt_pct
        commission = island_target_commission(pct_used)
        if pct_used is not None and pct_used >= HOMOGENEITY_MIN_PCT:
            qualifying += 1
        islands.append({
            "site_code": s.get("site_code"),
            "locatie": s.get("locatie"),
            "firma": s.get("firma"),
            "total_sales": round(sales, 2),
            "total_target": round(target, 2),
            "target_pct": tgt_pct,
            "forecast_sales": round(fc_sales, 2),
            "forecast_target_pct": fc_tgt_pct,
            "pct_used": pct_used,
            "commission": commission,
        })

    islands_commission = sum(i["commission"] for i in islands)
    islands_count = len(islands)
    qualifying_pct = round(qualifying / islands_count * 100, 1) if islands_count else 0.0
    homog_eligible = islands_count > 0 and (qualifying / islands_count) > 0.5
    homog_commission = HOMOGENEITY_COMMISSION if homog_eligible else 0

    acc_focus_pct = zone_focus_pct_used
    acc_focus_commission_val = acc_focus_commission(acc_focus_pct)

    total_salary = (
        ASM_FIXED_SALARY
        + zone_commission
        + islands_commission
        + homog_commission
        + acc_focus_commission_val
    )

    return {
        "is_forecast": is_partial,
        "forecast_factor": round(forecast_factor, 3),
        "fixed_salary": ASM_FIXED_SALARY,
        "zone": {
            "total_sales": round(zone_sales, 2),
            "total_target": round(zone_target, 2),
            "target_pct": zone_target_pct,
            "forecast_sales": round(zone_forecast_sales, 2),
            "forecast_target_pct": zone_forecast_target_pct,
            "pct_used": zone_pct_used,
            "commission": zone_commission,
        },
        "islands": islands,
        "islands_commission": islands_commission,
        "homogeneity": {
            "islands_count": islands_count,
            "qualifying_count": qualifying,
            "qualifying_pct": qualifying_pct,
            "min_pct": HOMOGENEITY_MIN_PCT,
            "eligible": homog_eligible,
            "commission": homog_commission,
        },
        "acc_focus": {
            "pct": acc_focus_pct,
            "commission": acc_focus_commission_val,
        },
        "total_salary": total_salary,
    }
