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
    validate_store_exception_scope,
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


def test_store_exception_scope_rejects_unknown_and_alias_collisions() -> None:
    rule_set = validate_target_rule_set(make_rule_set_record(), "2026-06")
    exact_mapping = [{"site_code": "SITE01", "locatie": "Magazin 1"}]
    validate_store_exception_scope(rule_set, cohort=exact_mapping, master_rows=exact_mapping)

    with pytest.raises(TargetRuleSetValidationError, match="master data"):
        validate_store_exception_scope(
            rule_set,
            cohort=[{"site_code": "SITE01", "locatie": "Magazin 1"}],
            master_rows=[],
        )
    with pytest.raises(TargetRuleSetValidationError, match="cohorta activa"):
        validate_store_exception_scope(
            rule_set,
            cohort=[],
            master_rows=exact_mapping,
        )
    with pytest.raises(TargetRuleSetValidationError, match="alias"):
        validate_store_exception_scope(
            rule_set,
            cohort=[{"site_code": "SITE01", "locatie": "Magazin Alias"}],
            master_rows=exact_mapping,
        )
    with pytest.raises(TargetRuleSetValidationError, match="unu-la-unu"):
        validate_store_exception_scope(
            rule_set,
            cohort=[
                {"site_code": "SITE01", "locatie": "Magazin 1"},
                {"site_code": "SITE01", "locatie": "Magazin 1"},
            ],
            master_rows=[{"site_code": "SITE01", "locatie": "Magazin 1"}],
        )


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
async def test_registry_derives_successor_interval_without_rewriting_history() -> None:
    pool = await get_pool()
    repo = TargetCalculatorRepository(pool)
    try:
        legacy = await repo.get_effective_target_rule_set("2025-07")
        effective = await repo.get_effective_target_rule_set("2025-08")
        assert legacy is not None and effective is not None
        assert legacy["id"] == "target-finance-legacy-19-v1"
        assert legacy["effective_to_month"] == "2025-08"
        assert effective["id"] == "target-finance-21-v1"
        assert effective["effective_to_month"] is None

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE target_calculator_rule_sets
                        SET effective_from_month = '2025-09'
                        WHERE id = $1
                        """,
                        "target-finance-21-v1",
                    )
            source = await conn.fetchrow(
                "SELECT rules::TEXT AS rules, rules_sha256 FROM target_calculator_rule_sets WHERE id = $1",
                "target-finance-21-v1",
            )
            assert source is not None
            await conn.execute(
                """
                INSERT INTO target_calculator_rule_sets (id, version, effective_from_month, rules, rules_sha256)
                VALUES ('target-finance-append-only-v3', 3, '2099-01', $1::jsonb, $2)
                """,
                source["rules"],
                source["rules_sha256"],
            )

        async with pool.acquire() as conn:
            with pytest.raises(asyncpg.PostgresError, match="must append"):
                async with conn.transaction():
                    await conn.execute(
                        """
                        INSERT INTO target_calculator_rule_sets (id, version, effective_from_month, rules, rules_sha256)
                        VALUES ('target-finance-out-of-order-v4', 4, '2025-09', $1::jsonb, $2)
                        """,
                        source["rules"],
                        source["rules_sha256"],
                    )

        before_successor = await repo.get_effective_target_rule_set("2098-12")
        successor = await repo.get_effective_target_rule_set("2099-01")
        assert before_successor is not None and successor is not None
        assert before_successor["id"] == "target-finance-21-v1"
        assert before_successor["effective_to_month"] == "2099-01"
        assert successor["id"] == "target-finance-append-only-v3"
        assert successor["effective_to_month"] is None
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
