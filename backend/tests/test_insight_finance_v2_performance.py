"""Static regression guard for the bounded Finance v2 row query."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT / "db" / "migrations" / "060_insight_finance_v2_performance.sql"
).read_text(encoding="utf-8")


def test_finance_v2_materializes_rows_once_without_expanding_snapshot() -> None:
    assert "finance_rows AS MATERIALIZED" in SQL
    assert SQL.count("FROM reporting_finance_preferred_rows_v1") == 1
    assert "reporting_source_snapshot_v7" not in SQL
    assert "GROUP BY row.period" in SQL
    assert "metadata.period = finance.period" in SQL


def test_finance_v2_contract_and_reader_grant_remain_stable() -> None:
    assert "CREATE OR REPLACE VIEW reporting_finance_month_v2" in SQL
    assert "estimated_rows_visible" in SQL
    assert "finance_unallocated_rows_visible" in SQL
    assert "finance_unmapped_rows_visible" in SQL
    assert "GRANT SELECT ON TABLE reporting_finance_month_v2" in SQL
    assert "DROP " not in SQL.upper()
