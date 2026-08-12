"""Candidate-only AI governance artifacts, monitoring and golden assertions."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from services.ai_forecast_governance import (
    ForecastGovernanceError,
    expand_governance_pairs,
)


SIX_PLACES = Decimal("0.000001")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def decimal_json(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value.quantize(SIX_PLACES), "f")
    if isinstance(value, dict):
        return {str(key): decimal_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [decimal_json(item) for item in value]
    return value


def build_model_card(
    evaluation: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    source_hash = _canonical_sha256(
        {"contract": fixture["contract"], "months": fixture["months"]}
    )
    cohort_hash = _canonical_sha256(
        [
            {
                "site_code": pair.site_code,
                "target_month": pair.target_month,
                "regional": pair.regional,
            }
            for pair in expand_governance_pairs(fixture)
        ]
    )
    return {
        "schema_version": 1,
        "methodology_version": "ai_governance_v1",
        "service_version": "timesfm_http_v1",
        "model_version": "candidate_fixture_v1",
        "feature_version": "historical_authority_v1",
        "cutoff_month": fixture["months"][-1],
        "source_sha256": source_hash,
        "cohort_sha256": cohort_hash,
        "exclusions": [],
        "metrics": {
            "candidate_point": evaluation["candidate_point"],
            "pinball_3_6_12": evaluation["candidate_pinball"],
            "fallback_ratio": evaluation["fallback_ratio"],
            "subgroups": "regional_gate_passed",
            "freshness_months": evaluation["source_freshness_months"],
        },
        "limitations": [
            "candidate-only evaluation",
            "live Planning promotion is outside this command contract",
        ],
        "owner": "UniHub Retail operations",
        "review_date": "2026-08-13",
        "candidate_decision": evaluation["decision"],
        "candidate_reasons": list(evaluation["reasons"]),
        "live_promotion_performed": False,
    }


def build_monitoring_report(
    evaluation: Mapping[str, Any],
    *,
    api_latency_seconds: Decimal = Decimal("0"),
    api_error_ratio: Decimal = Decimal("0"),
    cohort_change_ratio: Decimal = Decimal("0"),
) -> dict[str, Any]:
    if any(
        value < 0 or not value.is_finite()
        for value in (api_latency_seconds, api_error_ratio, cohort_change_ratio)
    ):
        raise ForecastGovernanceError("monitor inputs must be finite and nonnegative")
    candidate = evaluation["candidate_point"]
    missing_pairs = max(
        0,
        int(evaluation["expanded_pairs"] * (Decimal("1") - evaluation["pair_coverage"])),
    )
    alerts = {
        "absolute_bias_gt_10pct": abs(candidate["bias"]) > Decimal("0.10"),
        "fallback_gt_5pct": evaluation["fallback_ratio"] > Decimal("0.05"),
        "missing_pairs": missing_pairs > 0,
        "freshness_gt_one_month": evaluation["source_freshness_months"] > 1,
        "feature_psi_ge_0_20": any(
            value >= Decimal("0.20") for value in evaluation["feature_psi"].values()
        ),
        "api_error_ratio_ge_5pct": api_error_ratio >= Decimal("0.05"),
    }
    return {
        "schema_version": 1,
        "service_role": "ai_forecast_candidate_monitor",
        "candidate_decision": evaluation["decision"],
        "wape": candidate["wape"],
        "bias": candidate["bias"],
        "pinball_3_6_12": evaluation["candidate_pinball"],
        "fallback_ratio": evaluation["fallback_ratio"],
        "missing_pairs": missing_pairs,
        "source_freshness_months": evaluation["source_freshness_months"],
        "cohort_change_ratio": cohort_change_ratio,
        "feature_psi": evaluation["feature_psi"],
        "api_latency_seconds": api_latency_seconds,
        "api_error_ratio": api_error_ratio,
        "alerts": alerts,
        "alert_count": sum(alerts.values()),
        "live_promotion_performed": False,
    }


def monitoring_textfile(report: Mapping[str, Any]) -> str:
    alert_value = Decimal(int(report["alert_count"] > 0))
    metrics = {
        "unihub_ai_forecast_candidate_wape": report["wape"],
        "unihub_ai_forecast_candidate_bias": report["bias"],
        "unihub_ai_forecast_fallback_ratio": report["fallback_ratio"],
        "unihub_ai_forecast_missing_pairs": Decimal(report["missing_pairs"]),
        "unihub_ai_forecast_source_freshness_months": Decimal(report["source_freshness_months"]),
        "unihub_ai_forecast_api_latency_seconds": report["api_latency_seconds"],
        "unihub_ai_forecast_api_error_ratio": report["api_error_ratio"],
        "unihub_ai_forecast_alert_active": alert_value,
    }
    return "".join(f"{name} {value}\n" for name, value in metrics.items())


def write_governance_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decimal_json(dict(evidence)), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _golden_equal(actual: object, expected: object, *, field: str) -> None:
    if isinstance(expected, str):
        try:
            if Decimal(str(actual)) == Decimal(expected):
                return
        except Exception:
            pass
    if actual != expected:
        raise ForecastGovernanceError(
            f"golden mismatch for {field}: actual={actual!r} expected={expected!r}"
        )


def _assert_point_golden(
    actual: Mapping[str, Decimal],
    expected: Mapping[str, str],
    *,
    field: str,
) -> None:
    for name, expected_value in expected.items():
        _golden_equal(actual[name], expected_value, field=f"{field}.{name}")


def _assert_pinball_golden(
    evaluation: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    for window, expected_window in expected.items():
        _golden_equal(
            evaluation["pinball_actual_denominators"][window],
            expected_window["actual_denominator"],
            field=f"pinball.{window}.denominator",
        )
        for forecast_name, expected_forecast in expected_window.items():
            if forecast_name == "actual_denominator":
                continue
            actual_forecast = (
                evaluation["candidate_pinball"][window]
                if forecast_name == "candidate"
                else evaluation["baseline_pinball"][forecast_name][window]
            )
            for tau_name, expected_tau in expected_forecast.items():
                for metric_name, expected_value in expected_tau.items():
                    _golden_equal(
                        actual_forecast[tau_name][metric_name],
                        expected_value,
                        field=f"pinball.{window}.{forecast_name}.{tau_name}.{metric_name}",
                    )


def assert_evaluation_matches_fixture(
    evaluation: Mapping[str, Any],
    fixture: Mapping[str, Any],
) -> None:
    expected = fixture["expected"]
    for field in ("expanded_pairs", "pair_coverage", "fallback_ratio", "invalid_pairs"):
        _golden_equal(evaluation[field], expected[field], field=field)
    _assert_point_golden(
        evaluation["candidate_point"],
        expected["candidate_point"],
        field="candidate_point",
    )
    for baseline_name, expected_metrics in expected["baseline_point"].items():
        _assert_point_golden(
            evaluation["baseline_point"][baseline_name],
            expected_metrics,
            field=f"baseline_point.{baseline_name}",
        )
    _assert_pinball_golden(evaluation, expected["pinball_by_window"])
    _golden_equal(
        evaluation["candidate_quantile_coverage"],
        expected["pinball_gate"]["candidate_quantile_coverage"],
        field="candidate_quantile_coverage",
    )
    _golden_equal(evaluation["six_month_wins"], expected["six_month_wins"], field="six_month_wins")
    _golden_equal(
        evaluation["relative_wape_improvement"],
        expected["relative_wape_improvement"],
        field="relative_wape_improvement",
    )
    bootstrap = expected["bootstrap"]
    for field in ("seed", "replicates", "best_point_baseline", "ci95_lower", "ci95_upper"):
        _golden_equal(evaluation["bootstrap"][field], bootstrap[field], field=f"bootstrap.{field}")
    for field in ("minimum_delta", "maximum_delta"):
        _golden_equal(
            evaluation["bootstrap"][field],
            bootstrap["delta_every_replicate"],
            field=f"bootstrap.{field}",
        )
    _golden_equal(evaluation["decision"], expected["governance_decision"], field="decision")
