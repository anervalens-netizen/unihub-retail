from __future__ import annotations

import sys
from typing import Any

import pytest

from scripts.check_pg_workload_regression import (
    DEFAULT_POLICY,
    compare_snapshots,
    load_policy,
    parse_args,
)
from scripts.report_pg_stat_statements import normalize_query, statement_payload


def test_workload_checker_uses_builtin_policy_when_cli_policy_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["check", "baseline.json", "candidate.json"])

    args = parse_args()

    assert args.policy is None
    assert load_policy(args.policy) == DEFAULT_POLICY


def test_workload_checker_normalizes_temporary_writes_per_call() -> None:
    fingerprint = "a" * 64
    baseline: dict[str, Any] = {
        "schema_version": 2,
        "runtime_sha": "baseline",
        "statements": [
            {
                "fingerprint_sha256": fingerprint,
                "calls": 5,
                "mean_exec_time_ms": 1,
                "estimated_p95_exec_time_ms": 1,
                "temp_blocks_written": 10,
            }
        ],
    }
    candidate: dict[str, Any] = {
        "schema_version": 2,
        "runtime_sha": "candidate",
        "statements": [
            {
                "fingerprint_sha256": fingerprint,
                "calls": 10,
                "mean_exec_time_ms": 1,
                "estimated_p95_exec_time_ms": 1,
                "temp_blocks_written": 20,
            }
        ],
    }

    assert compare_snapshots(baseline, candidate)["passed"] is True

    candidate["statements"][0]["temp_blocks_written"] = 30
    regression = compare_snapshots(baseline, candidate)
    temp_regression = next(
        item for item in regression["regressions"] if item["metric"] == "temp_blocks_written"
    )
    assert temp_regression["baseline"] == 2.0
    assert temp_regression["candidate"] == 3.0
    assert temp_regression["normalization"] == "per_call"


def test_workload_checker_requires_review_for_frequent_candidate_only_statement() -> None:
    candidate_only = {
        "fingerprint_sha256": "b" * 64,
        "calls": 5,
        "mean_exec_time_ms": 1000,
        "estimated_p95_exec_time_ms": 2000,
        "temp_blocks_written": 500,
        "query": "SELECT expensive_new_query()",
    }
    baseline: dict[str, Any] = {
        "schema_version": 2,
        "runtime_sha": "baseline",
        "statements": [],
    }
    candidate: dict[str, Any] = {
        "schema_version": 2,
        "runtime_sha": "candidate",
        "statements": [candidate_only],
    }

    result = compare_snapshots(baseline, candidate)

    assert result["passed"] is False
    assert result["candidate_only_reviewed_statements"] == 1
    assert result["regressions"] == [
        {
            "fingerprint_sha256": "b" * 64,
            "owner": "retail-platform",
            "metric": "candidate_only_statement",
            "normalization": "review_required",
            "baseline": None,
            "candidate": 5,
            "absolute_delta": None,
            "regression_ratio": None,
            "limit_ratio": None,
            "zero_baseline_delta_limit": None,
            "query": "SELECT expensive_new_query()",
        }
    ]


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
        "fingerprint_sha256": "9d6cfde9b64b8ac169b1e0602ff4aaad61c898bc109a5d4ee0480903db48cda8",  # pragma: allowlist secret
        "calls": 7,
        "total_exec_time_ms": 123.457,
        "mean_exec_time_ms": 17.637,
        "min_exec_time_ms": 17.637,
        "max_exec_time_ms": 17.637,
        "stddev_exec_time_ms": 0.0,
        "estimated_p95_exec_time_ms": 17.637,
        "estimated_p95_method": "min(observed_max, mean+1.644854*stddev)",
        "rows": 99,
        "mean_rows_per_call": 14.143,
        "shared_blocks_hit": 101,
        "shared_blocks_read": 5,
        "shared_read_ratio": 0.04717,
        "temp_blocks_read": 2,
        "temp_blocks_written": 3,
        "wal_bytes": 0,
        "query": "SELECT * FROM reporting_item_month",
    }
