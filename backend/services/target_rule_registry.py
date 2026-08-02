from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from services.fiscal_rules import STANDARD_VAT_RULESET_ID, standard_vat_rule, standard_vat_ruleset_hash


TARGET_RULESET_SCHEMA_VERSION = 1
_SITE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class TargetRuleSetValidationError(ValueError):
    """A persisted Target rule-set is absent, malformed, or inconsistent with fiscal rules."""


@dataclass(frozen=True)
class TargetRuleSet:
    rule_set_id: str
    version: int
    effective_from_month: str
    effective_to_month: str | None
    rules_hash: str
    rules: dict[str, Any]

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": TARGET_RULESET_SCHEMA_VERSION,
            "rule_set_id": self.rule_set_id,
            "version": self.version,
            "effective_from_month": self.effective_from_month,
            "effective_to_month": self.effective_to_month,
            "rules_hash": self.rules_hash,
            "rules": self.rules,
        }


def canonical_rules_hash(rules: dict[str, Any]) -> str:
    canonical = json.dumps(rules, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _decimal(value: Any, name: str, *, minimum: Decimal | None = None) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise TargetRuleSetValidationError(f"{name} trebuie sa fie numeric.") from exc
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise TargetRuleSetValidationError(f"{name} este in afara domeniului permis.")
    return result


def _integer(value: Any, name: str, *, minimum: int = 1, maximum: int = 100) -> int:
    if isinstance(value, bool):
        raise TargetRuleSetValidationError(f"{name} trebuie sa fie intreg.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise TargetRuleSetValidationError(f"{name} trebuie sa fie intreg.") from exc
    if str(value) != str(result) or not minimum <= result <= maximum:
        raise TargetRuleSetValidationError(f"{name} este in afara domeniului permis.")
    return result


def _as_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetRuleSetValidationError(f"{name} trebuie sa fie obiect.")
    return value


def _validate_rules(rules: dict[str, Any], target_month: str) -> dict[str, Any]:
    if set(rules) != {"vat", "salary", "store_exceptions"}:
        raise TargetRuleSetValidationError("Rule-set-ul Target contine chei neacceptate sau lipsa.")

    vat = _as_object(rules["vat"], "vat")
    if set(vat) != {"ruleset_id", "rule_id", "rate", "multiplier"}:
        raise TargetRuleSetValidationError("Configuratia TVA Target nu are forma canonica.")
    rate = _decimal(vat["rate"], "vat.rate", minimum=Decimal("0"))
    multiplier = _decimal(vat["multiplier"], "vat.multiplier", minimum=Decimal("1"))
    fiscal_rule = standard_vat_rule(target_month)
    if (
        vat["ruleset_id"] != STANDARD_VAT_RULESET_ID
        or vat["rule_id"] != fiscal_rule.rule_id
        or rate != fiscal_rule.rate
        or multiplier != fiscal_rule.multiplier
        or multiplier != Decimal("1") + rate
    ):
        raise TargetRuleSetValidationError(
            "Rule-set-ul Target nu coincide cu registry-ul fiscal efectiv pentru luna ceruta."
        )

    salary = _as_object(rules["salary"], "salary")
    required_salary = {
        "pnl_factor",
        "meal_vouchers_per_agent",
        "sales_commission_rate",
        "assumed_attainment",
        "default_agent_count",
        "base_salary",
    }
    if set(salary) != required_salary:
        raise TargetRuleSetValidationError("Configuratia salariala Target nu are forma canonica.")
    pnl_factor = _decimal(salary["pnl_factor"], "salary.pnl_factor", minimum=Decimal("0"))
    meal_vouchers = _decimal(
        salary["meal_vouchers_per_agent"], "salary.meal_vouchers_per_agent", minimum=Decimal("0")
    )
    commission = _decimal(salary["sales_commission_rate"], "salary.sales_commission_rate", minimum=Decimal("0"))
    attainment = _decimal(salary["assumed_attainment"], "salary.assumed_attainment", minimum=Decimal("0"))
    base_salary = _decimal(salary["base_salary"], "salary.base_salary", minimum=Decimal("0"))
    if commission > Decimal("1") or attainment > Decimal("1") or pnl_factor <= 0:
        raise TargetRuleSetValidationError("Configuratia salariala Target depaseste limitele business.")
    default_agents = _integer(salary["default_agent_count"], "salary.default_agent_count")

    raw_exceptions = _as_object(rules["store_exceptions"], "store_exceptions")
    exceptions: dict[str, dict[str, Any]] = {}
    for site_code, raw_exception in raw_exceptions.items():
        if not isinstance(site_code, str) or not _SITE_CODE_PATTERN.fullmatch(site_code):
            raise TargetRuleSetValidationError("Mappingul magazinului Target are site_code invalid.")
        exception = _as_object(raw_exception, f"store_exceptions.{site_code}")
        if not exception or set(exception) - {"agent_count", "base_salary"}:
            raise TargetRuleSetValidationError("Exceptia magazinului Target are campuri neacceptate.")
        normalized: dict[str, Any] = {}
        if "agent_count" in exception:
            normalized["agent_count"] = _integer(
                exception["agent_count"], f"store_exceptions.{site_code}.agent_count"
            )
        if "base_salary" in exception:
            normalized["base_salary"] = str(
                _decimal(exception["base_salary"], f"store_exceptions.{site_code}.base_salary", minimum=Decimal("0"))
            )
        exceptions[site_code] = normalized

    return {
        "vat": {
            "ruleset_id": vat["ruleset_id"],
            "rule_id": vat["rule_id"],
            "rate": str(rate),
            "multiplier": str(multiplier),
            "ruleset_hash": standard_vat_ruleset_hash(),
        },
        "salary": {
            "pnl_factor": str(pnl_factor),
            "meal_vouchers_per_agent": str(meal_vouchers),
            "sales_commission_rate": str(commission),
            "assumed_attainment": str(attainment),
            "default_agent_count": default_agents,
            "base_salary": str(base_salary),
        },
        "store_exceptions": exceptions,
    }


def validate_target_rule_set(record: dict[str, Any], target_month: str) -> TargetRuleSet:
    try:
        rule_set_id = str(record["id"])
        version = int(record["version"])
        effective_from_month = str(record["effective_from_month"])
        effective_to_raw = record.get("effective_to_month")
        effective_to_month = str(effective_to_raw) if effective_to_raw is not None else None
        raw_rules = record["rules"]
        rules_hash = str(record["rules_sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TargetRuleSetValidationError("Registry-ul Target nu contine un rule-set complet.") from exc
    if not rule_set_id or version < 1 or effective_from_month > target_month:
        raise TargetRuleSetValidationError("Rule-set-ul Target nu este efectiv pentru luna ceruta.")
    if effective_to_month is not None and (effective_to_month <= effective_from_month or effective_to_month <= target_month):
        raise TargetRuleSetValidationError("Intervalul [from,to) Target este invalid.")
    if isinstance(raw_rules, str):
        try:
            raw_rules = json.loads(raw_rules)
        except json.JSONDecodeError as exc:
            raise TargetRuleSetValidationError("Rule-set-ul Target nu este JSON valid.") from exc
    if not isinstance(raw_rules, dict) or canonical_rules_hash(raw_rules) != rules_hash:
        raise TargetRuleSetValidationError("Hashul rule-set-ului Target nu corespunde continutului.")
    _validate_rules(raw_rules, target_month)
    return TargetRuleSet(
        rule_set_id=rule_set_id,
        version=version,
        effective_from_month=effective_from_month,
        effective_to_month=effective_to_month,
        rules_hash=rules_hash,
        rules=raw_rules,
    )


def target_rule_set_from_snapshot(snapshot: Any, target_month: str) -> TargetRuleSet | None:
    if not isinstance(snapshot, dict):
        return None
    if snapshot.get("schema_version") != TARGET_RULESET_SCHEMA_VERSION:
        raise TargetRuleSetValidationError("Schema snapshotului Target nu este recunoscuta.")
    try:
        record = {
            "id": snapshot["rule_set_id"],
            "version": snapshot["version"],
            "effective_from_month": snapshot["effective_from_month"],
            "effective_to_month": snapshot.get("effective_to_month"),
            "rules_sha256": snapshot["rules_hash"],
            "rules": snapshot["rules"],
        }
    except KeyError:
        return None
    return validate_target_rule_set(record, target_month)


def profitability_assumptions(rule_set: TargetRuleSet) -> dict[str, Any]:
    vat = rule_set.rules["vat"]
    salary = rule_set.rules["salary"]
    return {
        "target_rule_set_id": rule_set.rule_set_id,
        "target_rule_set_hash": rule_set.rules_hash,
        "vat_ruleset_id": vat["ruleset_id"],
        "vat_ruleset_hash": standard_vat_ruleset_hash(),
        "vat_rule_id": vat["rule_id"],
        "vat_multiplier": float(Decimal(vat["multiplier"])),
        "vat_rate": float(Decimal(vat["rate"])),
        "salary_pnl_factor": float(Decimal(salary["pnl_factor"])),
        "meal_vouchers_per_agent": float(Decimal(salary["meal_vouchers_per_agent"])),
        "sales_commission_rate": float(Decimal(salary["sales_commission_rate"])),
        "salary_assumed_attainment": float(Decimal(salary["assumed_attainment"])),
        "default_store_agent_count": salary["default_agent_count"],
        "base_salary_default": float(Decimal(salary["base_salary"])),
    }


def store_salary_parameters(rule_set: TargetRuleSet, site_code: str) -> tuple[int, Decimal]:
    salary = rule_set.rules["salary"]
    exception = rule_set.rules["store_exceptions"].get(site_code, {})
    agents = int(exception.get("agent_count", salary["default_agent_count"]))
    base_salary = Decimal(str(exception.get("base_salary", salary["base_salary"])))
    return agents, base_salary
