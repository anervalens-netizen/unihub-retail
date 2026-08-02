from __future__ import annotations

from scripts.report_pg_stat_statements import normalize_query, statement_payload


def test_normalize_query_compacts_and_bounds_statement_text() -> None:
    assert normalize_query(" SELECT\n  *   FROM reporting_item_day ") == (
        "SELECT * FROM reporting_item_day"
    )
    assert normalize_query("x" * 600, max_length=20) == ("x" * 17) + "..."


def test_statement_payload_preserves_operational_counters() -> None:
    result = statement_payload(
        {
            "query_id": 42,
            "calls": 7,
            "total_exec_time_ms": 123.45678,
            "mean_exec_time_ms": 17.63668,
            "rows": 99,
            "shared_blocks_hit": 101,
            "shared_blocks_read": 5,
            "temp_blocks_read": 2,
            "temp_blocks_written": 3,
            "query": "SELECT  *\nFROM reporting_item_month",
        }
    )

    assert result == {
        "query_id": "42",
        "calls": 7,
        "total_exec_time_ms": 123.457,
        "mean_exec_time_ms": 17.637,
        "rows": 99,
        "shared_blocks_hit": 101,
        "shared_blocks_read": 5,
        "temp_blocks_read": 2,
        "temp_blocks_written": 3,
        "query": "SELECT * FROM reporting_item_month",
    }
