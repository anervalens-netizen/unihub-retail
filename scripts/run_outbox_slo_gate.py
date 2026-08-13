#!/usr/bin/env python3
"""Own an isolated PostgreSQL/Valkey lifecycle for the AC-12 SLO authority."""

from __future__ import annotations

import argparse
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


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "backend/scripts/run_outbox_slo_workload.py"
BOOTSTRAP = ROOT / "backend/scripts/bootstrap_test_db.py"
PYTHON = Path(os.getenv("UNIHUB_BACKEND_VENV", str(ROOT / "backend/venv"))) / "bin/python"
MIGRATION = ROOT / "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql"
MIGRATION_MANIFEST = ROOT / "backend/db/migrations/manifest.json"
POSTGRES_IMAGE = "postgres:18-alpine"
VALKEY_IMAGE = "valkey/valkey:8.1.7-alpine"
EXPECTED = {
    "seed": 20260812,
    "warmup": 500,
    "events": 10_000,
    "rate": 20,
    "claimers": 4,
    "batch_size": 50,
    "handlers": 8,
}


def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, **kwargs)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    calculated_p95 = sorted(float(value) for value in latencies)[
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
    if any(
        abs(float(offset) - index / 20.0) > 0.75
        for index, offset in enumerate(enqueue)
    ):
        raise RuntimeError("measured feed did not hold the locked 20 events/second schedule")
    ratios = payload.get("failure_ratio_samples")
    pending = payload.get("pending_age_samples")
    if not isinstance(ratios, list) or not ratios or not isinstance(pending, list) or not pending:
        raise RuntimeError("raw ratio/pending samples missing")
    pending_elapsed = [float(item["elapsed_seconds"]) for item in pending]
    if pending_elapsed != sorted(pending_elapsed) or pending_elapsed[-1] < 499.0:
        raise RuntimeError("pending-age samples do not cover the full 500-second feed")
    if any(
        later - earlier > 2.5
        for earlier, later in zip(pending_elapsed, pending_elapsed[1:])
    ):
        raise RuntimeError("pending-age sampling has an unexplained gap")
    ratio_elapsed = [float(item["elapsed_seconds"]) for item in ratios]
    if any(
        later - earlier > 7.5
        for earlier, later in zip(ratio_elapsed, ratio_elapsed[1:])
    ):
        raise RuntimeError("failure-ratio sampling has an unexplained gap")
    if max(float(item["ratio"]) for item in ratios) >= 0.01:
        raise RuntimeError("one-hour failure-ratio threshold failed")
    if not calculated_p95 < 30:
        raise RuntimeError("p95 delivery threshold failed")
    if not float(payload["oldest_pending_seconds"]) < 60:
        raise RuntimeError("oldest pending threshold failed")
    if (
        payload.get("delivery_attempts") != 10_050
        or payload.get("failed_attempts") != 50
        or payload.get("duplicate_effects") != 0
        or abs(float(payload.get("failure_ratio", -1)) - 50 / 10_050) > 1e-12
    ):
        raise RuntimeError("fault/idempotency counts differ from contract")
    if (
        payload.get("effective_sales_mutations") != 2_000
        or payload.get("sales_transport_calls") != 2_000
    ):
        raise RuntimeError("sales effective-once count differs from contract")
    receipts = payload.get("receipt_counts")
    if not isinstance(receipts, dict) or len(receipts) != 5 or set(receipts.values()) != {2_000}:
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
    environment = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    completed = subprocess.run(
        [str(PYTHON if PYTHON.exists() else Path(sys.executable)), str(DRIVER), "--self-test"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr or completed.stdout)
    print("outbox gate self-test PASS: fake PASS rejected; driver contract stable")


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
    for path in (MIGRATION, MIGRATION_MANIFEST):
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
    with tempfile.TemporaryDirectory(prefix="retail-outbox-slo-") as temp:
        raw = Path(temp) / "raw.json"
        try:
            run([
                "docker", "run", "-d", "--name", postgres, "--label", "unihub.test=retail-outbox",
                "-e", "POSTGRES_USER=unihub_test", "-e", f"POSTGRES_PASSWORD={password}",
                "-e", "POSTGRES_DB=unihub_test_outbox", "-p", "127.0.0.1::5432", POSTGRES_IMAGE,
            ], stdout=subprocess.DEVNULL)
            run([
                "docker", "run", "-d", "--name", valkey, "--label", "unihub.test=retail-outbox",
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
                "PYTHONPATH": str(ROOT / "backend"),
            }
            run([str(PYTHON), str(BOOTSTRAP)], env=env, stdout=subprocess.DEVNULL)
            command = [
                str(PYTHON), str(DRIVER), "--dsn", dsn, "--valkey-url", valkey_url,
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
            "command": "UNIHUB_TEST_DATABASE=1 PYTHONPATH=backend backend/venv/bin/python scripts/run_outbox_slo_gate.py --seed 20260812 --warmup 500 --events 10000 --rate 20 --claimers 4 --batch-size 50 --handlers 8 --evidence <path>",
            "duration_seconds": duration,
            "environment": {
                "host": socket.gethostname(),
                "python": platform.python_version(),
                "postgres_image": POSTGRES_IMAGE,
                "valkey_image": VALKEY_IMAGE,
            },
            "required_authorities": {
                str(path.relative_to(ROOT)): authority(path)
                for path in (
                    Path(__file__).resolve(),
                    DRIVER,
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
