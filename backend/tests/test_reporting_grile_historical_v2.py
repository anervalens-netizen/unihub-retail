"""Static contracts for additive Insight Grile historical v2 read models."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "db" / "migrations" / "058_insight_grile_historical_v2.sql").read_text(
    encoding="utf-8"
)


def _view_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\) WITH \(security_barrier = true\)",
        SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def test_v6_keeps_n_minus_one_contracts_and_exact_snapshot_shape() -> None:
    assert _view_columns("reporting_source_snapshot_v6") == (
        "domain", "period", "source", "source_generation", "authority", "authority_head",
        "contract_version", "rule_version", "status", "as_of", "cutoff", "is_final",
        "coverage_numerator", "coverage_denominator", "produced_at", "warnings",
    )
    assert "FROM reporting_source_snapshot_v5\nWHERE domain <> 'grile'" in SQL
    assert "CREATE OR REPLACE VIEW reporting_source_snapshot_v5" not in SQL
    assert "CREATE OR REPLACE VIEW reporting_grile_month_v1" not in SQL


def test_grile_v2_selects_one_whole_period_source_deterministically() -> None:
    assert "COALESCE(current.numerator, 0) > 0 AS use_current" in SQL
    assert "ROW_NUMBER() OVER" in SQL
    assert "run.status = 'completed'" in SQL
    assert "run.id DESC" in SQL
    assert "grile-current-v2:" in SQL
    assert "grile-completed-run-v2:" in SQL
    assert "grile_current_projection_empty" in SQL
    assert "grile_completed_full_run_immutable" in SQL
    assert "snapshot.source = 'grile_store_current_status'" in SQL
    assert "snapshot.source = 'grile_store_status'" in SQL


def test_historical_population_is_audited_not_the_current_active_sheet_list() -> None:
    historical = SQL[SQL.index("completed_run_sites AS"):SQL.index("CREATE OR REPLACE VIEW reporting_grile_month_v2")]
    assert "grile_run_store_generations" in historical
    assert "grile_store_status" in historical
    assert "sheet.is_active" not in historical
    assert "store.locatie NOT ILIKE 'TR%'" in historical
    assert "store.locatie NOT ILIKE '%cartel%'" in historical


def test_row_states_and_reader_grant_remain_explicit_and_narrow() -> None:
    assert "WHEN NOT row.covered OR row.error_code IS NOT NULL THEN 'unavailable'" in SQL
    assert "THEN 'partial'" in SQL
    assert "grile_fill_status_mismatch" in SQL
    assert "grile_target_status_mismatch" in SQL
    assert "grile_sales_status_mismatch" in SQL
    assert "GRANT SELECT ON TABLE reporting_source_snapshot_v6, reporting_grile_month_v2" in SQL
    assert "ALL TABLES" not in SQL
