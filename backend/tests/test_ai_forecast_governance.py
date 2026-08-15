"""Independent governance metrics, drift and candidate-only safety contract."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from services.ai_forecast_governance import (
    ForecastGovernanceError,
    evaluate_governance_fixture,
    expand_governance_pairs,
    load_governance_fixture,
    maximum_categorical_share_movement,
    paired_cluster_bootstrap,
    population_stability_index,
)
from services.ai_forecast_governance_evidence import (
    assert_evaluation_matches_fixture,
    build_model_card,
    build_monitoring_report,
    monitoring_textfile,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "docs/contracts/ai-governance-golden-v1.json"


@pytest.fixture(scope="module")
def fixture() -> dict[str, object]:
    return load_governance_fixture(FIXTURE_PATH)


def _rehash(payload: dict[str, object]) -> None:
    hashed = {key: value for key, value in payload.items() if key != "contract_payload_sha256"}
    payload["contract_payload_sha256"] = hashlib.sha256(
        json.dumps(
            hashed,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def test_locked_fixture_expands_24_pairs_and_matches_every_expected_value(
    fixture: dict[str, object],
) -> None:
    evaluation = evaluate_governance_fixture(fixture, seed=20260812)
    assert_evaluation_matches_fixture(evaluation, fixture)
    assert len(expand_governance_pairs(fixture)) == 24
    assert evaluation["decision"] == "eligible_candidate_only_no_live_promotion"
    assert evaluation["candidate_only"] is True
    assert evaluation["live_promotion_performed"] is False


def test_bootstrap_is_exact_seeded_cluster_resampling(fixture: dict[str, object]) -> None:
    evidence = paired_cluster_bootstrap(
        expand_governance_pairs(fixture),
        baseline_name="moving_average_high",
        seed=20260812,
    )
    assert evidence == {
        "seed": 20260812,
        "replicates": 10_000,
        "best_point_baseline": "moving_average_high",
        "ci95_lower": Decimal("-0.05"),
        "ci95_upper": Decimal("-0.05"),
        "minimum_delta": Decimal("-0.05"),
        "maximum_delta": Decimal("-0.05"),
    }


def test_fixture_tampering_or_wrong_quantile_layout_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["stores"][0]["actual"] = "101.00"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ForecastGovernanceError, match="payload hash differs"):
        load_governance_fixture(path)

    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["stores"][0]["candidate_quantile_layout"] = ["1"] * 8
    _rehash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    malformed = load_governance_fixture(path)
    with pytest.raises(ForecastGovernanceError, match="exactly 9 or 10"):
        expand_governance_pairs(malformed)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"response_profile": "point_only_v1"}, "quantiles_required"),
        ({"authority_ready": False}, "authority_incomplete"),
        ({"source_freshness_months": 2}, "source_stale"),
        (
            {"feature_psi": {"log1p_monthly_value": Decimal("0.20")}},
            "feature_drift",
        ),
        ({"categorical_share_movement": Decimal("0.21")}, "categorical_drift"),
    ],
)
def test_governance_blocks_each_finite_safety_gate(
    fixture: dict[str, object],
    kwargs: dict[str, object],
    reason: str,
) -> None:
    evaluation = evaluate_governance_fixture(fixture, seed=20260812, **kwargs)  # type: ignore[arg-type]
    assert evaluation["decision"] == "BLOCKED"
    assert reason in evaluation["reasons"]
    assert evaluation["live_promotion_performed"] is False


def test_zero_denominator_is_blocked_not_divided(fixture: dict[str, object]) -> None:
    payload = deepcopy(fixture)
    for store in cast(list[dict[str, Any]], payload["stores"]):
        store["actual"] = "0.00"
        store["candidate_point"] = "0.00"
        store["candidate_quantile_layout"] = ["0.00"] * len(store["candidate_quantile_layout"])
        store["baseline_points"] = {
            name: "0.00" for name in store["baseline_points"]
        }
    _rehash(payload)
    evaluation = evaluate_governance_fixture(payload, seed=20260812)
    assert evaluation["decision"] == "BLOCKED"
    assert evaluation["reasons"] == ["zero_actual_denominator"]
    assert evaluation["candidate_point"]["wape"] is None


def test_drift_uses_fixed_deciles_minimum_sample_and_share_threshold() -> None:
    reference = [Decimal(index) for index in range(100)]
    assert population_stability_index(reference, reference) == 0
    shifted = [Decimal(index + 200) for index in range(100)]
    assert population_stability_index(reference, shifted) >= Decimal("0.20")
    with pytest.raises(ForecastGovernanceError, match="at least 100"):
        population_stability_index(reference[:99], reference[:99])
    assert maximum_categorical_share_movement(
        ["A"] * 50 + ["B"] * 50,
        ["A"] * 30 + ["B"] * 70,
    ) == Decimal("0.20")


def test_model_card_and_monitor_are_sanitized_candidate_only(
    fixture: dict[str, object],
) -> None:
    evaluation = evaluate_governance_fixture(fixture, seed=20260812)
    card = build_model_card(evaluation, fixture)
    report = build_monitoring_report(evaluation)
    required = {
        "schema_version",
        "methodology_version",
        "service_version",
        "model_version",
        "feature_version",
        "cutoff_month",
        "source_sha256",
        "cohort_sha256",
        "exclusions",
        "metrics",
        "limitations",
        "owner",
        "review_date",
        "candidate_decision",
        "candidate_reasons",
    }
    assert required <= set(card)
    assert card["live_promotion_performed"] is False
    assert report["alert_count"] == 0
    textfile = monitoring_textfile(report)
    assert "site_code" not in textfile
    assert "firma" not in textfile
    assert "unihub_ai_forecast_candidate_wape 0" in textfile


def test_monitor_alert_thresholds_are_finite_and_inclusive(
    fixture: dict[str, object],
) -> None:
    evaluation = evaluate_governance_fixture(fixture, seed=20260812)
    report = build_monitoring_report(
        evaluation,
        api_error_ratio=Decimal("0.05"),
    )
    assert report["alerts"]["api_error_ratio_ge_5pct"] is True
    assert report["alert_count"] == 1
