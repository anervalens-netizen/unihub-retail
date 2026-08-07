"""Static contracts for complete additive Insight Compensation/Finance v2 views."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "db" / "migrations" / "059_insight_full_visibility_read_models.sql"
).read_text(encoding="utf-8")


def _view_sql(view_name: str) -> str:
    marker = f"CREATE OR REPLACE VIEW {view_name}"
    start = SQL.index(marker)
    next_view = SQL.find("CREATE OR REPLACE VIEW ", start + len(marker))
    return SQL[start : next_view if next_view != -1 else len(SQL)]


def _view_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\) WITH \(security_barrier = true\)",
        SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def test_snapshot_v7_is_additive_and_replaces_only_the_two_broken_domains() -> None:
    assert _view_columns("reporting_source_snapshot_v7") == (
        "domain", "period", "source", "source_generation", "authority",
        "authority_head", "contract_version", "rule_version", "status", "as_of",
        "cutoff", "is_final", "coverage_numerator", "coverage_denominator",
        "produced_at", "warnings",
    )
    snapshot = _view_sql("reporting_source_snapshot_v7")
    assert "FROM reporting_source_snapshot_v6 AS snapshot" in snapshot
    assert "snapshot.domain NOT IN ('compensation', 'finance')" in snapshot
    assert "FROM salary_records AS salary" in snapshot
    assert "FROM reporting_finance_preferred_rows_v1 AS finance" in snapshot
    assert "'official'::text" in snapshot
    assert "CREATE OR REPLACE VIEW reporting_source_snapshot_v6" not in SQL


def test_compensation_v2_keeps_every_salary_row_without_private_cnp() -> None:
    person_columns = _view_columns("reporting_compensation_person_month_v2")
    person = _view_sql("reporting_compensation_person_month_v2")
    aggregate = _view_sql("reporting_compensation_month_v2")

    assert {
        "salary_row_id", "person_id", "full_name", "total_salary", "company_name",
        "site_code", "salary_location", "store_location", "regional", "asm",
        "linked_agent_codes", "record_source_state", "source_file", "source_row",
    }.issubset(person_columns)
    assert "salary.id" in person
    assert "LEFT JOIN salary_import_batches" in person
    assert "LEFT JOIN stores" in person
    assert "LEFT JOIN LATERAL" in person
    assert "link.effective_from_month <=" in person
    assert "HAVING" not in person
    assert ">= 2000" not in person
    assert "batch.status = 'applied'" not in person
    assert "approval_artifact" not in person
    assert "cnp" not in person.lower()
    assert "AVG(total_salary)" in aggregate
    assert "COUNT(*)::bigint AS person_count" in aggregate
    assert "HAVING" not in aggregate


def test_finance_v2_matches_retail_precedence_and_keeps_unassigned_rows() -> None:
    preferred = _view_sql("reporting_finance_preferred_rows_v1")
    finance_columns = _view_columns("reporting_finance_month_v2")

    assert "FROM store_pnl_monthly AS pnl" in preferred
    assert "GROUP BY company_name, period, canonical_site_code" in preferred
    assert "bool_or(data_kind = 'actual')" in preferred
    assert "THEN 'actual' ELSE 'estimated'" in preferred
    assert "__FINANCE_UNALLOCATED__" in preferred
    assert "row.linked_site_code IS NULL" in preferred
    assert {"data_kind", "is_unallocated", "is_unmapped", "source_row_id"}.issubset(
        finance_columns
    )
    assert "store_pnl_generation_heads" not in preferred
    assert "store_pnl_generation_rows" not in preferred


def test_reader_grants_only_complete_views_not_raw_sources_or_helper() -> None:
    grant = SQL[SQL.index("DO $$") :]
    for view_name in (
        "reporting_source_snapshot_v7",
        "reporting_compensation_person_month_v2",
        "reporting_compensation_month_v2",
        "reporting_finance_month_v2",
    ):
        assert view_name in grant
    assert "reporting_finance_preferred_rows_v1" not in grant
    assert "salary_records" not in grant
    assert "store_pnl_monthly" not in grant
    assert "ALL TABLES" not in grant
    assert "DROP " not in SQL.upper()
