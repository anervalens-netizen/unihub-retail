from datetime import date
from decimal import Decimal

from services.fiscal_rules import (
    STANDARD_VAT_RULESET_ID,
    EFFECTIVE_DATED_VAT_ENV,
    gross_to_net,
    net_to_gross,
    runtime_gross_to_net,
    standard_vat_rule,
    standard_vat_ruleset_hash,
)


def test_standard_vat_switches_on_effective_date() -> None:
    assert standard_vat_rule(date(2025, 7, 31)).multiplier == Decimal("1.19")
    assert standard_vat_rule(date(2025, 8, 1)).multiplier == Decimal("1.21")


def test_gross_and_net_conversion_round_once_to_cent() -> None:
    assert gross_to_net(Decimal("119.00"), "2025-07") == Decimal("100.00")
    assert gross_to_net(Decimal("121.00"), "2025-08") == Decimal("100.00")
    assert net_to_gross(Decimal("100.005"), "2025-08") == Decimal("121.01")

def test_runtime_conversion_stays_legacy_until_explicit_activation(
    monkeypatch,
) -> None:
    monkeypatch.delenv(EFFECTIVE_DATED_VAT_ENV, raising=False)
    assert runtime_gross_to_net(Decimal("121.00"), "2025-08") == Decimal("101.68")

    monkeypatch.setenv(EFFECTIVE_DATED_VAT_ENV, "1")
    assert runtime_gross_to_net(Decimal("121.00"), "2025-08") == Decimal("100.00")



def test_ruleset_has_stable_audit_identity() -> None:
    assert STANDARD_VAT_RULESET_ID == "ro-standard-vat-v1"
    assert standard_vat_ruleset_hash() == standard_vat_ruleset_hash()
    assert len(standard_vat_ruleset_hash()) == 64
