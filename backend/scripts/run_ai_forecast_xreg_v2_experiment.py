from __future__ import annotations

import argparse
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from run_ai_forecast_xreg import DEFAULT_API_URL, add_month


DEFAULT_OUTPUT_DIR = Path("backend/outputs/ai_forecast/xreg_v2_experiment")


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def health_url(api_url: str) -> str:
    if api_url.endswith("/forecast_xreg"):
        return api_url[: -len("/forecast_xreg")] + "/health"
    return api_url.rstrip("/") + "/health"


def check_health(api_url: str, api_key: str, timeout: int) -> str:
    request = urllib.request.Request(
        health_url(api_url),
        headers={"X-API-Key": api_key},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def run_command(command: list[str], *, cwd: Path, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n$ " + " ".join(command) + "\n")
        log.flush()
        process = subprocess.run(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(f"Comanda a esuat cu exit code {process.returncode}: {' '.join(command)}")


def base_command(args: argparse.Namespace, *, metric: str, profile: str, output_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "backend/scripts/run_ai_forecast_xreg.py",
        "--metric",
        metric,
        "--feature-profile",
        profile,
        "--history-start-month",
        args.history_start_month,
        "--api-url",
        args.api_url,
        "--timeout",
        str(args.timeout),
        "--output-dir",
        str(output_dir),
    ]
    if args.api_key:
        command.extend(["--api-key", args.api_key])
    for site_code in args.exclude_site_code:
        command.extend(["--exclude-site-code", site_code])
    return command


def run_experiment(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = output_dir / f"xreg_v2_experiment_{run_id}.log"
    metrics = split_csv(args.metrics)
    profiles = split_csv(args.profiles)
    api_key = args.api_key or os.environ.get("TIMESFM_API_KEY", "")
    if not api_key:
        raise RuntimeError("TIMESFM_API_KEY lipseste. Seteaza env var sau foloseste --api-key.")

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"run_id={run_id}\n")
        log.write(f"backtest={args.backtest_start_month}..{args.backtest_end_month}\n")
        log.write(f"forecast={args.forecast_start_month}..{args.forecast_end_month}\n")
        log.write(f"metrics={metrics}\nprofiles={profiles}\n")
        log.write("health=" + check_health(args.api_url, api_key, args.health_timeout) + "\n")

    for metric in metrics:
        for profile in profiles:
            command = base_command(args, metric=metric, profile=profile, output_dir=output_dir)
            command.extend(
                [
                    "--start-month",
                    args.backtest_start_month,
                    "--end-month",
                    args.backtest_end_month,
                ]
            )
            run_command(command, cwd=repo_root, log_path=log_path)

    for metric in metrics:
        for profile in profiles:
            command = base_command(args, metric=metric, profile=profile, output_dir=output_dir)
            command.extend(
                [
                    "--operational",
                    "--start-month",
                    args.forecast_start_month,
                    "--end-month",
                    args.forecast_end_month,
                    "--source-month",
                    args.source_month or add_month(args.forecast_start_month, -1),
                ]
            )
            run_command(command, cwd=repo_root, log_path=log_path)

    print(f"Experiment terminat. Log: {log_path}")
    print(f"Output: {output_dir}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ruleaza comparatia xreg_timesfm v1 vs v2 fara monitorizare interactiva.")
    parser.add_argument("--repo-root", default="/opt/Mobiup/unihub-retail")
    parser.add_argument("--backtest-start-month", default="2025-07")
    parser.add_argument("--backtest-end-month", default="2026-06")
    parser.add_argument("--forecast-start-month", default="2026-07")
    parser.add_argument("--forecast-end-month", default="2026-07")
    parser.add_argument("--source-month", default=None)
    parser.add_argument("--history-start-month", default="2018-01")
    parser.add_argument("--metrics", default="sales_value,units")
    parser.add_argument("--profiles", default="v1,v2")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--health-timeout", type=int, default=30)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
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
