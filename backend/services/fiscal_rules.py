from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP


MONEY = Decimal("0.01")
STANDARD_VAT_RULESET_ID = "ro-standard-vat-v1"
LEGACY_VAT_RULESET_ID = "legacy-standard-vat-19"
EFFECTIVE_DATED_VAT_ENV = "EFFECTIVE_DATED_VAT_ENABLED"



@dataclass(frozen=True)
class StandardVatRule:
    rule_id: str
    effective_from: date
    multiplier: Decimal

    @property
    def rate(self) -> Decimal:
        return self.multiplier - Decimal("1")


STANDARD_VAT_RULES = (
    StandardVatRule("ro-standard-vat-19", date.min, Decimal("1.19")),
    StandardVatRule("ro-standard-vat-21", date(2025, 8, 1), Decimal("1.21")),
)


def _as_date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        if len(value) == 7:
            return date.fromisoformat(f"{value}-01")
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Data fiscala trebuie sa fie YYYY-MM sau YYYY-MM-DD") from exc


def standard_vat_rule(value: date | datetime | str) -> StandardVatRule:
    moment = _as_date(value)
    return max(
        (rule for rule in STANDARD_VAT_RULES if rule.effective_from <= moment),
        key=lambda rule: rule.effective_from,
    )


def gross_to_net(
    value: Decimal | int | str | float,
    moment: date | datetime | str,
) -> Decimal:
    gross = Decimal(str(value))
    return (gross / standard_vat_rule(moment).multiplier).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def net_to_gross(
    value: Decimal | int | str | float,
    moment: date | datetime | str,
) -> Decimal:
    net = Decimal(str(value))
    return (net * standard_vat_rule(moment).multiplier).quantize(
        MONEY,
        rounding=ROUND_HALF_UP,
    )


def effective_dated_vat_enabled() -> bool:
    return os.getenv(EFFECTIVE_DATED_VAT_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def legacy_gross_to_net(
    value: Decimal | int | str | float,
    _moment: date | datetime | str,
) -> Decimal:
    gross = Decimal(str(value))
    return (gross / Decimal("1.19")).quantize(MONEY, rounding=ROUND_HALF_UP)



def runtime_gross_to_net(
    value: Decimal | int | str | float,
    moment: date | datetime | str,
) -> Decimal:
    if effective_dated_vat_enabled():
        return gross_to_net(value, moment)
    return legacy_gross_to_net(value, moment)


def standard_vat_ruleset_hash() -> str:
    payload = {
        "ruleset_id": STANDARD_VAT_RULESET_ID,
        "rules": [
            {
                "rule_id": rule.rule_id,
                "effective_from": rule.effective_from.isoformat(),
                "multiplier": str(rule.multiplier),
            }
            for rule in STANDARD_VAT_RULES
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
