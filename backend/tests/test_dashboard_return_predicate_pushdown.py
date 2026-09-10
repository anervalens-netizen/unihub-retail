"""Regression guards for the Dashboard return-summary data source.

Lot 21 filtered raw return rows before aggregation.  Lot 23 materializes the
canonical return-receipt count in the reporting read model, so the guard is now
that every return summary reads ``reporting_agent_month`` and never scans raw
``sales_transactions``.  The existing scope clauses (``JOIN stores`` plus the
generated store/agent/current-scope predicates) must stay intact, because
several paths deliberately keep using current ``stores`` metadata.
"""
from __future__ import annotations

from repositories.dashboard import _monthly_history_sql
from services.dashboard.query_agents import _agent_base_query
from services.dashboard.query_managers import _regional_base_query
from services.dashboard.query_stores import _store_stats_query

_RETURN_CLAUSE = "s.locatie NOT ILIKE 'TR %'"


def _return_summary_sql(sql: str) -> str:
    body = sql.split("return_summary AS (", 1)[1]
    depth = 1
    index = 0
    while depth:
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
        index += 1
    return body[:index]


def _assert_materialized_return_source(sql: str) -> str:
    return_cte = _return_summary_sql(sql)

    assert "FROM reporting_agent_month st" in return_cte
    assert "sales_transactions" not in return_cte
    assert "JOIN stores s ON s.site_code = st.site_code" in return_cte
    # The materialized value already encodes the raw-row predicates.
    assert "st.quantity" not in return_cte
    assert "st.bon_nr" not in return_cte
    assert "is_cartela" not in return_cte
    return return_cte


def test_regional_return_summary_reads_materialized_month_model() -> None:
    sql = _regional_base_query(False, _RETURN_CLAUSE, ["agg.import_month = $1"])

    return_cte = _assert_materialized_return_source(sql)
    assert _RETURN_CLAUSE in return_cte
    assert "COALESCE(SUM(st.return_receipt_count), 0)::INT AS return_receipt_count" in return_cte
    assert "GROUP BY s.regional" in return_cte


def test_monthly_history_return_summary_reads_materialized_month_model() -> None:
    sql = _monthly_history_sql("", [], [], [])

    return_cte = _assert_materialized_return_source(sql)
    assert "COALESCE(SUM(st.return_receipt_count), 0)::INT AS return_receipt_count" in return_cte
    assert "GROUP BY st.import_month" in return_cte


def test_store_return_summary_reads_materialized_month_model() -> None:
    sql = _store_stats_query(False, _RETURN_CLAUSE, ["true"])

    return_cte = _assert_materialized_return_source(sql)
    assert _RETURN_CLAUSE in return_cte
    assert "COALESCE(SUM(st.return_receipt_count), 0)::INT AS return_receipt_count" in return_cte
    assert "GROUP BY st.import_month, st.site_code" in return_cte


def test_agent_return_summary_reads_materialized_month_model() -> None:
    sql = _agent_base_query(False, _RETURN_CLAUSE, ["true"])

    return_cte = _assert_materialized_return_source(sql)
    assert _RETURN_CLAUSE in return_cte
    assert "COALESCE(SUM(st.return_receipt_count), 0)::INT AS return_receipt_count" in return_cte
    assert "GROUP BY st.import_month, st.site_code, st.agent" in return_cte
