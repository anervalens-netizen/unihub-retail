"""Calcul salarial ASM pe procente exacte și reguli effective-dated."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class AsmSalaryRuleSet:
    rule_set_id: str
    effective_from: str
    fixed_salary: int
    zone_target_tiers: tuple[tuple[Decimal, int], ...]
    island_target_tiers: tuple[tuple[Decimal, int], ...]
    acc_focus_tiers: tuple[tuple[Decimal, int], ...]
    homogeneity_min_pct: Decimal
    homogeneity_commission: int

    @property
    def sha256(self) -> str:
        material = {
            "rule_set_id": self.rule_set_id,
            "effective_from": self.effective_from,
            "fixed_salary": self.fixed_salary,
            "zone_target_tiers": [[str(pct), amount] for pct, amount in self.zone_target_tiers],
            "island_target_tiers": [[str(pct), amount] for pct, amount in self.island_target_tiers],
            "acc_focus_tiers": [[str(pct), amount] for pct, amount in self.acc_focus_tiers],
            "homogeneity_min_pct": str(self.homogeneity_min_pct),
            "homogeneity_commission": self.homogeneity_commission,
        }
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


ASM_SALARY_RULE_SETS: tuple[AsmSalaryRuleSet, ...] = (
    AsmSalaryRuleSet(
        rule_set_id="asm-v1",
        effective_from="2000-01",
        fixed_salary=4000,
        zone_target_tiers=tuple(
            (Decimal(pct), amount)
            for pct, amount in (("109", 1500), ("99", 1400), ("94", 1200), ("89", 1000), ("84", 800), ("79", 700))
        ),
        island_target_tiers=tuple(
            (Decimal(pct), amount)
            for pct, amount in (("109", 250), ("99", 200), ("89", 150), ("79", 100))
        ),
        acc_focus_tiers=tuple(
            (Decimal(pct), amount)
            for pct, amount in (("7", 600), ("6.5", 500), ("6", 400), ("5.5", 300), ("5", 200))
        ),
        homogeneity_min_pct=Decimal("99"),
        homogeneity_commission=500,
    ),
)

DEFAULT_ASM_SALARY_RULE_SET = ASM_SALARY_RULE_SETS[-1]
ASM_FIXED_SALARY = DEFAULT_ASM_SALARY_RULE_SET.fixed_salary
ZONE_TARGET_TIERS = DEFAULT_ASM_SALARY_RULE_SET.zone_target_tiers
ISLAND_TARGET_TIERS = DEFAULT_ASM_SALARY_RULE_SET.island_target_tiers
ACC_FOCUS_TIERS = DEFAULT_ASM_SALARY_RULE_SET.acc_focus_tiers
HOMOGENEITY_MIN_PCT = float(DEFAULT_ASM_SALARY_RULE_SET.homogeneity_min_pct)
HOMOGENEITY_COMMISSION = DEFAULT_ASM_SALARY_RULE_SET.homogeneity_commission


def asm_salary_rule_set_for_month(month: str) -> AsmSalaryRuleSet:
    matches = [rules for rules in ASM_SALARY_RULE_SETS if rules.effective_from <= month]
    if not matches:
        raise ValueError(f"Nu exista grila ASM pentru luna {month}")
    return matches[-1]


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Valoare numerica ASM invalida") from exc


def _exact_pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator * Decimal("100")


def _display(value: Decimal | None, places: str = "0.1") -> float | None:
    return None if value is None else float(value.quantize(Decimal(places)))


def _exact_text(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def commission_for_tier(
    pct: Decimal | float | int | None,
    tiers: Iterable[tuple[Decimal, int]],
) -> int:
    """Decide comisionul pe valoarea exactă; rotunjirea este doar de afișare."""
    if pct is None:
        return 0
    exact_pct = _decimal(pct)
    for threshold, amount in tiers:
        if exact_pct >= threshold:
            return amount
    return 0


def zone_target_commission(pct: Decimal | float | int | None) -> int:
    return commission_for_tier(pct, ZONE_TARGET_TIERS)


def island_target_commission(pct: Decimal | float | int | None) -> int:
    return commission_for_tier(pct, ISLAND_TARGET_TIERS)


def acc_focus_commission(pct: Decimal | float | int | None) -> int:
    return commission_for_tier(pct, ACC_FOCUS_TIERS)


def compute_asm_salary(
    stores: Sequence[Mapping[str, Any]],
    forecast_factor: float | Decimal,
    *,
    rules: AsmSalaryRuleSet = DEFAULT_ASM_SALARY_RULE_SET,
) -> dict[str, Any]:
    """Calculează defalcarea ASM fără rotunjire înaintea pragurilor."""
    factor = _decimal(forecast_factor)
    is_partial = factor > Decimal("1.001")
    zone_sales = sum((_decimal(s.get("total_sales")) for s in stores), Decimal(0))
    zone_target = sum((_decimal(s.get("target_value")) for s in stores), Decimal(0))
    zone_focus_qty = sum((_decimal(s.get("focus_quantity")) for s in stores), Decimal(0))
    zone_total_qty = sum((_decimal(s.get("total_quantity")) for s in stores), Decimal(0))

    zone_target_pct_exact = _exact_pct(zone_sales, zone_target)
    zone_forecast_sales = zone_sales * factor
    zone_forecast_pct_exact = _exact_pct(zone_forecast_sales, zone_target)
    zone_focus_pct_exact = _exact_pct(zone_focus_qty, zone_total_qty)
    zone_pct_used_exact = zone_forecast_pct_exact if is_partial else zone_target_pct_exact
    zone_commission = commission_for_tier(zone_pct_used_exact, rules.zone_target_tiers)

    islands: list[dict[str, Any]] = []
    qualifying = 0
    for store in stores:
        sales = _decimal(store.get("total_sales"))
        target = _decimal(store.get("target_value"))
        target_pct_exact = _exact_pct(sales, target)
        forecast_sales = sales * factor
        forecast_pct_exact = _exact_pct(forecast_sales, target)
        pct_used_exact = forecast_pct_exact if is_partial else target_pct_exact
        qualifies = pct_used_exact is not None and pct_used_exact >= rules.homogeneity_min_pct
        qualifying += int(qualifies)
        islands.append({
            "site_code": store.get("site_code"),
            "locatie": store.get("locatie"),
            "firma": store.get("firma"),
            "total_sales": _display(sales, "0.01"),
            "total_target": _display(target, "0.01"),
            "target_pct": _display(target_pct_exact),
            "forecast_sales": _display(forecast_sales, "0.01"),
            "forecast_target_pct": _display(forecast_pct_exact),
            "pct_used": _display(pct_used_exact),
            "decision_pct_exact": _exact_text(pct_used_exact),
            "homogeneity_qualifies": qualifies,
            "commission": commission_for_tier(pct_used_exact, rules.island_target_tiers),
        })

    islands_count = len(islands)
    homogeneity_eligible = islands_count > 0 and Decimal(qualifying) / Decimal(islands_count) > Decimal("0.5")
    focus_pct_for_decision = zone_focus_pct_exact or Decimal(0)
    islands_commission = sum(island["commission"] for island in islands)
    homogeneity_commission = rules.homogeneity_commission if homogeneity_eligible else 0
    focus_commission = commission_for_tier(focus_pct_for_decision, rules.acc_focus_tiers)
    total_salary = rules.fixed_salary + zone_commission + islands_commission + homogeneity_commission + focus_commission

    return {
        "rule_set_id": rules.rule_set_id,
        "rule_set_sha256": rules.sha256,
        "rule_effective_from": rules.effective_from,
        "is_forecast": is_partial,
        "forecast_factor": _display(factor, "0.001"),
        "fixed_salary": rules.fixed_salary,
        "zone": {
            "total_sales": _display(zone_sales, "0.01"),
            "total_target": _display(zone_target, "0.01"),
            "target_pct": _display(zone_target_pct_exact),
            "forecast_sales": _display(zone_forecast_sales, "0.01"),
            "forecast_target_pct": _display(zone_forecast_pct_exact),
            "pct_used": _display(zone_pct_used_exact),
            "decision_pct_exact": _exact_text(zone_pct_used_exact),
            "commission": zone_commission,
        },
        "islands": islands,
        "islands_commission": islands_commission,
        "homogeneity": {
            "islands_count": islands_count,
            "qualifying_count": qualifying,
            "qualifying_pct": round(qualifying / islands_count * 100, 1) if islands_count else 0.0,
            "min_pct": float(rules.homogeneity_min_pct),
            "eligible": homogeneity_eligible,
            "commission": homogeneity_commission,
        },
        "acc_focus": {
            "pct": _display(zone_focus_pct_exact),
            "decision_pct_exact": _exact_text(zone_focus_pct_exact),
            "commission": focus_commission,
        },
        "total_salary": total_salary,
    }
