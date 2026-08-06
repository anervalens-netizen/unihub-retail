"""Static database-contract checks for Insight's versioned Retail read models."""
from __future__ import annotations

import os
from pathlib import Path
import re
from uuid import UUID

import asyncpg
import pytest


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "047_insight_reporting_read_models.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
SALES_DAY_MIGRATION = MIGRATION.with_name("048_insight_sales_day_read_model.sql")
SALES_DAY_SQL = SALES_DAY_MIGRATION.read_text(encoding="utf-8")
VISITS_V2_MIGRATION = MIGRATION.with_name(
    "049_insight_visits_team_leader_read_model.sql"
)
VISITS_V2_SQL = VISITS_V2_MIGRATION.read_text(encoding="utf-8")


def _view_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\)\s*WITH \(security_barrier = true\)",
        SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def _view_sql(view_name: str) -> str:
    marker = f"CREATE OR REPLACE VIEW {view_name}"
    start = SQL.index(marker)
    next_view = SQL.find("CREATE OR REPLACE VIEW ", start + len(marker))
    return SQL[start : next_view if next_view != -1 else len(SQL)]


def _sales_day_columns() -> tuple[str, ...]:
    match = re.search(
        r"CREATE OR REPLACE VIEW reporting_sales_day_v1 \((.*?)\)\nWITH \(security_barrier = true\)",
        SALES_DAY_SQL,
        flags=re.DOTALL,
    )
    assert match, "missing versioned security-barrier daily Sales view"
    return tuple(column.strip() for column in match.group(1).split(","))


def _visits_v2_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\)\s*WITH \(security_barrier = true\)",
        VISITS_V2_SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def test_sales_day_contract_is_observed_additive_and_snapshot_bound() -> None:
    assert _sales_day_columns() == (
        "period",
        "sale_date",
        "site_code",
        "locatie",
        "firma",
        "regional",
        "asm",
        "agent",
        "net_sales",
        "net_quantity",
        "positive_quantity",
        "return_quantity",
        "receipt_count",
        "receipt_2plus_count",
        "coverage_state",
        "source",
        "source_generation",
        "authority",
        "authority_head",
        "contract_version",
        "rule_version",
        "status",
        "as_of",
        "cutoff",
        "is_final",
        "coverage_numerator",
        "coverage_denominator",
        "produced_at",
        "warnings",
    )
    assert "FROM reporting_agent_day AS daily" in SALES_DAY_SQL
    assert "FROM reporting_item_day AS item" in SALES_DAY_SQL
    assert "JOIN reporting_source_snapshot_v1 AS snapshot" in SALES_DAY_SQL
    assert "snapshot.domain = 'sales'" in SALES_DAY_SQL
    assert "'observed'::text" in SALES_DAY_SQL
    assert "generate_series" not in SALES_DAY_SQL
    assert "sales_transactions" not in SALES_DAY_SQL
    assert "GRANT SELECT ON TABLE reporting_sales_day_v1" in SALES_DAY_SQL
    assert "DROP " not in SALES_DAY_SQL.upper()


def test_visits_v2_uses_the_authoritative_team_leader_snapshot() -> None:
    assert _visits_v2_columns("reporting_source_snapshot_v2") == _view_columns(
        "reporting_source_snapshot_v1"
    )
    assert _visits_v2_columns("reporting_visit_month_v2") == (
        "period",
        "team_leader_id",
        "team_leader_name",
        "site_code",
        "locatie",
        "firma",
        "regional",
        "asm",
        "total_visits",
        "avg_completion",
        "avg_duration",
        "distinct_stores",
        "checklist_score",
        "approved_pct",
        "source",
        "source_generation",
        "authority",
        "authority_head",
        "contract_version",
        "rule_version",
        "status",
        "as_of",
        "cutoff",
        "is_final",
        "coverage_numerator",
        "coverage_denominator",
        "produced_at",
        "warnings",
    )
    assert "FROM fieldops_visits AS visit" in VISITS_V2_SQL
    assert "to_regclass('public.fieldops_visits') IS NULL" in VISITS_V2_SQL
    assert "visit.team_leader_id" in VISITS_V2_SQL
    assert "visit.team_leader_name" in VISITS_V2_SQL
    assert "JOIN stores AS store" in VISITS_V2_SQL
    assert "store.site_code = visit.magazin" in VISITS_V2_SQL
    assert "visit.status <> 'draft'" in VISITS_V2_SQL
    assert "store.locatie NOT ILIKE 'TR %'" in VISITS_V2_SQL
    assert "store.locatie NOT ILIKE '%cartel%'" in VISITS_V2_SQL
    assert "legacy_asm" not in VISITS_V2_SQL
    assert "visits_snapshot" not in VISITS_V2_SQL
    assert "reporting_source_snapshot_v1 AS snapshot" in VISITS_V2_SQL
    assert "snapshot.domain <> 'visits'" in VISITS_V2_SQL
    assert "GRANT SELECT ON TABLE " in VISITS_V2_SQL
    assert "reporting_source_snapshot_v2, reporting_visit_month_v2" in VISITS_V2_SQL
    assert "DROP " not in VISITS_V2_SQL.upper()


def test_source_snapshot_v1_has_the_exact_cross_domain_contract() -> None:
    assert _view_columns("reporting_source_snapshot_v1") == (
        "domain",
        "period",
        "source",
        "source_generation",
        "authority",
        "authority_head",
        "contract_version",
        "rule_version",
        "status",
        "as_of",
        "cutoff",
        "is_final",
        "coverage_numerator",
        "coverage_denominator",
        "produced_at",
        "warnings",
    )
    assert "scope_key" not in _view_sql("reporting_source_snapshot_v1")


def test_all_insight_read_models_are_additive_versioned_and_barriered() -> None:
    expected_views = {
        "reporting_source_snapshot_v1",
        "reporting_campaign_month_v1",
        "reporting_workforce_month_v1",
        "reporting_compensation_month_v1",
        "reporting_visit_month_v1",
        "reporting_finance_month_v1",
        "reporting_planning_scenario_v1",
    }
    actual_views = set(
        re.findall(r"CREATE OR REPLACE VIEW (reporting_[a-z_]+_v1)", SQL)
    )
    assert actual_views == expected_views
    assert "DROP " not in SQL.upper()
    for view_name in expected_views:
        _view_columns(view_name)


def test_compensation_contract_is_aggregate_only_and_fails_closed() -> None:
    columns = _view_columns("reporting_compensation_month_v1")
    assert not {"person_id", "full_name", "site_code", "agent"}.intersection(columns)

    view_sql = _view_sql("reporting_compensation_month_v1")
    assert "JOIN salary_import_batches AS batch" in view_sql
    assert "batch.status = 'applied'" in view_sql
    assert "batch.approval_artifact_sha256 IS NOT NULL" in view_sql
    assert "HAVING COUNT(*) >= 3" in view_sql
    assert "eligible_person_count" in columns
    assert "'__ALL__'::text AS company_name" in view_sql
    assert (
        "AVG(person_month.total_salary) FILTER (WHERE person_month.total_salary >= 2000)"
        in view_sql
    )
    assert "percentile_cont(0.5) WITHIN GROUP (ORDER BY person_month.total_salary)" in view_sql
    assert "salary.full_name" not in view_sql
    assert "salary.site_code" not in view_sql

    snapshot_sql = _view_sql("reporting_source_snapshot_v1")
    assert "compensation.produced_at," in snapshot_sql
    assert "approved-salary-batches:" in snapshot_sql
    assert "now()" not in snapshot_sql


def test_finance_contract_reads_only_current_promoted_generation_actuals() -> None:
    view_sql = _view_sql("reporting_finance_month_v1")
    assert "FROM store_pnl_generation_heads AS head" in view_sql
    assert "generation.state = 'promoted'" in view_sql
    assert "row.row_set = 'candidate'" in view_sql
    assert "'actual'::text" in view_sql
    assert "FROM store_pnl_monthly" not in view_sql


def test_planning_contract_keeps_forecast_run_and_target_scenario_authority() -> None:
    snapshot_sql = _view_sql("reporting_source_snapshot_v1")
    planning_sql = _view_sql("reporting_planning_scenario_v1")
    assert "completed_forecast_candidates" in snapshot_sql
    assert "finalized_target_candidates" in snapshot_sql
    assert "PARTITION BY forecast.forecast_month" in snapshot_sql
    assert "PARTITION BY scenario.target_month" in snapshot_sql
    assert "'planning'::text" in snapshot_sql
    assert "'planning_forecast'::text" not in snapshot_sql
    assert "'planning_target'::text" not in snapshot_sql
    assert "'forecast-run:' || forecast.id::text" in planning_sql
    assert "'target-scenario:' || scenario.id::text" in planning_sql
    assert "scenario.revision" in planning_sql
    assert "scenario.rule_set_hash" in planning_sql


def test_acl_contract_exposes_views_without_breaking_the_n_minus_one_consumer() -> None:
    assert "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'unihub_insight_reader')" in SQL
    assert "REVOKE ALL ON TABLE " not in SQL
    for view_name in (
        "reporting_source_snapshot_v1",
        "reporting_campaign_month_v1",
        "reporting_workforce_month_v1",
        "reporting_compensation_month_v1",
        "reporting_visit_month_v1",
        "reporting_finance_month_v1",
        "reporting_planning_scenario_v1",
    ):
        assert view_name in SQL


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires the isolated PostgreSQL contract database",
)
async def test_migration_publishes_views_and_preserves_n_minus_one_acl_in_postgres() -> None:
    """Exercise the conditional role path on an isolated, disposable database."""
    from db.migration_runner import run_migrations

    database_url = os.environ["DATABASE_URL"]
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute("CREATE ROLE unihub_insight_reader NOLOGIN")
        await connection.execute(
            "GRANT SELECT ON TABLE salary_records, agent_salary_links, "
            "store_pnl_monthly, store_pnl_generations, store_pnl_generation_scopes, "
            "store_pnl_generation_rows, store_pnl_generation_heads "
            "TO unihub_insight_reader"
        )
        await connection.execute(
            "DELETE FROM schema_migrations WHERE filename = $1",
            MIGRATION.name,
        )
    finally:
        await connection.close()

    assert await run_migrations(database_url) == [MIGRATION.name]

    connection = await asyncpg.connect(database_url)
    try:
        assert await connection.fetchval(
            "SELECT has_table_privilege("
            "'unihub_insight_reader', 'public.reporting_compensation_month_v1', 'SELECT'"
            ")"
        )
        assert await connection.fetchval(
            "SELECT has_table_privilege("
            "'unihub_insight_reader', 'public.salary_records', 'SELECT'"
            ")"
        )
        assert await connection.fetchval(
            "SELECT has_table_privilege("
            "'unihub_insight_reader', 'public.store_pnl_generation_rows', 'SELECT'"
            ")"
        )
        columns = await connection.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "AND table_name = 'reporting_source_snapshot_v1' "
            "ORDER BY ordinal_position"
        )
        assert tuple(row["column_name"] for row in columns) == _view_columns(
            "reporting_source_snapshot_v1"
        )

        batch_id = UUID("00000000-0000-0000-0000-000000000047")
        await connection.execute(
            "INSERT INTO salary_import_batches ("
            "batch_id, year, month, status, manifest, manifest_sha256, applied_by, "
            "approval_artifact_sha256, reviewer_key_id"
            ") VALUES ($1, 2099, 1, 'applied', '{}'::jsonb, $2, 'test', $3, 'test-key')",
            batch_id,
            "a" * 64,
            "b" * 64,
        )
        people = [
            ("sp1_" + "c" * 64, "fixture a"),
            ("sp1_" + "d" * 64, "fixture b"),
            ("sp1_" + "e" * 64, "fixture c"),
        ]
        await connection.executemany(
            "INSERT INTO salary_private.people (person_id, normalized_name, identity_source) "
            "VALUES ($1, $2, 'name')",
            people,
        )
        await connection.executemany(
            "INSERT INTO salary_records ("
            "year, month, full_name, total_salary, company_name, person_id, "
            "import_batch_id, source_file, source_sheet, source_row, source_sha256"
            ") VALUES (2099, 1, $1, $2, 'Mobiup', $3, $4, 'fixture.xlsx', 'salary', $5, $6)",
            [
                ("Fixture A", 1000, people[0][0], batch_id, 1, "f" * 64),
                ("Fixture B", 2000, people[1][0], batch_id, 2, "f" * 64),
                ("Fixture C", 5000, people[2][0], batch_id, 3, "f" * 64),
            ],
        )
        compensation = await connection.fetchrow(
            "SELECT eligible_person_count, payroll_total, average_salary_eligible, median_salary, status "
            "FROM reporting_compensation_month_v1 "
            "WHERE period = '2099-01' AND company_name = 'Mobiup'"
        )
        assert compensation is not None
        assert compensation["eligible_person_count"] == 3
        assert float(compensation["payroll_total"]) == 8000.0
        assert float(compensation["average_salary_eligible"]) == 3500.0
        assert float(compensation["median_salary"]) == 2000.0
        assert compensation["status"] == "official"
        all_compensation = await connection.fetchrow(
            "SELECT eligible_person_count, payroll_total, average_salary_eligible, median_salary "
            "FROM reporting_compensation_month_v1 "
            "WHERE period = '2099-01' AND company_name = '__ALL__'"
        )
        assert all_compensation is not None
        assert all_compensation["eligible_person_count"] == 3
        assert float(all_compensation["payroll_total"]) == 8000.0
        assert float(all_compensation["average_salary_eligible"]) == 3500.0
        assert float(all_compensation["median_salary"]) == 2000.0
        compensation_snapshot = await connection.fetchrow(
            "SELECT source_generation, produced_at "
            "FROM reporting_source_snapshot_v1 "
            "WHERE domain = 'compensation' AND period = '2099-01'"
        )
        assert compensation_snapshot is not None
        assert str(batch_id) in compensation_snapshot["source_generation"]
        assert compensation_snapshot == await connection.fetchrow(
            "SELECT source_generation, produced_at "
            "FROM reporting_source_snapshot_v1 "
            "WHERE domain = 'compensation' AND period = '2099-01'"
        )

        first_run = await connection.fetchval(
            "INSERT INTO ai_forecast_runs ("
            "forecast_month, source_month, metric, horizon, model_name, model_mode, variant, "
            "status, generated_at"
            ") VALUES ('2099-02', '2099-01', 'sales_value', 'current_month', "
            "'fixture', 'fixture', 'older', 'completed', '2099-02-01T00:00:00Z') "
            "RETURNING id"
        )
        latest_run = await connection.fetchval(
            "INSERT INTO ai_forecast_runs ("
            "forecast_month, source_month, metric, horizon, model_name, model_mode, variant, "
            "status, generated_at"
            ") VALUES ('2099-02', '2099-01', 'sales_value', 'current_month', "
            "'fixture', 'fixture', 'latest', 'completed', '2099-02-02T00:00:00Z') "
            "RETURNING id"
        )
        assert first_run < latest_run
        planning = await connection.fetch(
            "SELECT source_generation FROM reporting_source_snapshot_v1 "
            "WHERE domain = 'planning' AND period = '2099-02'"
        )
        assert [row["source_generation"] for row in planning] == [
            f"forecast-run:{latest_run}"
        ]
        duplicates = await connection.fetch(
            "SELECT domain, period FROM reporting_source_snapshot_v1 "
            "GROUP BY domain, period HAVING COUNT(*) > 1"
        )
        assert duplicates == []
    finally:
        await connection.close()
