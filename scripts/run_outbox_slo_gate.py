#!/usr/bin/env python3
"""Own an isolated PostgreSQL/Valkey lifecycle for the AC-12 SLO authority."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any


for _startup_variable in (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONINSPECT",
    "MYPYPATH",
    "MYPY_CONFIG_FILE",
    "BASH_ENV",
    "ENV",
    "CDPATH",
    "GLOBIGNORE",
):
    os.environ.pop(_startup_variable, None)
os.environ.update(
    {
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
)


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "backend/scripts/run_outbox_slo_workload.py"
ENGINE = ROOT / "backend/scripts/outbox_slo_workload_engine.py"
BOOTSTRAP = ROOT / "backend/scripts/bootstrap_test_db.py"
PYTHON = ROOT / "backend/venv/bin/python"
PYTHON_BASE = Path("/usr/bin/python3.12")
PYTHON_BASE_SHA256 = "1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
MIGRATION = ROOT / "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql"
MIGRATION_MANIFEST = ROOT / "backend/db/migrations/manifest.json"
POSTGRES_IMAGE = "postgres@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"
VALKEY_IMAGE = "valkey/valkey@sha256:b027235326507cfdade9b6684056ec1d0b0c0757412e628245129b5d7b788618"
EXPECTED = {
    "seed": 20260812,
    "warmup": 500,
    "events": 10_000,
    "rate": 20,
    "claimers": 4,
    "batch_size": 50,
    "handlers": 8,
}
EXPECTED_EVENT_TYPES = (
    "retail.sales_generation_promoted.v1",
    "retail.pnl_generation_promoted.v1",
    "retail.salary_import_completed.v1",
    "retail.planning_forecast_promoted.v1",
    "retail.grile_manifest_approved.v1",
)


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, **kwargs)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_python_identity() -> None:
    if (
        not PYTHON.is_file()
        or not os.access(PYTHON, os.X_OK)
        or PYTHON.resolve() != PYTHON_BASE
        or Path(sys.executable).resolve() != PYTHON_BASE
        or not PYTHON_BASE.is_file()
        or digest(PYTHON_BASE) != PYTHON_BASE_SHA256
        or not sys.flags.isolated
    ):
        raise SystemExit("AC-12 requires the pinned /usr/bin/python3.12 runtime")


def authority(path: Path) -> dict[str, Any]:
    return {
        "sha256": digest(path),
        "git_mode": subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-s", "--", str(path.relative_to(ROOT))],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.split()[0],
    }


def wait_port(port: int, seconds: float = 60.0) -> None:
    deadline = time.monotonic() + seconds
    consecutive = 0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                consecutive += 1
                if consecutive == 2:
                    return
        except OSError:
            consecutive = 0
        time.sleep(0.5)
    raise RuntimeError(f"isolated port {port} did not become ready")


def docker_port(container: str, internal: str) -> int:
    value = run(
        ["docker", "inspect", "--format", f'{{{{(index (index .NetworkSettings.Ports "{internal}") 0).HostPort}}}}', container],
        capture_output=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9]+", value):
        raise RuntimeError("Docker returned an invalid bound port")
    port = int(value)
    if port in {5432, 6379}:
        raise RuntimeError("Docker used a forbidden default host port")
    return port


def validate_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != 2:
        raise RuntimeError("wrong workload evidence schema")
    if payload.get("authority") != "backend/scripts/run_outbox_slo_workload.py":
        raise RuntimeError("wrong workload authority")
    if payload.get("result") != "PASS":
        raise RuntimeError("outbox workload did not pass")
    workload = payload.get("workload", {})
    expected_fields = {
        "warmup": 500,
        "events": 10_000,
        "rate_per_second": 20,
        "claimers": 4,
        "batch_size": 50,
        "handlers": 8,
        "aggregates_per_type": 200,
        "sequences_per_aggregate": 10,
        "transient_failures": 50,
    }
    for key, expected in expected_fields.items():
        if workload.get(key) != expected:
            raise RuntimeError(f"workload field mismatch: {key}")
    if workload.get("event_types") != list(EXPECTED_EVENT_TYPES):
        raise RuntimeError("workload event types differ from the frozen contract")
    if payload.get("terminal") != {
        "completed": 10_000, "pending": 0, "processing": 0, "dead": 0, "total": 10_000
    }:
        raise RuntimeError("terminal event counts differ from AC-12")
    latencies = payload.get("latency_seconds")
    if not isinstance(latencies, list) or len(latencies) != 10_000:
        raise RuntimeError("raw 10k latency series missing")
    latency_hash = hashlib.sha256(
        (json.dumps(latencies, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    if latency_hash != payload.get("latency_input_sha256"):
        raise RuntimeError("latency input digest mismatch")
    numeric_latencies = [float(value) for value in latencies]
    if any(not math.isfinite(value) or value < 0 for value in numeric_latencies):
        raise RuntimeError("latency series contains a non-finite/negative value")
    calculated_p95 = sorted(numeric_latencies)[
        math.ceil(0.95 * len(latencies)) - 1
    ]
    if abs(calculated_p95 - float(payload.get("p95_delivery_seconds", -1))) > 1e-9:
        raise RuntimeError("nearest-rank p95 was not calculated from the raw series")
    enqueue = payload.get("enqueue_offsets_seconds")
    if not isinstance(enqueue, list) or len(enqueue) != 10_000:
        raise RuntimeError("raw enqueue timing series missing")
    enqueue_hash = hashlib.sha256(
        (json.dumps(enqueue, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    if enqueue_hash != payload.get("enqueue_offsets_sha256"):
        raise RuntimeError("enqueue timing digest mismatch")
    numeric_enqueue = [float(offset) for offset in enqueue]
    if any(not math.isfinite(value) or value < 0 for value in numeric_enqueue):
        raise RuntimeError("enqueue series contains a non-finite/negative value")
    if numeric_enqueue != sorted(numeric_enqueue) or any(
        abs(offset - index / 20.0) > 0.75
        for index, offset in enumerate(numeric_enqueue)
    ):
        raise RuntimeError("measured feed did not hold the locked 20 events/second schedule")
    ratios = payload.get("failure_ratio_samples")
    pending = payload.get("pending_age_samples")
    if not isinstance(ratios, list) or not ratios or not isinstance(pending, list) or not pending:
        raise RuntimeError("raw ratio/pending samples missing")
    pending_keys = {
        "elapsed_seconds",
        "oldest_pending_seconds",
        "head_blocked_age_seconds",
    }
    if any(not isinstance(item, dict) or set(item) != pending_keys for item in pending):
        raise RuntimeError("pending-age sample schema differs from the contract")
    pending_elapsed = [float(item["elapsed_seconds"]) for item in pending]
    oldest_pending = [float(item["oldest_pending_seconds"]) for item in pending]
    head_blocked = [float(item["head_blocked_age_seconds"]) for item in pending]
    if any(
        not math.isfinite(value) or value < 0
        for value in pending_elapsed + oldest_pending + head_blocked
    ):
        raise RuntimeError("pending-age samples contain non-finite/negative values")
    if (
        len(pending_elapsed) < 200
        or pending_elapsed[0] > 2.5
        or pending_elapsed != sorted(pending_elapsed)
        or pending_elapsed[-1] < 499.0
    ):
        raise RuntimeError("pending-age samples do not cover the full 500-second feed")
    if any(
        later - earlier > 2.5
        for earlier, later in zip(pending_elapsed, pending_elapsed[1:])
    ):
        raise RuntimeError("pending-age sampling has an unexplained gap")
    ratio_keys = {"elapsed_seconds", "attempts", "failures", "ratio"}
    if any(not isinstance(item, dict) or set(item) != ratio_keys for item in ratios):
        raise RuntimeError("failure-ratio sample schema differs from the contract")
    ratio_elapsed = [float(item["elapsed_seconds"]) for item in ratios]
    ratio_values = [float(item["ratio"]) for item in ratios]
    ratio_attempts = [item["attempts"] for item in ratios]
    ratio_failures = [item["failures"] for item in ratios]
    if any(not math.isfinite(value) or value < 0 for value in ratio_elapsed + ratio_values):
        raise RuntimeError("failure-ratio samples contain non-finite/negative values")
    if any(type(value) is not int or value < 200 for value in ratio_attempts):
        raise RuntimeError("failure-ratio sample attempts are invalid")
    if any(type(value) is not int or value < 0 for value in ratio_failures):
        raise RuntimeError("failure-ratio sample failures are invalid")
    if (
        len(ratio_elapsed) < 65
        or ratio_elapsed[0] > 15.0
        or ratio_elapsed[-1] < 495.0
        or ratio_elapsed != sorted(ratio_elapsed)
        or ratio_attempts != sorted(ratio_attempts)
        or ratio_failures != sorted(ratio_failures)
    ):
        raise RuntimeError("failure-ratio samples are not monotonic")
    if any(
        failures > attempts or abs(ratio - failures / attempts) > 1e-12
        for attempts, failures, ratio in zip(
            ratio_attempts, ratio_failures, ratio_values
        )
    ):
        raise RuntimeError("failure-ratio samples are not bound to raw counts")
    if any(
        later - earlier > 7.5
        for earlier, later in zip(ratio_elapsed, ratio_elapsed[1:])
    ):
        raise RuntimeError("failure-ratio sampling has an unexplained gap")
    if max(ratio_values) >= 0.01:
        raise RuntimeError("one-hour failure-ratio threshold failed")
    if not calculated_p95 < 30:
        raise RuntimeError("p95 delivery threshold failed")
    declared_oldest = float(payload["oldest_pending_seconds"])
    if (
        not math.isfinite(declared_oldest)
        or abs(declared_oldest - max(oldest_pending)) > 1e-9
        or max(oldest_pending) >= 60
        or max(head_blocked) >= 60
    ):
        raise RuntimeError("oldest pending threshold failed")
    if (
        payload.get("delivery_attempts") != 10_050
        or payload.get("failed_attempts") != 50
        or payload.get("duplicate_effects") != 0
        or abs(float(payload.get("failure_ratio", -1)) - 50 / 10_050) > 1e-12
    ):
        raise RuntimeError("fault/idempotency counts differ from contract")
    if (
        ratio_attempts[-1] != payload["delivery_attempts"]
        or ratio_failures[-1] != payload["failed_attempts"]
        or abs(ratio_values[-1] - float(payload["failure_ratio"])) > 1e-12
    ):
        raise RuntimeError("failure-ratio samples are not bound to terminal attempts")
    if (
        payload.get("effective_sales_mutations") != 2_000
        or payload.get("sales_transport_calls") != 2_000
    ):
        raise RuntimeError("sales effective-once count differs from contract")
    receipts = payload.get("receipt_counts")
    if (
        not isinstance(receipts, dict)
        or set(receipts) != set(EXPECTED_EVENT_TYPES)
        or any(type(value) is not int or value != 2_000 for value in receipts.values())
    ):
        raise RuntimeError("consumer receipt counts differ from contract")
    if payload.get("protected_live_promotion_executed") is not False:
        raise RuntimeError("protected live promotion was executed")
    if payload.get("salary_export_executed") is not False:
        raise RuntimeError("salary export was executed")
    dispatch = payload.get("production_dispatch")
    if dispatch != {
        "repository": "repositories.transactional_outbox.TransactionalOutboxRepository",
        "dispatcher": "services.outbox_worker.dispatch_outbox_once",
        "sales_delivery": "services.grile_outbox_delivery.deliver_sales_generation_event",
        "sales_producer": "repositories.transactional_outbox.emit_sales_generation_promoted",
        "dispatcher_valkey_dependency": False,
    }:
        raise RuntimeError("production outbox API binding is missing or drifted")
    expected_sources = {
        "repositories.transactional_outbox": (
            "backend/repositories/transactional_outbox.py",
            ["TransactionalOutboxRepository", "emit_sales_generation_promoted"],
        ),
        "services.outbox_worker": (
            "backend/services/outbox_worker.py",
            ["dispatch_outbox_once"],
        ),
        "services.grile_outbox_delivery": (
            "backend/services/grile_outbox_delivery.py",
            ["deliver_sales_generation_event"],
        ),
    }
    sources = payload.get("production_api")
    if not isinstance(sources, dict) or set(sources) != set(expected_sources):
        raise RuntimeError("production source authorities are incomplete")
    for module, (relative, symbols) in expected_sources.items():
        item = sources[module]
        path = ROOT / relative
        if (
            item.get("path") != relative
            or item.get("symbols") != symbols
            or item.get("sha256") != digest(path)
        ):
            raise RuntimeError(f"production source authority mismatch: {module}")
    fixture = payload.get("fixture_adapters")
    if fixture != {
        "non_sales_producers": [
            "emit_retail_pnl_generation_promoted",
            "emit_retail_salary_import_completed",
            "emit_retail_planning_forecast_promoted",
            "emit_retail_grile_manifest_approved",
        ],
        "source": "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql",
        "effects": "deterministic non-network callbacks; sales uses production delivery chain",
    }:
        raise RuntimeError("fixture adapters are not explicitly bounded")
    migration_manifest = json.loads(MIGRATION_MANIFEST.read_text(encoding="utf-8"))
    locked_migration_sha = migration_manifest["migrations"][MIGRATION.name]
    if (
        locked_migration_sha != digest(MIGRATION)
        or payload.get("migration_069_checksum") != locked_migration_sha
    ):
        raise RuntimeError("migration 069 evidence is not bound to its manifest")


def self_test() -> None:
    fake = {
        "authority": "backend/scripts/run_outbox_slo_workload.py",
        "result": "PASS",
    }
    try:
        validate_payload(fake)
    except RuntimeError:
        pass
    else:
        raise SystemExit("manual PASS payload was accepted")
    latencies = [0.1] * 10_000
    enqueue = [index / 20.0 for index in range(10_000)]
    pending = [
        {
            "elapsed_seconds": float(index),
            "oldest_pending_seconds": 1.0,
            "head_blocked_age_seconds": 1.0,
        }
        for index in range(501)
    ]
    ratio_elapsed = list(range(0, 501, 5))
    ratios = [
        {
            "elapsed_seconds": float(elapsed),
            "attempts": 200 + ((10_050 - 200) * index // (len(ratio_elapsed) - 1)),
            "failures": (
                50
                if index == len(ratio_elapsed) - 1
                else min(49, (50 * index // (len(ratio_elapsed) - 1)))
            ),
            "ratio": 0.0,
        }
        for index, elapsed in enumerate(ratio_elapsed)
    ]
    for item in ratios:
        item["ratio"] = item["failures"] / item["attempts"]
    adversarial: dict[str, Any] = {
        "schema_version": 2,
        "authority": "backend/scripts/run_outbox_slo_workload.py",
        "result": "PASS",
        "workload": {
            "warmup": 500,
            "events": 10_000,
            "rate_per_second": 20,
            "claimers": 4,
            "batch_size": 50,
            "handlers": 8,
            "event_types": list(EXPECTED_EVENT_TYPES),
            "aggregates_per_type": 200,
            "sequences_per_aggregate": 10,
            "transient_failures": 50,
        },
        "terminal": {
            "completed": 10_000,
            "pending": 0,
            "processing": 0,
            "dead": 0,
            "total": 10_000,
        },
        "latency_seconds": latencies,
        "latency_input_sha256": hashlib.sha256(
            (json.dumps(latencies, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "p95_delivery_seconds": 0.1,
        "enqueue_offsets_seconds": enqueue,
        "enqueue_offsets_sha256": hashlib.sha256(
            (json.dumps(enqueue, sort_keys=True, separators=(",", ":")) + "\n").encode()
        ).hexdigest(),
        "failure_ratio_samples": ratios,
        "pending_age_samples": pending,
        "oldest_pending_seconds": 1.0,
        "delivery_attempts": 10_050,
        "failed_attempts": 50,
        "duplicate_effects": 0,
        "failure_ratio": 50 / 10_050,
        "effective_sales_mutations": 2_000,
        "sales_transport_calls": 2_000,
        "receipt_counts": {event_type: 2_000 for event_type in EXPECTED_EVENT_TYPES},
    }
    forged_oldest = copy.deepcopy(adversarial)
    forged_oldest["pending_age_samples"][0]["oldest_pending_seconds"] = 9_999.0
    try:
        validate_payload(forged_oldest)
    except RuntimeError as exc:
        if "oldest pending threshold failed" not in str(exc):
            raise
    else:
        raise SystemExit("forged oldest-pending summary was accepted")
    sparse_samples = copy.deepcopy(adversarial)
    sparse_samples["pending_age_samples"] = [pending[-1]]
    sparse_samples["failure_ratio_samples"] = [ratios[-1]]
    try:
        validate_payload(sparse_samples)
    except RuntimeError as exc:
        if "samples do not cover" not in str(exc):
            raise
    else:
        raise SystemExit("sparse pending/ratio samples were accepted")
    forged_ratio = copy.deepcopy(adversarial)
    forged_ratio["failure_ratio_samples"][10]["ratio"] = 0.0
    try:
        validate_payload(forged_ratio)
    except RuntimeError as exc:
        if "not bound to raw counts" not in str(exc):
            raise
    else:
        raise SystemExit("forged intermediate failure-ratio sample was accepted")
    forged_receipts = copy.deepcopy(adversarial)
    forged_receipts["receipt_counts"] = {
        f"retail.fake_event_{index}.v1": 2_000 for index in range(5)
    }
    try:
        validate_payload(forged_receipts)
    except RuntimeError as exc:
        if "consumer receipt counts differ" not in str(exc):
            raise
    else:
        raise SystemExit("forged receipt event types were accepted")
    environment = {
        **os.environ,
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
    }
    completed = subprocess.run(
        [str(PYTHON), "-B", "-I", str(DRIVER), "--self-test"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr or completed.stdout)
    print(
        "outbox gate self-test PASS: fake PASS, forged pending summary and "
        "forged receipt keys rejected; driver contract stable"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for name in ("seed", "warmup", "events", "rate", "claimers", "batch_size", "handlers"):
        parser.add_argument("--" + name.replace("_", "-"), type=int)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return args
    actual = {key: getattr(args, key) for key in EXPECTED}
    if actual != EXPECTED:
        parser.error(f"workload differs from locked AC-12 contract: {actual!r}")
    if args.evidence is None:
        parser.error("--evidence is required")
    if args.evidence.exists() or args.evidence.is_symlink():
        parser.error("evidence already exists")
    return args


def main() -> None:
    args = parse_args()
    verify_python_identity()
    if args.self_test:
        self_test()
        return
    if os.getenv("UNIHUB_TEST_DATABASE") != "1":
        raise SystemExit("UNIHUB_TEST_DATABASE=1 is required")
    if socket.gethostname() != "dell-standby":
        raise SystemExit("AC-12 SLO gate is locked to dell-standby")
    for path in (DRIVER, BOOTSTRAP, PYTHON):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise SystemExit(f"required locked authority missing/not executable: {path}")
    for path in (ENGINE, MIGRATION, MIGRATION_MANIFEST):
        if not path.is_file():
            raise SystemExit(f"required locked authority missing: {path}")
    if shutil.which("docker") is None or shutil.which("openssl") is None:
        raise SystemExit("docker and openssl are required")
    sha = run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    tree = run(["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"], capture_output=True).stdout.strip()
    dirty = run(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
    ).stdout
    if dirty:
        raise SystemExit("candidate worktree must be clean")
    password = run(["openssl", "rand", "-hex", "24"], capture_output=True).stdout.strip()
    stamp = f"{int(time.time())}-{os.getpid()}"
    postgres = f"unihub-outbox-pg-{stamp}"
    valkey = f"unihub-outbox-valkey-{stamp}"
    containers = [postgres, valkey]
    run(["docker", "image", "inspect", POSTGRES_IMAGE, VALKEY_IMAGE], stdout=subprocess.DEVNULL)
    with tempfile.TemporaryDirectory(prefix="retail-outbox-slo-") as temp:
        raw = Path(temp) / "raw.json"
        try:
            run([
                "docker", "run", "--pull=never", "-d", "--name", postgres, "--label", "unihub.test=retail-outbox",
                "-e", "POSTGRES_USER=unihub_test", "-e", f"POSTGRES_PASSWORD={password}",
                "-e", "POSTGRES_DB=unihub_test_outbox", "-p", "127.0.0.1::5432", POSTGRES_IMAGE,
            ], stdout=subprocess.DEVNULL)
            run([
                "docker", "run", "--pull=never", "-d", "--name", valkey, "--label", "unihub.test=retail-outbox",
                "-p", "127.0.0.1::6379", VALKEY_IMAGE,
            ], stdout=subprocess.DEVNULL)
            pg_port = docker_port(postgres, "5432/tcp")
            valkey_port = docker_port(valkey, "6379/tcp")
            wait_port(pg_port)
            wait_port(valkey_port)
            dsn = f"postgresql://unihub_test:{password}@127.0.0.1:{pg_port}/unihub_test_outbox"
            valkey_url = f"redis://127.0.0.1:{valkey_port}/15"
            env = {
                **os.environ,
                "DATABASE_URL": dsn,
                "UNIHUB_TEST_DATABASE": "1",
                "UNIHUB_RUNNING_TESTS": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONSAFEPATH": "1",
            }
            run(
                [str(PYTHON), "-B", "-I", str(BOOTSTRAP)],
                env=env,
                stdout=subprocess.DEVNULL,
            )
            command = [
                str(PYTHON), "-B", "-I", str(DRIVER), "--dsn", dsn, "--valkey-url", valkey_url,
                "--seed", str(args.seed), "--warmup", str(args.warmup),
                "--events", str(args.events), "--rate", str(args.rate),
                "--claimers", str(args.claimers), "--batch-size", str(args.batch_size),
                "--handlers", str(args.handlers), "--output", str(raw),
            ]
            started = time.monotonic()
            run(command, env=env)
            duration = time.monotonic() - started
            payload = json.loads(raw.read_text(encoding="utf-8"))
            validate_payload(payload)
        finally:
            for container in containers:
                subprocess.run(
                    ["docker", "rm", "-f", "-v", container],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        evidence = {
            "schema_version": 1,
            "result": "PASS",
            "sha": sha,
            "tree": tree,
            "command": "UNIHUB_TEST_DATABASE=1 backend/venv/bin/python -B -I scripts/run_outbox_slo_gate.py --seed 20260812 --warmup 500 --events 10000 --rate 20 --claimers 4 --batch-size 50 --handlers 8 --evidence <path>",
            "duration_seconds": duration,
            "environment": {
                "host": socket.gethostname(),
                "python": platform.python_version(),
                "python_resolved_path": str(PYTHON_BASE),
                "python_sha256": PYTHON_BASE_SHA256,
                "postgres_image": POSTGRES_IMAGE,
                "valkey_image": VALKEY_IMAGE,
            },
            "required_authorities": {
                str(path.relative_to(ROOT)): authority(path)
                for path in (
                    Path(__file__).resolve(),
                    DRIVER,
                    ENGINE,
                    BOOTSTRAP,
                    MIGRATION,
                    MIGRATION_MANIFEST,
                    ROOT / "backend/repositories/transactional_outbox.py",
                    ROOT / "backend/services/outbox_worker.py",
                    ROOT / "backend/services/grile_outbox_delivery.py",
                )
            },
            "raw_evidence_sha256": digest(raw),
            "raw": payload,
            "protected_live_promotion_executed": False,
            "salary_export_executed": False,
        }
        args.evidence.parent.mkdir(parents=True, exist_ok=True)
        args.evidence.write_text(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    print(f"outbox SLO gate PASS: {sha} ({args.evidence})")


if __name__ == "__main__":
    main()
