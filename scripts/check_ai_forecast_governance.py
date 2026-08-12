#!/usr/bin/env python3
"""Prove the locked AI governance golden and candidate-only boundary."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.ai_forecast_governance import (  # noqa: E402
    ForecastGovernanceError,
    evaluate_governance_fixture,
    load_governance_fixture,
    load_locked_json_contract,
    maximum_categorical_share_movement,
    population_stability_index,
)
from services.ai_forecast_governance_evidence import (  # noqa: E402
    assert_evaluation_matches_fixture,
    build_model_card,
    build_monitoring_report,
    monitoring_textfile,
    write_governance_evidence,
)


def deterministic_drift_proof() -> tuple[dict[str, Decimal], Decimal]:
    monthly = [Decimal(str(math.log1p(index))) for index in range(1, 101)]
    contexts = [Decimal(index) for index in range(12, 112)]
    ages = [Decimal(index) for index in range(1, 101)]
    psi = {
        "log1p_monthly_value": population_stability_index(monthly, monthly),
        "context_months": population_stability_index(contexts, contexts),
        "months_since_opening": population_stability_index(ages, ages),
    }
    categories = ["F1"] * 50 + ["F2"] * 50
    return psi, maximum_categorical_share_movement(categories, categories)


def run_check(args: argparse.Namespace) -> dict[str, Any]:
    load_locked_json_contract(
        args.contract,
        contract="business-golden-v2",
        version=2,
    )
    fixture = load_governance_fixture(args.governance_fixture)
    psi, categorical_movement = deterministic_drift_proof()
    evaluation = evaluate_governance_fixture(
        fixture,
        seed=args.seed,
        feature_psi=psi,
        categorical_share_movement=categorical_movement,
    )
    assert_evaluation_matches_fixture(evaluation, fixture)
    model_card = build_model_card(evaluation, fixture)
    monitoring = build_monitoring_report(evaluation)
    if monitoring["alert_count"] != 0 or model_card["live_promotion_performed"] is not False:
        raise ForecastGovernanceError("candidate evidence is not safe for publication")

    evidence = {
        **evaluation,
        "result": "PASS",
        "model_card_path": str(args.evidence.with_suffix(".model-card.json").name),
        "monitoring_path": str(args.evidence.with_suffix(".monitoring.json").name),
        "textfile_path": str(args.evidence.with_suffix(".prom").name),
    }
    write_governance_evidence(args.evidence, evidence)
    write_governance_evidence(args.evidence.with_suffix(".model-card.json"), model_card)
    write_governance_evidence(args.evidence.with_suffix(".monitoring.json"), monitoring)
    args.evidence.with_suffix(".prom").write_text(monitoring_textfile(monitoring), encoding="utf-8")
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--governance-fixture", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = run_check(args)
    print(
        json.dumps(
            {
                "result": evidence["result"],
                "decision": evidence["decision"],
                "expanded_pairs": evidence["expanded_pairs"],
                "live_promotion_performed": evidence["live_promotion_performed"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
