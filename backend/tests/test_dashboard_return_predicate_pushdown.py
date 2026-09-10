"""Regression guards for filtering return rows before dashboard aggregation."""
from __future__ import annotations

from repositories.dashboard import _monthly_history_sql
from services.dashboard.query_managers import _regional_base_query


def _assert_return_rows_are_filtered_before_aggregation(sql: str) -> None:
    return_cte = sql.split("return_summary AS (", 1)[1].split("GROUP BY", 1)[0]

    filter_clause = return_cte.split("FILTER (", 1)[1].split(") AS return_receipt_count", 1)[0]
    assert "st.quantity < 0" in filter_clause
    assert "st.bon_nr IS NOT NULL" in filter_clause

    scan_clause = return_cte.split("FROM sales_transactions st", 1)[1]
    where_clause = scan_clause.split("WHERE", 1)[1]
    assert "st.quantity < 0" in where_clause
    assert "st.bon_nr IS NOT NULL" in where_clause


def test_regional_return_summary_pushes_return_predicates_into_where() -> None:
    sql = _regional_base_query(
        "st.bon_nr",
        False,
        "true",
        ["agg.import_month = $1"],
    )

    _assert_return_rows_are_filtered_before_aggregation(sql)


def test_monthly_history_return_summary_pushes_return_predicates_into_where() -> None:
    sql = _monthly_history_sql(
        "",
        [],
        [],
        [],
        "st.bon_nr",
    )

    _assert_return_rows_are_filtered_before_aggregation(sql)
