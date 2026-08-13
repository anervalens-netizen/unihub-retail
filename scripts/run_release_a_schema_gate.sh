#!/usr/bin/env bash

set -Eeuo pipefail
GATE_STARTED_EPOCH_NS="$(date +%s%N)"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASELINE_SHA="0be82b430e55b7414babf470abe3fc5404b6cdc9"
PYTHON="$ROOT_DIR/backend/venv/bin/python"
PYTEST="$ROOT_DIR/backend/venv/bin/pytest"
EVIDENCE_PATH=""

usage() {
  printf 'usage: %s --evidence <path.json>\n' "${0##*/}" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      EVIDENCE_PATH="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$EVIDENCE_PATH" ]] || { usage; exit 2; }
if [[ "$EVIDENCE_PATH" != /* ]]; then
  EVIDENCE_PATH="$ROOT_DIR/$EVIDENCE_PATH"
fi
[[ -x "$PYTHON" && -x "$PYTEST" ]] || {
  printf 'Release-A gate requires backend/venv.\n' >&2
  exit 1
}
[[ -z "$(git -C "$ROOT_DIR" status --porcelain)" ]] || {
  printf 'Release-A gate requires a clean worktree including untracked files.\n' >&2
  exit 1
}
export PYTHONNOUSERSITE=1
export PYTHONSAFEPATH=1
unset MYPYPATH MYPY_CONFIG_FILE

CURRENT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
STAMP="release-a-${CURRENT_SHA:0:12}-$$"
POSTGRES_CONTAINER="unihub-retail-${STAMP}"
VALKEY_CONTAINER="unihub-retail-valkey-${STAMP}"
TEMP_DIR="$(mktemp -d)"
EVIDENCE_DIR="$(dirname "$EVIDENCE_PATH")"
JUNIT_EMPTY_PATH="$EVIDENCE_DIR/release-a-schema-empty.xml"
JUNIT_RESTORED_PATH="$EVIDENCE_DIR/release-a-schema-restored.xml"
CANDIDATE_EVIDENCE_PATH="$EVIDENCE_DIR/release-a-candidate.json"
EXPECTED_EVIDENCE_PATH="$ROOT_DIR/test-results/closure/$CURRENT_SHA/release-a/schema-gate.json"
[[ "$EVIDENCE_PATH" == "$EXPECTED_EVIDENCE_PATH" ]] || {
  printf 'Release-A evidence path must be exact-SHA canonical path.\n' >&2
  exit 1
}
for fresh_path in "$EVIDENCE_PATH" "$JUNIT_EMPTY_PATH" \
  "$JUNIT_RESTORED_PATH" "$CANDIDATE_EVIDENCE_PATH"; do
  [[ ! -e "$fresh_path" && ! -L "$fresh_path" ]] || {
    printf 'Release-A evidence path must be new: %s\n' "$fresh_path" >&2
    exit 1
  }
done

cleanup() {
  timeout 30 docker rm -f -v "$POSTGRES_CONTAINER" >/dev/null 2>&1 || true
  timeout 30 docker rm -f -v "$VALKEY_CONTAINER" >/dev/null 2>&1 || true
  if [[ "$TEMP_DIR" == /tmp/tmp.* && -d "$TEMP_DIR" ]]; then
    rm -rf -- "$TEMP_DIR"
  fi
}
trap cleanup EXIT

mkdir -p "$EVIDENCE_DIR" "$TEMP_DIR/baseline"
[[ ! -L "$ROOT_DIR/test-results" && ! -L "$ROOT_DIR/test-results/closure" \
  && ! -L "$ROOT_DIR/test-results/closure/$CURRENT_SHA" \
  && ! -L "$EVIDENCE_DIR" \
  && "$(realpath -m "$EVIDENCE_DIR")" == "$EVIDENCE_DIR" ]] || {
  printf 'Release-A evidence directory contains an unsafe symlink.\n' >&2
  exit 1
}
git -C "$ROOT_DIR" archive "$BASELINE_SHA" | tar -x -C "$TEMP_DIR/baseline"
"$PYTHON" "$ROOT_DIR/scripts/check_release_a_candidate.py" \
  --evidence "$CANDIDATE_EVIDENCE_PATH"

PASSWORD="$(openssl rand -hex 24)"
docker run -d \
  --name "$POSTGRES_CONTAINER" \
  --label unihub.test=retail-release-a \
  -e POSTGRES_USER=unihub_test \
  -e POSTGRES_PASSWORD="$PASSWORD" \
  -e POSTGRES_DB=unihub_test \
  -p 127.0.0.1::5432 \
  postgres:18-alpine >/dev/null
docker run -d \
  --name "$VALKEY_CONTAINER" \
  --label unihub.test=retail-release-a \
  -p 127.0.0.1::6379 \
  valkey/valkey:8.1.7-alpine >/dev/null

POSTGRES_READY=0
VALKEY_READY=0
for _ in $(seq 1 60); do
  if docker exec "$POSTGRES_CONTAINER" pg_isready -U unihub_test -d unihub_test \
      >/dev/null 2>&1; then
    POSTGRES_READY=$((POSTGRES_READY + 1))
  else
    POSTGRES_READY=0
  fi
  if docker exec "$VALKEY_CONTAINER" valkey-cli ping >/dev/null 2>&1; then
    VALKEY_READY=$((VALKEY_READY + 1))
  else
    VALKEY_READY=0
  fi
  if [[ "$POSTGRES_READY" -ge 2 && "$VALKEY_READY" -ge 2 ]]; then
    break
  fi
  sleep 1
done
[[ "$POSTGRES_READY" -ge 2 && "$VALKEY_READY" -ge 2 ]] || {
  printf 'Release-A isolated dependencies did not become ready.\n' >&2
  exit 1
}

POSTGRES_PORT="$(
  docker inspect \
    --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' \
    "$POSTGRES_CONTAINER"
)"
VALKEY_PORT="$(
  docker inspect \
    --format '{{(index (index .NetworkSettings.Ports "6379/tcp") 0).HostPort}}' \
    "$VALKEY_CONTAINER"
)"

export UNIHUB_RUNNING_TESTS=1
export UNIHUB_TEST_DATABASE=1
export UNIHUB_ENV=development
export BACKEND_SENTRY_DSN=
export BACKEND_SENTRY_TRACES_SAMPLE_RATE=0
export SENTRY_DSN=
export SENTRY_TRACES_SAMPLE_RATE=0
export VITE_FRONTEND_GLITCHTIP_DSN=
export DB_POOL_MIN_SIZE=1
export DB_POOL_MAX_SIZE=4
export RATE_LIMIT_TEST_VALKEY_URL="redis://127.0.0.1:${VALKEY_PORT}/15"
BASELINE_DATABASE_NAME="unihub_test"
EMPTY_DATABASE_NAME="unihub_empty_069_test"
RESTORED_DATABASE_NAME="unihub_restore_069_test"
BASELINE_DATABASE_URL="postgresql://unihub_test:${PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${BASELINE_DATABASE_NAME}"
EMPTY_DATABASE_URL="postgresql://unihub_test:${PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${EMPTY_DATABASE_NAME}"
RESTORED_DATABASE_URL="postgresql://unihub_test:${PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${RESTORED_DATABASE_NAME}"
export DATABASE_URL="$BASELINE_DATABASE_URL"

database_state() {
  DATABASE_URL="$1" "$PYTHON" - <<'PY'
from __future__ import annotations

import asyncio
import hashlib
import json
import os

import asyncpg


async def main() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        database_name = await connection.fetchval("SELECT current_database()")
        public_table_count = await connection.fetchval(
            """
            SELECT count(*)
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        has_ledger = await connection.fetchval(
            "SELECT to_regclass('public.schema_migrations') IS NOT NULL"
        )
        rows = []
        marker_count = 0
        if has_ledger:
            rows = await connection.fetch(
                "SELECT filename, checksum FROM schema_migrations ORDER BY filename"
            )
            has_meta = await connection.fetchval(
                "SELECT to_regclass('public.schema_meta') IS NOT NULL"
            )
            if has_meta:
                marker_count = await connection.fetchval(
                    """
                    SELECT count(*) FROM schema_meta
                    WHERE schema_name = 'release_a_synthetic_restore_marker'
                      AND schema_hash = $1
                    """,
                    "6" * 64,
                )
    finally:
        await connection.close()
    ledger = [
        {"filename": str(row["filename"]), "checksum": str(row["checksum"])}
        for row in rows
    ]
    payload = json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
    print(
        json.dumps(
            {
                "database_name": str(database_name),
                "public_table_count": int(public_table_count),
                "migration_count": len(ledger),
                "last_migration": ledger[-1]["filename"] if ledger else None,
                "ledger_sha256": hashlib.sha256(payload).hexdigest(),
                "restored_marker_count": int(marker_count),
            },
            sort_keys=True,
        )
    )


asyncio.run(main())
PY
}

"$PYTHON" "$TEMP_DIR/baseline/backend/scripts/bootstrap_test_db.py" >/dev/null
"$PYTHON" - <<'PY'
import asyncio
import os

import asyncpg


async def main() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        maximum = await connection.fetchval("SELECT max(filename) FROM schema_migrations")
        if maximum != "068_grile_v2_forecast_digest_authority.sql":
            raise RuntimeError("pre-069 fixture did not stop at migration 068")
        await connection.execute(
            """
            INSERT INTO schema_meta (schema_name, schema_hash)
            VALUES ('release_a_synthetic_restore_marker', $1)
            """,
            "6" * 64,
        )
    finally:
        await connection.close()


asyncio.run(main())
PY
BASELINE_068_STATE_JSON="$(database_state "$BASELINE_DATABASE_URL")"

docker exec "$POSTGRES_CONTAINER" \
  pg_dump -U unihub_test -d unihub_test -Fc -f /tmp/pre069.dump
PRE069_DUMP_SHA256="$(
  docker exec "$POSTGRES_CONTAINER" sha256sum /tmp/pre069.dump | awk '{print $1}'
)"
docker exec "$POSTGRES_CONTAINER" createdb -U unihub_test "$EMPTY_DATABASE_NAME"
EMPTY_INITIAL_STATE_JSON="$(database_state "$EMPTY_DATABASE_URL")"
export DATABASE_URL="$EMPTY_DATABASE_URL"
"$PYTHON" "$ROOT_DIR/backend/scripts/bootstrap_test_db.py" >/dev/null
EMPTY_FINAL_STATE_JSON="$(database_state "$EMPTY_DATABASE_URL")"

docker exec "$POSTGRES_CONTAINER" createdb -U unihub_test "$RESTORED_DATABASE_NAME"
docker exec "$POSTGRES_CONTAINER" \
  pg_restore -U unihub_test -d "$RESTORED_DATABASE_NAME" /tmp/pre069.dump
RESTORED_PRE_UPGRADE_STATE_JSON="$(database_state "$RESTORED_DATABASE_URL")"

export DATABASE_URL="$RESTORED_DATABASE_URL"
"$PYTHON" "$ROOT_DIR/backend/scripts/bootstrap_test_db.py" >/dev/null
RESTORED_FINAL_STATE_JSON="$(database_state "$RESTORED_DATABASE_URL")"

cd "$ROOT_DIR/backend"
export DATABASE_URL="$EMPTY_DATABASE_URL"
"$PYTEST" tests/test_release_a_schema_069.py -q --junitxml="$JUNIT_EMPTY_PATH"
export DATABASE_URL="$RESTORED_DATABASE_URL"
"$PYTEST" tests/test_release_a_schema_069.py -q --junitxml="$JUNIT_RESTORED_PATH"
cd "$ROOT_DIR"

export CURRENT_SHA BASELINE_SHA PRE069_DUMP_SHA256 EVIDENCE_PATH ROOT_DIR
export JUNIT_EMPTY_PATH JUNIT_RESTORED_PATH
export BASELINE_DATABASE_URL EMPTY_DATABASE_URL RESTORED_DATABASE_URL
export BASELINE_068_STATE_JSON EMPTY_INITIAL_STATE_JSON EMPTY_FINAL_STATE_JSON
export RESTORED_PRE_UPGRADE_STATE_JSON RESTORED_FINAL_STATE_JSON
export CANDIDATE_EVIDENCE_PATH
export GATE_STARTED_EPOCH_NS
"$PYTHON" - <<'PY'
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import asyncpg


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", os.environ["ROOT_DIR"], *args],
        text=True,
    ).strip()


async def database_evidence(database_url: str) -> dict[str, object]:
    connection = await asyncpg.connect(database_url)
    try:
        database_name = await connection.fetchval("SELECT current_database()")
        marker = await connection.fetchval(
            """
            SELECT count(*)
            FROM schema_meta
            WHERE schema_name = 'release_a_synthetic_restore_marker'
              AND schema_hash = $1
            """,
            "6" * 64,
        )
        applied = await connection.fetch(
            "SELECT filename, checksum FROM schema_migrations ORDER BY filename"
        )
        outbox_count = await connection.fetchval(
            "SELECT count(*) FROM retail_outbox_events"
        )
        catalog_rows = await connection.fetch(
            """
            SELECT kind, name, definition
            FROM (
                SELECT 'column'::text AS kind,
                       table_name || '.' || column_name AS name,
                       data_type || ':' || is_nullable || ':' || COALESCE(column_default, '') AS definition
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'ai_forecast_cohort_snapshots',
                      'ai_forecast_cohort_rows',
                      'retail_outbox_events',
                      'retail_outbox_consumer_receipts',
                      'retail_outbox_replay_audit'
                  )
                UNION ALL
                SELECT 'constraint', conname, pg_get_constraintdef(oid, true)
                FROM pg_constraint
                WHERE conrelid IN (
                    'ai_forecast_cohort_snapshots'::regclass,
                    'ai_forecast_cohort_rows'::regclass,
                    'retail_outbox_events'::regclass,
                    'retail_outbox_consumer_receipts'::regclass,
                    'retail_outbox_replay_audit'::regclass
                )
                UNION ALL
                SELECT 'index', indexname, indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename IN (
                      'ai_forecast_cohort_snapshots',
                      'ai_forecast_cohort_rows',
                      'retail_outbox_events',
                      'retail_outbox_consumer_receipts',
                      'retail_outbox_replay_audit'
                  )
            ) AS catalog
            ORDER BY kind, name, definition
            """
        )
    finally:
        await connection.close()
    serialized = json.dumps(
        [dict(row) for row in catalog_rows],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    ledger_serialized = json.dumps(
        [dict(row) for row in applied],
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return {
        "database_name": str(database_name),
        "restored_marker_count": int(marker),
        "migration_count": len(applied),
        "last_migration": str(applied[-1]["filename"]),
        "migration_069_checksum": str(applied[-1]["checksum"]),
        "ledger_sha256": hashlib.sha256(ledger_serialized).hexdigest(),
        "outbox_event_count": int(outbox_count),
        "schema_catalog_sha256": hashlib.sha256(serialized).hexdigest(),
        "schema_catalog_entry_count": len(catalog_rows),
    }


candidate_evidence_path = Path(os.environ["CANDIDATE_EVIDENCE_PATH"])
candidate_evidence = json.loads(candidate_evidence_path.read_text(encoding="utf-8"))
if candidate_evidence.get("result") != "PASS":
    raise SystemExit("Release-A exact candidate/source/typecheck gate did not pass")
changed = candidate_evidence["changed_paths"]

baseline_068 = json.loads(os.environ["BASELINE_068_STATE_JSON"])
empty_initial = json.loads(os.environ["EMPTY_INITIAL_STATE_JSON"])
empty_final_state = json.loads(os.environ["EMPTY_FINAL_STATE_JSON"])
restored_pre_upgrade = json.loads(os.environ["RESTORED_PRE_UPGRADE_STATE_JSON"])
restored_final_state = json.loads(os.environ["RESTORED_FINAL_STATE_JSON"])
empty_database = asyncio.run(database_evidence(os.environ["EMPTY_DATABASE_URL"]))
restored_database = asyncio.run(database_evidence(os.environ["RESTORED_DATABASE_URL"]))
expected_069 = hashlib.sha256(
    (Path(os.environ["ROOT_DIR"]) / "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql").read_bytes()
).hexdigest()
database_names = {
    baseline_068["database_name"],
    empty_initial["database_name"],
    restored_pre_upgrade["database_name"],
}
if len(database_names) != 3:
    raise SystemExit("Release-A database paths are not distinct")
if empty_initial != {
    **empty_initial,
    "public_table_count": 0,
    "migration_count": 0,
    "last_migration": None,
    "restored_marker_count": 0,
}:
    raise SystemExit("Release-A empty database was not empty before bootstrap")
if baseline_068["migration_count"] != 68 or baseline_068["last_migration"] != "068_grile_v2_forecast_digest_authority.sql":
    raise SystemExit("Release-A baseline fixture did not stop at 068")
if restored_pre_upgrade != {
    **restored_pre_upgrade,
    "migration_count": 68,
    "last_migration": "068_grile_v2_forecast_digest_authority.sql",
    "ledger_sha256": baseline_068["ledger_sha256"],
    "public_table_count": baseline_068["public_table_count"],
    "restored_marker_count": 1,
}:
    raise SystemExit("Release-A restored fixture does not equal the dumped 068 ledger")
for state in (empty_final_state, restored_final_state):
    if state["migration_count"] != 69 or state["last_migration"] != "069_ai_cohort_and_transactional_outbox.sql":
        raise SystemExit("Release-A final database ledger did not reach 069")
if empty_final_state["ledger_sha256"] != restored_final_state["ledger_sha256"]:
    raise SystemExit("Release-A empty and restored final ledgers differ")
for database, marker_count in ((empty_database, 0), (restored_database, 1)):
    if database["restored_marker_count"] != marker_count:
        raise SystemExit("Release-A database restore marker mismatch")
    if database["migration_count"] != 69 or database["last_migration"] != "069_ai_cohort_and_transactional_outbox.sql":
        raise SystemExit("Release-A database evidence did not reach 069")
    if database["migration_069_checksum"] != expected_069 or database["outbox_event_count"] != 0:
        raise SystemExit("Release-A database migration hash or outbox inertness failed")
if empty_database["ledger_sha256"] != empty_final_state["ledger_sha256"]:
    raise SystemExit("Release-A empty database ledger changed after bootstrap")
if restored_database["ledger_sha256"] != restored_final_state["ledger_sha256"]:
    raise SystemExit("Release-A restored database ledger changed after upgrade")
if empty_database["schema_catalog_sha256"] != restored_database["schema_catalog_sha256"]:
    raise SystemExit("Release-A empty and restored schema catalogs differ")

manifest_path = Path(os.environ["ROOT_DIR"]) / "backend/db/migrations/manifest.json"
evidence = {
    "schema_version": 1,
    "result": "PASS",
    "baseline_sha": os.environ["BASELINE_SHA"],
    "release_a_sha": os.environ["CURRENT_SHA"],
    "contract_content_commit": candidate_evidence["contract_content_commit"],
    "contract_lock_commit": candidate_evidence["contract_lock_commit"],
    "command": [
        "scripts/run_release_a_schema_gate.sh",
        "--evidence",
        os.environ["EVIDENCE_PATH"],
    ],
    "duration_seconds": round(
        (time.time_ns() - int(os.environ["GATE_STARTED_EPOCH_NS"])) / 1_000_000_000,
        6,
    ),
    "candidate_gate_sha256": hashlib.sha256(candidate_evidence_path.read_bytes()).hexdigest(),
    "candidate_tree": candidate_evidence["candidate_tree"],
    "changed_paths": changed,
    "changed_path_count": len(changed),
    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "migration_069_sha256": expected_069,
    "compatibility_test_sha256": hashlib.sha256(
        (Path(os.environ["ROOT_DIR"]) / "backend/tests/test_release_a_schema_069.py").read_bytes()
    ).hexdigest(),
    "pre_069_dump_sha256": os.environ["PRE069_DUMP_SHA256"],
    "junit_empty_sha256": hashlib.sha256(
        Path(os.environ["JUNIT_EMPTY_PATH"]).read_bytes()
    ).hexdigest(),
    "junit_restored_sha256": hashlib.sha256(
        Path(os.environ["JUNIT_RESTORED_PATH"]).read_bytes()
    ).hexdigest(),
    "database_paths": {
        "baseline_068": baseline_068,
        "empty_initial": empty_initial,
        "empty_final": empty_database,
        "restored_pre_upgrade": restored_pre_upgrade,
        "restored_final": restored_database,
    },
    "assertions": {
        "database_identities_distinct": True,
        "empty_database_initially_zero_tables": True,
        "empty_database_bootstrap_through_069": True,
        "sanitized_dump_restore": True,
        "restored_database_pre_upgrade_through_068": True,
        "restored_database_upgrade_068_to_069": True,
        "final_schema_ledgers_equal": True,
        "final_schema_catalogs_equal": True,
        "exact_source_transform": True,
        "direct_unshadowed_full_mypy": True,
        "release_a_runtime_ready_on_empty": True,
        "release_a_runtime_ready_on_restored": True,
        "pre_069_manifest_refused_on_empty": True,
        "pre_069_manifest_refused_on_restored": True,
        "outbox_inert": True,
    },
}
path = Path(os.environ["EVIDENCE_PATH"])
path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"result": "PASS", "release_a_sha": os.environ["CURRENT_SHA"]}))
PY
