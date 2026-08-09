from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "config/performance-gates.json"
EXPORT_REQUEST = {
    "dataset": "stores",
    "months": ["2026-07"],
    "dimensions": ["site_code", "locatie", "firma", "regional", "asm"],
    "metrics": ["total_sales", "total_quantity", "total_receipts", "target"],
    "filters": {},
    "preview_limit": 10,
    "export_mode": "table",
    "include_closed_stores": False,
    "monthly_metrics": [],
    "daily_metrics": ["total_sales"],
    "comparison_levels": [],
    "selected_days": [1],
    "filename": "mixed-load-gate.xlsx",
}


@dataclass(frozen=True)
class GatePolicy:
    duration_seconds: float
    concurrency: int
    request_timeout_seconds: float
    minimum_requests: int
    maximum_error_rate: float
    maximum_p95_ms: float
    maximum_p99_ms: float


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[position]


def evaluate(summary: dict[str, Any], policy: GatePolicy) -> list[str]:
    failures: list[str] = []
    total = int(summary["requests"])
    error_rate = float(summary["error_rate"])
    if total < policy.minimum_requests:
        failures.append(f"requests {total} below minimum {policy.minimum_requests}")
    if error_rate > policy.maximum_error_rate:
        failures.append(
            f"error_rate {error_rate:.4f} above {policy.maximum_error_rate:.4f}"
        )
    if float(summary["latency_ms"]["p95"]) > policy.maximum_p95_ms:
        failures.append(
            f"p95 {summary['latency_ms']['p95']:.2f}ms above {policy.maximum_p95_ms:.2f}ms"
        )
    if float(summary["latency_ms"]["p99"]) > policy.maximum_p99_ms:
        failures.append(
            f"p99 {summary['latency_ms']['p99']:.2f}ms above {policy.maximum_p99_ms:.2f}ms"
        )
    if any(int(status) != 200 for status in summary.get("readiness_checks", [])):
        failures.append("application did not recover to three consecutive ready checks")
    export_states = summary.get("export_operation_states", [])
    if len(export_states) != 2 or any(state != "completed" for state in export_states):
        failures.append(
            f"export operations did not complete successfully: {export_states}"
        )
    return failures


def load_policy(path: Path, profile: str) -> GatePolicy:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise ValueError("unsupported performance gate policy version")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not isinstance(profiles.get(profile), dict):
        raise ValueError(f"unknown performance gate profile: {profile}")
    raw = profiles[profile]
    return GatePolicy(
        duration_seconds=float(raw["duration_seconds"]),
        concurrency=int(raw["concurrency"]),
        request_timeout_seconds=float(raw["request_timeout_seconds"]),
        minimum_requests=int(raw["minimum_requests"]),
        maximum_error_rate=float(raw["maximum_error_rate"]),
        maximum_p95_ms=float(raw["maximum_p95_ms"]),
        maximum_p99_ms=float(raw["maximum_p99_ms"]),
    )


async def fetch_token(client: httpx.AsyncClient, token_url: str) -> str:
    response = await client.get(token_url)
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("token endpoint did not return access_token")
    return token


def route_for(sequence: int) -> tuple[str, str, dict[str, Any] | None]:
    slot = sequence % 10
    if slot in {0, 1, 2, 3, 4, 5}:
        return "dashboard", "/api/dashboard/all?month=2026-07", None
    if slot in {6, 7}:
        return "months", "/api/filters/months", None
    if slot == 8:
        return "agents", "/api/agents/overview?selected_month=2026-07", None
    return "export-preview", "/api/exports/preview", EXPORT_REQUEST


async def run_gate(
    *,
    base_url: str,
    token_url: str,
    policy: GatePolicy,
) -> dict[str, Any]:
    timeout = httpx.Timeout(policy.request_timeout_seconds)
    limits = httpx.Limits(
        max_connections=max(policy.concurrency * 2, 16),
        max_keepalive_connections=max(policy.concurrency, 8),
    )
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"), timeout=timeout, limits=limits, follow_redirects=False
    ) as client:
        token = await fetch_token(client, token_url)
        headers = {"Authorization": f"Bearer {token}"}
        warmup = await client.get("/readyz")
        warmup.raise_for_status()
        export_operations: list[dict[str, Any]] = []
        for index in range(2):
            request = {**EXPORT_REQUEST, "filename": f"mixed-load-gate-{index + 1}.xlsx"}
            response = await client.post(
                "/api/exports/operations", headers=headers, json=request
            )
            if response.status_code not in {200, 201, 409}:
                response.raise_for_status()
            if response.status_code in {200, 201}:
                export_operations.append(response.json())

        latencies: list[float] = []
        route_latencies: dict[str, list[float]] = defaultdict(list)
        statuses: Counter[str] = Counter()
        errors: list[str] = []
        sequence = 0
        sequence_lock = asyncio.Lock()
        deadline = time.monotonic() + policy.duration_seconds

        async def worker() -> None:
            nonlocal sequence
            while time.monotonic() < deadline:
                async with sequence_lock:
                    current = sequence
                    sequence += 1
                route, path, payload = route_for(current)
                started = time.perf_counter()
                try:
                    if payload is None:
                        response = await client.get(path, headers=headers)
                    else:
                        response = await client.post(path, headers=headers, json=payload)
                    elapsed = (time.perf_counter() - started) * 1000
                    latencies.append(elapsed)
                    route_latencies[route].append(elapsed)
                    statuses[str(response.status_code)] += 1
                    if not 200 <= response.status_code < 300:
                        errors.append(f"{route}:{response.status_code}")
                except (httpx.HTTPError, asyncio.TimeoutError) as exc:
                    elapsed = (time.perf_counter() - started) * 1000
                    latencies.append(elapsed)
                    route_latencies[route].append(elapsed)
                    statuses["transport_error"] += 1
                    errors.append(f"{route}:{type(exc).__name__}")

        await asyncio.gather(*(worker() for _ in range(policy.concurrency)))
        readiness_checks: list[int] = []
        for _ in range(3):
            ready = await client.get("/readyz")
            readiness_checks.append(ready.status_code)
            await asyncio.sleep(0.2)
        export_operation_states: list[str] = []
        async def poll_export(operation: dict[str, Any]) -> str:
            operation_id = operation.get("id")
            if operation_id is None:
                return "missing_id"
            operation_deadline = time.monotonic() + 30
            state = "poll_timeout"
            while time.monotonic() < operation_deadline:
                status_response = await client.get(
                    f"/api/exports/operations/{operation_id}", headers=headers
                )
                if status_response.status_code != 200:
                    state = f"http_{status_response.status_code}"
                    break
                state = str(status_response.json().get("status"))
                if state in {"completed", "failed", "cancelled", "expired"}:
                    break
                await asyncio.sleep(0.2)
            return state

        for operation in export_operations:
            export_operation_states.append(await poll_export(operation))
        # The API intentionally permits only one active export per requester.
        # A second pre-load reservation can therefore return 409. Submit its
        # replacement after the first terminal result so two real jobs are
        # still consumed and verified by the isolated export worker.
        while len(export_operation_states) < 2:
            request = {
                **EXPORT_REQUEST,
                "filename": f"mixed-load-gate-followup-{len(export_operation_states) + 1}.xlsx",
            }
            response = await client.post(
                "/api/exports/operations", headers=headers, json=request
            )
            if response.status_code not in {200, 201}:
                export_operation_states.append(f"submit_http_{response.status_code}")
                break
            export_operation_states.append(await poll_export(response.json()))

    request_count = len(latencies)
    route_summary = {
        route: {
            "requests": len(values),
            "p50": round(percentile(values, 0.50), 2),
            "p95": round(percentile(values, 0.95), 2),
            "p99": round(percentile(values, 0.99), 2),
        }
        for route, values in sorted(route_latencies.items())
    }
    return {
        "requests": request_count,
        "errors": len(errors),
        "error_rate": (len(errors) / request_count) if request_count else 1.0,
        "status_counts": dict(sorted(statuses.items())),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 2),
            "p95": round(percentile(latencies, 0.95), 2),
            "p99": round(percentile(latencies, 0.99), 2),
            "max": round(max(latencies, default=0.0), 2),
        },
        "routes": route_summary,
        "sample_errors": errors[:20],
        "readiness_checks": readiness_checks,
        "export_operation_states": export_operation_states,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("REAL_E2E_BASE_URL"))
    parser.add_argument(
        "--token-url",
        default=(
            f"{os.getenv('REAL_E2E_OIDC_ORIGIN', '').rstrip('/')}/test-token/admin"
            if os.getenv("REAL_E2E_OIDC_ORIGIN")
            else None
        ),
    )
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--profile", default="ci_mixed_load")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    if not args.base_url or not args.token_url:
        raise SystemExit("--base-url and --token-url are required")
    policy = load_policy(args.policy, args.profile)
    summary = await run_gate(
        base_url=args.base_url,
        token_url=args.token_url,
        policy=policy,
    )
    failures = evaluate(summary, policy)
    report = {
        "profile": args.profile,
        "policy": policy.__dict__,
        "summary": summary,
        "failures": failures,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(rendered, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 1 if failures else 0


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
