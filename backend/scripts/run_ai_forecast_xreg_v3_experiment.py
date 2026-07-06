from __future__ import annotations

import argparse

from run_ai_forecast_xreg import DEFAULT_API_URL
from run_ai_forecast_xreg_v2_experiment import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Ruleaza comparatia xreg_timesfm v1 vs v3 fara monitorizare interactiva.")
    parser.add_argument("--repo-root", default="/opt/Mobiup/unihub-retail")
    parser.add_argument("--backtest-start-month", default="2025-07")
    parser.add_argument("--backtest-end-month", default="2026-06")
    parser.add_argument("--forecast-start-month", default="2026-07")
    parser.add_argument("--forecast-end-month", default="2026-07")
    parser.add_argument("--source-month", default=None)
    parser.add_argument("--history-start-month", default="2018-01")
    parser.add_argument("--metrics", default="sales_value,units")
    parser.add_argument("--profiles", default="v1,v3")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--health-timeout", type=int, default=30)
    parser.add_argument("--output-dir", default="backend/outputs/ai_forecast/xreg_v3_experiment")
    parser.add_argument(
        "--exclude-site-code",
        action="append",
        default=["CRFVUL", "CRFARENA"],
        help="Exclude magazine inchise sau non-comparabile.",
    )
    args = parser.parse_args()
    raise SystemExit(run_experiment(args))


if __name__ == "__main__":
    main()
