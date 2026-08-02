from services.target_calculator import TargetCalculatorService


def test_new_target_scenario_captures_effective_vat_rule() -> None:
    assumptions = TargetCalculatorService._profitability_assumptions("2026-08")

    assert assumptions["vat_rule_id"] == "ro-standard-vat-21"
    assert assumptions["vat_multiplier"] == 1.21
    assert len(assumptions["vat_ruleset_hash"]) == 64


def test_legacy_target_scenario_keeps_previous_unversioned_behavior() -> None:
    assumptions = TargetCalculatorService._legacy_profitability_assumptions()

    assert assumptions["vat_rule_id"] == "legacy-unversioned"
    assert assumptions["vat_multiplier"] == 1.21
    assert assumptions["vat_ruleset_hash"] is None
