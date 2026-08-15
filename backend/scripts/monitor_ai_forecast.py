#!/usr/bin/env python3
"""Emit privacy-safe candidate forecast monitoring JSON and Prometheus text."""
from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.ai_forecast_governance import (  # noqa: E402
    evaluate_governance_fixture,
    load_governance_fixture,
)
from services.ai_forecast_governance_evidence import (  # noqa: E402
    build_monitoring_report,
    monitoring_textfile,
    write_governance_evidence,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--governance-fixture", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--textfile", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--api-latency-seconds", type=Decimal, default=Decimal("0"))
    parser.add_argument("--api-error-ratio", type=Decimal, default=Decimal("0"))
    parser.add_argument("--cohort-change-ratio", type=Decimal, default=Decimal("0"))
    args = parser.parse_args()

    fixture = load_governance_fixture(args.governance_fixture)
    evaluation = evaluate_governance_fixture(fixture, seed=args.seed)
    report = build_monitoring_report(
        evaluation,
        api_latency_seconds=args.api_latency_seconds,
        api_error_ratio=args.api_error_ratio,
        cohort_change_ratio=args.cohort_change_ratio,
    )
    write_governance_evidence(args.json, report)
    args.textfile.parent.mkdir(parents=True, exist_ok=True)
    args.textfile.write_text(monitoring_textfile(report), encoding="utf-8")
    print(f"candidate_decision={report['candidate_decision']} alerts={report['alert_count']}")


if __name__ == "__main__":
    main()
