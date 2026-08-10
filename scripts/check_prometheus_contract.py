#!/usr/bin/env python3
"""Fail CI when Retail rules reference scrape jobs that do not exist."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SCRAPES = (
    ROOT / "ops/observability/retail-process-scrape.yml",
    ROOT / "ops/observability/retail-readiness-scrape.yml",
)
RULES = ROOT / "ops/observability/retail-slo-rules.yml"
JOB_NAME = re.compile(r"(?m)^\s*-?\s*job_name:\s*[\"']?([^\"'\s]+)")
EXACT_JOB_SELECTOR = re.compile(r"\bjob\s*=\s*[\"']([^\"']+)[\"']")
RECORD_NAME = re.compile(r"(?m)^\s*-\s*record:\s*(\S+)\s*$")
CRITICAL_RECORDINGS = {
    "unihub_retail:http_requests_excluding_probes:rate5m",
    "unihub_retail:http_5xx_ratio:rate5m",
    "unihub_retail:http_latency_p95_seconds:rate5m",
    "unihub_retail:dashboard_latency_p95_seconds:rate5m",
}


def main() -> None:
    scrape_jobs: set[str] = set()
    for path in SCRAPES:
        scrape_jobs.update(JOB_NAME.findall(path.read_text(encoding="utf-8")))
    rules_text = RULES.read_text(encoding="utf-8")
    selected_jobs = set(EXACT_JOB_SELECTOR.findall(rules_text))
    unknown = selected_jobs - scrape_jobs
    if unknown:
        raise SystemExit("Prometheus rules reference unknown jobs: " + ", ".join(sorted(unknown)))
    missing = CRITICAL_RECORDINGS - set(RECORD_NAME.findall(rules_text))
    if missing:
        raise SystemExit("Critical recording rules are missing: " + ", ".join(sorted(missing)))
    if "unihub-retail-web" not in selected_jobs:
        raise SystemExit("HTTP/SLO rules do not select the live Retail web job")
    print(f"Prometheus contract valid: {len(scrape_jobs)} scrape jobs, {len(selected_jobs)} exact selectors")


if __name__ == "__main__":
    main()
