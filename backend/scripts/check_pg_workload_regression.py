#!/usr/bin/env python3
"""Compare pg_stat_statements snapshots using stable fingerprints and policy budgets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

DEFAULT_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "defaults": {
        "owner": "retail-platform",
        "min_baseline_calls": 5,
        "metric_limits": {
            "mean_exec_time_ms": {"max_regression_ratio": 0.10, "max_zero_baseline_delta": 0.0},
            "estimated_p95_exec_time_ms": {"max_regression_ratio": 0.10, "max_zero_baseline_delta": 0.0},
            "temp_blocks_written": {"max_regression_ratio": 0.10, "max_zero_baseline_delta": 0.0},
        },
    },
    "statements": {},
}


def load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 2 or not isinstance(payload.get("statements"), list):
        raise ValueError(f"unsupported workload snapshot: {path}")
    return payload


def load_policy(path: Path | None) -> dict[str, Any]:
    payload = DEFAULT_POLICY if path is None else json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported workload policy schema")
    defaults = payload.get("defaults")
    statements = payload.get("statements")
    if not isinstance(defaults, dict) or not isinstance(statements, dict):
        raise ValueError("workload policy must define defaults and statements objects")
    metric_limits = defaults.get("metric_limits")
    if not isinstance(metric_limits, dict) or not metric_limits:
        raise ValueError("workload policy defaults.metric_limits must be non-empty")
    return payload


def statement_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in payload["statements"]:
        fingerprint = item.get("fingerprint_sha256")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise ValueError("snapshot contains an invalid statement fingerprint")
        if fingerprint in result:
            raise ValueError("snapshot contains duplicate statement fingerprints")
        result[fingerprint] = item
    return result


def _statement_policy(policy: dict[str, Any], fingerprint: str) -> dict[str, Any]:
    defaults = policy["defaults"]
    override = policy["statements"].get(fingerprint, {})
    if not isinstance(override, dict):
        raise ValueError(f"invalid policy override for {fingerprint}")
    metric_limits = dict(defaults["metric_limits"])
    override_limits = override.get("metric_limits", {})
    if not isinstance(override_limits, dict):
        raise ValueError(f"invalid metric_limits override for {fingerprint}")
    metric_limits.update(override_limits)
    return {
        "owner": str(override.get("owner", defaults.get("owner", "unassigned"))),
        "min_baseline_calls": int(
            override.get("min_baseline_calls", defaults.get("min_baseline_calls", 5))
        ),
        "metric_limits": metric_limits,
    }


def _validate_metric_rule(metric: str, rule: Any) -> tuple[float, float]:
    if not isinstance(rule, dict):
        raise ValueError(f"invalid metric rule for {metric}")
    max_ratio = float(rule.get("max_regression_ratio", 0.10))
    max_zero_delta = float(rule.get("max_zero_baseline_delta", 0.0))
    if not 0 <= max_ratio <= 10 or max_zero_delta < 0:
        raise ValueError(f"invalid metric thresholds for {metric}")
    return max_ratio, max_zero_delta


def _metric_value(statement: dict[str, Any], metric: str) -> float:
    value = float(statement.get(metric, 0) or 0)
    if metric == "temp_blocks_written":
        calls = int(statement.get("calls", 0) or 0)
        return value / calls if calls > 0 else 0.0
    return value


def compare_snapshots(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    max_regression_ratio: float | None = None,
    min_baseline_calls: int | None = None,
) -> dict[str, Any]:
    effective_policy = load_policy(None) if policy is None else load_policy_payload(policy)
    baseline_index = statement_index(baseline)
    candidate_index = statement_index(candidate)
    regressions: list[dict[str, Any]] = []
    compared = 0
    skipped_low_calls = 0
    missing_candidate = 0
    for fingerprint, old in baseline_index.items():
        statement_policy = _statement_policy(effective_policy, fingerprint)
        min_calls = (
            min_baseline_calls
            if min_baseline_calls is not None
            else statement_policy["min_baseline_calls"]
        )
        if min_calls < 1:
            raise ValueError("min_baseline_calls must be at least 1")
        if int(old.get("calls", 0)) < min_calls:
            skipped_low_calls += 1
            continue
        new = candidate_index.get(fingerprint)
        if new is None:
            missing_candidate += 1
            continue
        compared += 1
        for metric, rule in statement_policy["metric_limits"].items():
            configured_ratio, max_zero_delta = _validate_metric_rule(metric, rule)
            ratio_limit = max_regression_ratio if max_regression_ratio is not None else configured_ratio
            if not 0 <= ratio_limit <= 10:
                raise ValueError("max_regression_ratio must be between 0 and 10")
            old_value = _metric_value(old, metric)
            new_value = _metric_value(new, metric)
            absolute_delta = new_value - old_value
            ratio = absolute_delta / old_value if old_value > 0 else None
            breached = ratio is not None and ratio > ratio_limit
            if old_value <= 0:
                breached = absolute_delta > max_zero_delta
            if breached:
                regressions.append(
                    {
                        "fingerprint_sha256": fingerprint,
                        "owner": statement_policy["owner"],
                        "metric": metric,
                        "normalization": (
                            "per_call" if metric == "temp_blocks_written" else "native"
                        ),
                        "baseline": round(old_value, 6),
                        "candidate": round(new_value, 6),
                        "absolute_delta": round(absolute_delta, 6),
                        "regression_ratio": round(ratio, 6) if ratio is not None else None,
                        "limit_ratio": ratio_limit,
                        "zero_baseline_delta_limit": max_zero_delta,
                        "query": new.get("query") or old.get("query"),
                    }
                )
    regressions.sort(
        key=lambda item: (
            -(item["regression_ratio"] if item["regression_ratio"] is not None else float("inf")),
            item["fingerprint_sha256"],
            item["metric"],
        )
    )
    return {
        "schema_version": 2,
        "baseline_runtime_sha": baseline.get("runtime_sha"),
        "candidate_runtime_sha": candidate.get("runtime_sha"),
        "compared_statements": compared,
        "skipped_low_call_statements": skipped_low_calls,
        "missing_candidate_statements": missing_candidate,
        "regressions": regressions,
        "passed": not regressions,
    }


def load_policy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported workload policy schema")
    defaults = payload.get("defaults")
    statements = payload.get("statements")
    if not isinstance(defaults, dict) or not isinstance(statements, dict):
        raise ValueError("workload policy must define defaults and statements objects")
    metric_limits = defaults.get("metric_limits")
    if not isinstance(metric_limits, dict) or not metric_limits:
        raise ValueError("workload policy defaults.metric_limits must be non-empty")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--max-regression-percent", type=float)
    parser.add_argument("--min-baseline-calls", type=int)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = compare_snapshots(
        load_snapshot(args.baseline),
        load_snapshot(args.candidate),
        policy=load_policy(args.policy),
        max_regression_ratio=(
            args.max_regression_percent / 100 if args.max_regression_percent is not None else None
        ),
        min_baseline_calls=args.min_baseline_calls,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
