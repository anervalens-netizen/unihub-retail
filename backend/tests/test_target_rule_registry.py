from __future__ import annotations

from copy import deepcopy
import os
from decimal import Decimal
from typing import Any

import asyncpg
import pytest

from db.connection import close_db_pool, get_pool
from repositories.target_calculator import TargetCalculatorRepository

from services.target_rule_registry import (
    TargetRuleSetValidationError,
    canonical_rules_hash,
    profitability_assumptions,
    store_salary_parameters,
    target_rule_set_from_snapshot,
    validate_target_rule_set,
)


def make_rule_set_record(target_month: str = "2026-06") -> dict[str, Any]:
    if target_month < "2025-08":
        rule_id, rate, multiplier = "ro-standard-vat-19", "0.19", "1.19"
    else:
        rule_id, rate, multiplier = "ro-standard-vat-21", "0.21", "1.21"
    rules = {
        "vat": {
            "ruleset_id": "ro-standard-vat-v1",
            "rule_id": rule_id,
            "rate": rate,
            "multiplier": multiplier,
        },
        "salary": {
            "pnl_factor": "1.5",
            "meal_vouchers_per_agent": "100",
            "sales_commission_rate": "0.05",
            "assumed_attainment": "0.80",
            "default_agent_count": 2,
            "base_salary": "3000",
        },
        "store_exceptions": {
            "SITE01": {"agent_count": 4, "base_salary": "3100"},
        },
    }
    return {
        "id": "target-finance-test-v1",
        "version": 1,
        "effective_from_month": "1900-01",
        "effective_to_month": None,
        "rules": rules,
        "rules_sha256": canonical_rules_hash(rules),
    }


def test_rule_set_is_effective_dated_hashed_and_has_valid_business_mapping() -> None:
    record = make_rule_set_record()

    rule_set = validate_target_rule_set(record, "2026-06")

    assert rule_set.rules_hash == record["rules_sha256"]
    assert profitability_assumptions(rule_set)["vat_multiplier"] == 1.21
    assert store_salary_parameters(rule_set, "SITE01") == (4, 3100)
    assert store_salary_parameters(rule_set, "SITE02") == (2, 3000)


def test_rule_set_rejects_tampering_and_invalid_store_mapping() -> None:
    record = make_rule_set_record()
    tampered = deepcopy(record)
    tampered["rules"]["salary"]["base_salary"] = "9999"  # type: ignore[index]
    with pytest.raises(TargetRuleSetValidationError, match="Hash"):
        validate_target_rule_set(tampered, "2026-06")

    invalid_mapping = make_rule_set_record()
    invalid_mapping["rules"]["store_exceptions"]["SITE01"]["unknown"] = 1  # type: ignore[index]
    invalid_mapping["rules_sha256"] = canonical_rules_hash(invalid_mapping["rules"])  # type: ignore[arg-type]
    with pytest.raises(TargetRuleSetValidationError, match="neacceptate"):
        validate_target_rule_set(invalid_mapping, "2026-06")


def test_snapshot_revalidates_without_reading_current_registry() -> None:
    rule_set = validate_target_rule_set(make_rule_set_record(), "2026-06")

    restored = target_rule_set_from_snapshot(rule_set.snapshot(), "2026-06")
    tampered_snapshot = rule_set.snapshot()
    tampered_snapshot["rules"]["salary"]["base_salary"] = "9999"

    assert restored is not None
    assert restored.rule_set_id == rule_set.rule_set_id
    assert restored.rules == rule_set.rules
    with pytest.raises(TargetRuleSetValidationError, match="Hash"):
        target_rule_set_from_snapshot(tampered_snapshot, "2026-06")

    unknown_schema = rule_set.snapshot()
    unknown_schema["schema_version"] = 2
    with pytest.raises(TargetRuleSetValidationError, match="Schema"):
        target_rule_set_from_snapshot(unknown_schema, "2026-06")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_registry_uses_contiguous_from_to_intervals_and_blocks_legacy_mutations() -> None:
    pool = await get_pool()
    repo = TargetCalculatorRepository(pool)
    try:
        legacy = await repo.get_effective_target_rule_set("2025-07")
        effective = await repo.get_effective_target_rule_set("2025-08")
        assert legacy is not None and effective is not None
        assert legacy["id"] == "target-finance-legacy-19-v1"
        assert legacy["effective_to_month"] == "2025-08"
        assert effective["id"] == "target-finance-21-v1"

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError, match="immutable"):
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE target_calculator_rule_sets
                        SET rules = jsonb_set(rules, '{salary,base_salary}', '9999'::jsonb)
                        WHERE id = $1
                        """,
                        "target-finance-21-v1",
                    )

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError, match="gap"):
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE target_calculator_rule_sets SET effective_to_month = $1 WHERE id = $2",
                        "2025-07",
                        "target-finance-legacy-19-v1",
                    )
                    await conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    finally:
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_legacy_row_mutation_is_blocked_for_ruleset_draft() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO stores (site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month)
                    VALUES ('TRULEM01', 'Rule store', 'Test', 'Test', 'Test', '2099-10', '2099-10')
                    ON CONFLICT (site_code) DO NOTHING
                    """
                )
                scenario_id = await conn.fetchval(
                    """
                    INSERT INTO target_scenarios (
                        target_month, cohort_month, total_target, min_floor,
                        previous_month_floor_pct, calculation_method, source_months, warnings, calculation_params
                    )
                    VALUES ('2099-12', '2099-11', 100, 0, 0, 'seasonal_blended_multiyear_v2_ruleset', '[]', '[]', '{}')
                    ON CONFLICT (target_month) DO UPDATE SET calculation_method = EXCLUDED.calculation_method
                    RETURNING id
                    """
                )
                await conn.execute(
                    """
                    INSERT INTO target_scenario_rows (
                        scenario_id, site_code, locatie, firma, regional, asm,
                        calculated_weight, floor_target, proposed_target, final_target, history, calculation_details
                    )
                    VALUES ($1, 'TRULEM01', 'Rule store', 'Test', 'Test', 'Test', 1, 0, 100, NULL, '[]', '{}')
                    ON CONFLICT (scenario_id, site_code) DO UPDATE SET final_target = NULL
                    """,
                    scenario_id,
                )
                with pytest.raises(asyncpg.PostgresError, match="legacy target mutation blocked"):
                    async with conn.transaction():
                        await conn.execute(
                            "UPDATE target_scenario_rows SET final_target = $2 WHERE scenario_id = $1 AND site_code = 'TRULEM01'",
                            scenario_id,
                            Decimal("100"),
                        )
                await conn.execute("DELETE FROM target_scenarios WHERE id = $1", scenario_id)
                await conn.execute("DELETE FROM stores WHERE site_code = 'TRULEM01'")
    finally:
        await close_db_pool()
