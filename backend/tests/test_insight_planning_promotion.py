"""Planning v2 promotion, integrity and fail-closed reporting contract."""
from __future__ import annotations

import json
import os
from pathlib import Path

import asyncpg
import pytest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "051_insight_planning_promotion_read_model.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
ACL_MIGRATION = MIGRATION.with_name("052_insight_planning_hash_acl.sql")
ACL_SQL = ACL_MIGRATION.read_text(encoding="utf-8")


def test_planning_v2_contract_is_head_only_and_append_only() -> None:
    assert "CREATE TABLE planning_forecast_heads" in SQL
    assert "CREATE TABLE planning_forecast_promotions" in SQL
    assert "planning forecast promotion ledger is append-only" in SQL
    assert "public.advance_planning_forecast_head" in SQL
    assert "SECURITY DEFINER" in SQL
    assert "p_expected_revision" in SQL
    assert "approval_artifact_sha256" in SQL
    assert "forecast_run_not_promoted" in SQL
    assert "promoted_forecast_integrity_mismatch" in SQL
    assert "reporting_source_snapshot_v3" in SQL
    assert "reporting_planning_scenario_v2" in SQL
    assert "FROM eligible_forecast_head AS head" in SQL
    assert "FROM ai_forecast_runs AS forecast" not in SQL
    assert "scenario.rule_set_snapshot = jsonb_build_object(" in SQL
    assert "JOIN target_calculator_effective_rule_sets AS registry" in SQL
    assert "GRANT EXECUTE ON FUNCTION public.advance_planning_forecast_head" in SQL
    assert "TO unihub_operations" in SQL
    assert "TO unihub_business_write" not in SQL
    assert "DROP TABLE" not in SQL.upper()
    assert "DROP VIEW" not in SQL.upper()


def test_planning_v2_digest_bridge_is_narrow_and_read_only() -> None:
    assert "ALTER FUNCTION public.planning_forecast_run_sha256(BIGINT)" in ACL_SQL
    assert "SECURITY DEFINER" in ACL_SQL
    assert "SET search_path = pg_catalog, public" in ACL_SQL
    assert (
        "GRANT EXECUTE ON FUNCTION public.planning_forecast_run_sha256(BIGINT)"
        in ACL_SQL
    )
    assert "TO unihub_insight_reader" in ACL_SQL
    assert "FROM PUBLIC" in ACL_SQL
    assert "GRANT SELECT" not in ACL_SQL
    assert "GRANT EXECUTE" not in ACL_SQL.split("TO unihub_insight_reader", 1)[1]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires the isolated PostgreSQL contract database",
)
async def test_planning_v2_requires_head_exact_target_and_preserves_rollback_lineage() -> None:
    from db.migration_runner import run_migrations

    database_url = os.environ["DATABASE_URL"]
    setup = await asyncpg.connect(database_url)
    created_reader_role = not await setup.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader')"
    )
    try:
        if created_reader_role:
            await setup.execute("CREATE ROLE unihub_insight_reader NOLOGIN")
        await setup.execute(
            "GRANT SELECT ON TABLE reporting_source_snapshot_v3, "
            "reporting_planning_scenario_v2 TO unihub_insight_reader"
        )
        await setup.execute(
            "DELETE FROM schema_migrations WHERE filename = $1", ACL_MIGRATION.name
        )
    finally:
        await setup.close()
    assert await run_migrations(database_url) == [ACL_MIGRATION.name]

    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month
            ) VALUES
                ('PLAN-A', 'Planning A', 'Mobiup', 'RM', 'ASM', '2199-01', '2199-12'),
                ('PLAN-B', 'Planning B', 'Mobiup', 'RM', 'ASM', '2199-01', '2199-12')
            ON CONFLICT (site_code) DO NOTHING
            """
        )
        first_run = await connection.fetchval(
            """
            INSERT INTO ai_forecast_runs (
                forecast_month, source_month, metric, horizon, model_name,
                model_mode, variant, status, generated_at
            ) VALUES (
                '2199-02', '2199-01', 'sales_value', 'current_month',
                'fixture', 'offline', 'first', 'completed', '2199-02-01T00:00:00Z'
            ) RETURNING id
            """
        )
        second_run = await connection.fetchval(
            """
            INSERT INTO ai_forecast_runs (
                forecast_month, source_month, metric, horizon, model_name,
                model_mode, variant, status, generated_at
            ) VALUES (
                '2199-02', '2199-01', 'sales_value', 'current_month',
                'fixture', 'offline', 'second', 'completed', '2199-02-02T00:00:00Z'
            ) RETURNING id
            """
        )
        for run_id, multiplier in ((first_run, 1), (second_run, 2)):
            await connection.executemany(
                """
                INSERT INTO ai_forecast_store_month (
                    run_id, site_code, forecast_sales, metadata
                ) VALUES ($1, $2, $3, '{}'::jsonb)
                """,
                [
                    (run_id, "PLAN-A", 100 * multiplier),
                    (run_id, "PLAN-B", 200 * multiplier),
                ],
            )

        before = await connection.fetchrow(
            """
            SELECT status, warnings
            FROM reporting_source_snapshot_v3
            WHERE domain = 'planning' AND period = '2199-02'
            """
        )
        assert before is not None
        assert before["status"] == "partial"
        assert "forecast_run_not_promoted" in before["warnings"]
        assert await connection.fetchval(
            "SELECT COUNT(*) FROM reporting_planning_scenario_v2 WHERE period = '2199-02'"
        ) == 0

        await connection.execute("SET ROLE unihub_operations")
        promoted = await connection.fetchrow(
            """
            SELECT * FROM public.advance_planning_forecast_head(
                '2199-02', 'sales_value', 'current_month', $1, 0,
                $2, 'fixture-operator', 'approved fixture', 'promote'
            )
            """,
            first_run,
            "a" * 64,
        )
        assert promoted is not None and promoted["revision"] == 1
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(
                """
                UPDATE planning_forecast_heads
                SET revision = revision + 1
                WHERE forecast_month = '2199-02'
                """
            )
        with pytest.raises(asyncpg.RaiseError, match="revision CAS failed"):
            await connection.fetchrow(
                """
                SELECT * FROM public.advance_planning_forecast_head(
                    '2199-02', 'sales_value', 'current_month', $1, 0,
                    $2, 'fixture-operator', 'stale fixture', 'promote'
                )
                """,
                second_run,
                "b" * 64,
            )
        await connection.execute("RESET ROLE")

        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM reporting_planning_scenario_v2
            WHERE period = '2199-02' AND authority_kind = 'forecast'
            """
        ) == 2

        await connection.execute("SET ROLE unihub_insight_reader")
        reader_snapshot = await connection.fetchrow(
            """
            SELECT status, warnings
            FROM reporting_source_snapshot_v3
            WHERE domain = 'planning' AND period = '2199-02'
            """
        )
        assert reader_snapshot is not None
        assert reader_snapshot["status"] == "partial"
        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM reporting_planning_scenario_v2
            WHERE period = '2199-02' AND authority_kind = 'forecast'
            """
        ) == 2
        assert await connection.fetchval(
            """
            SELECT has_function_privilege(
                current_user,
                'public.planning_forecast_run_sha256(bigint)',
                'EXECUTE'
            )
            """
        ) is True
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.fetchval("SELECT COUNT(*) FROM ai_forecast_runs")
        await connection.execute("RESET ROLE")

        rule = await connection.fetchrow(
            """
            SELECT id, version, effective_from_month, rules, rules_sha256
            FROM target_calculator_rule_sets
            ORDER BY effective_from_month DESC
            LIMIT 1
            """
        )
        assert rule is not None
        rules = rule["rules"]
        if isinstance(rules, str):
            rules = json.loads(rules)
        snapshot = {
            "schema_version": 1,
            "rule_set_id": rule["id"],
            "version": rule["version"],
            "effective_from_month": rule["effective_from_month"],
            "effective_to_month": None,
            "rules_hash": rule["rules_sha256"],
            "rules": dict(rules),
        }
        scenario_id = await connection.fetchval(
            """
            INSERT INTO target_scenarios (
                target_month, cohort_month, total_target, status, revision,
                rule_set_id, rule_set_hash, rule_set_snapshot, finalized_at
            ) VALUES (
                '2199-02', '2199-01', 500, 'finalized', 1,
                $1, $2, $3::jsonb, '2199-02-03T00:00:00Z'
            ) RETURNING id
            """,
            rule["id"],
            rule["rules_sha256"],
            json.dumps(snapshot),
        )
        await connection.executemany(
            """
            INSERT INTO target_scenario_rows (
                scenario_id, site_code, locatie, firma, regional, asm, final_target
            ) VALUES ($1, $2, $3, 'Mobiup', 'RM', 'ASM', $4)
            """,
            [
                (scenario_id, "PLAN-A", "Planning A", 200),
                (scenario_id, "PLAN-B", "Planning B", 300),
            ],
        )
        exact = await connection.fetchrow(
            """
            SELECT status, is_final, warnings
            FROM reporting_source_snapshot_v3
            WHERE domain = 'planning' AND period = '2199-02'
            """
        )
        assert exact is not None
        assert exact["status"] == "official" and exact["is_final"] is True
        assert exact["warnings"] == []
        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM reporting_planning_scenario_v2
            WHERE period = '2199-02' AND authority_kind = 'target'
            """
        ) == 2

        legacy_scenario = await connection.fetchval(
            """
            INSERT INTO target_scenarios (
                target_month, cohort_month, total_target, status, revision, finalized_at
            ) VALUES (
                '2199-03', '2199-02', 100, 'finalized', 1, '2199-03-01T00:00:00Z'
            ) RETURNING id
            """
        )
        await connection.execute(
            """
            INSERT INTO target_scenario_rows (
                scenario_id, site_code, locatie, firma, regional, asm, final_target
            ) VALUES ($1, 'PLAN-A', 'Planning A', 'Mobiup', 'RM', 'ASM', 100)
            """,
            legacy_scenario,
        )
        legacy = await connection.fetchrow(
            """
            SELECT status, warnings
            FROM reporting_source_snapshot_v3
            WHERE domain = 'planning' AND period = '2199-03'
            """
        )
        assert legacy is not None and legacy["status"] == "partial"
        assert "finalized_target_lacks_a_versioned_rule_snapshot_or_values" in legacy["warnings"]
        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM reporting_planning_scenario_v2
            WHERE period = '2199-03' AND authority_kind = 'target'
            """
        ) == 0

        await connection.execute("SET ROLE unihub_operations")
        second = await connection.fetchrow(
            """
            SELECT * FROM public.advance_planning_forecast_head(
                '2199-02', 'sales_value', 'current_month', $1, 1,
                $2, 'fixture-operator', 'approved replacement', 'promote'
            )
            """,
            second_run,
            "b" * 64,
        )
        assert second is not None and second["revision"] == 2
        rollback = await connection.fetchrow(
            """
            SELECT * FROM public.advance_planning_forecast_head(
                '2199-02', 'sales_value', 'current_month', $1, 2,
                $2, 'fixture-operator', 'approved rollback', 'rollback'
            )
            """,
            first_run,
            "c" * 64,
        )
        assert rollback is not None and rollback["revision"] == 3
        await connection.execute("RESET ROLE")
        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM planning_forecast_promotions
            WHERE forecast_month = '2199-02'
            """
        ) == 3

        await connection.execute(
            """
            UPDATE ai_forecast_store_month
            SET forecast_sales = forecast_sales + 1
            WHERE run_id = $1 AND site_code = 'PLAN-A'
            """,
            first_run,
        )
        broken = await connection.fetchrow(
            """
            SELECT status, warnings
            FROM reporting_source_snapshot_v3
            WHERE domain = 'planning' AND period = '2199-02'
            """
        )
        assert broken is not None and broken["status"] == "partial"
        assert "promoted_forecast_integrity_mismatch" in broken["warnings"]
        assert await connection.fetchval(
            """
            SELECT COUNT(*) FROM reporting_planning_scenario_v2
            WHERE period = '2199-02' AND authority_kind = 'forecast'
            """
        ) == 0
    finally:
        await connection.execute("RESET ROLE")
        await connection.close()
        if created_reader_role:
            cleanup = await asyncpg.connect(database_url)
            try:
                await cleanup.execute("DROP OWNED BY unihub_insight_reader")
                await cleanup.execute("DROP ROLE unihub_insight_reader")
            finally:
                await cleanup.close()
