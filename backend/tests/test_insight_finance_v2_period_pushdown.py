"""Static guards for Finance v2 period-bounded execution."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "db" / "migrations" / "061_insight_finance_v2_period_pushdown.sql"
).read_text(encoding="utf-8")


def test_preference_is_one_window_pass_with_explicit_period_date() -> None:
    assert "bool_or(row.data_kind = 'actual') OVER" in SQL
    assert "PARTITION BY row.company_name, row.period, row.canonical_site_code" in SQL
    assert "period_date" in SQL
    assert "MATERIALIZED" not in SQL
    assert "GROUP BY company_name, period, canonical_site_code" not in SQL


def test_finance_metadata_is_period_local_and_snapshot_independent() -> None:
    finance = SQL[SQL.index("CREATE OR REPLACE VIEW reporting_finance_month_v2") :]
    assert "PARTITION BY finance.period_date" in finance
    assert "reporting_source_snapshot_v7" not in finance
    assert "estimated_rows_visible" in finance
    assert "finance_unallocated_rows_visible" in finance
    assert "finance_unmapped_rows_visible" in finance
    assert "GRANT SELECT ON TABLE reporting_finance_month_v2" in finance
    assert "DROP " not in SQL.upper()
