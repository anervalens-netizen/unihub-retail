#!/usr/bin/env bash

set -Eeuo pipefail

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
[[ -x "$PYTHON" && -x "$PYTEST" ]] || {
  printf 'Release-A gate requires backend/venv.\n' >&2
  exit 1
}
git -C "$ROOT_DIR" diff --quiet
git -C "$ROOT_DIR" diff --cached --quiet

CURRENT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
STAMP="release-a-${CURRENT_SHA:0:12}-$$"
POSTGRES_CONTAINER="unihub-retail-${STAMP}"
VALKEY_CONTAINER="unihub-retail-valkey-${STAMP}"
TEMP_DIR="$(mktemp -d)"
EVIDENCE_DIR="$(dirname "$EVIDENCE_PATH")"
JUNIT_PATH="$EVIDENCE_DIR/release-a-schema.xml"

cleanup() {
  timeout 30 docker rm -f -v "$POSTGRES_CONTAINER" >/dev/null 2>&1 || true
  timeout 30 docker rm -f -v "$VALKEY_CONTAINER" >/dev/null 2>&1 || true
  if [[ "$TEMP_DIR" == /tmp/tmp.* && -d "$TEMP_DIR" ]]; then
    rm -rf -- "$TEMP_DIR"
  fi
}
trap cleanup EXIT

mkdir -p "$EVIDENCE_DIR" "$TEMP_DIR/baseline"
git -C "$ROOT_DIR" archive "$BASELINE_SHA" | tar -x -C "$TEMP_DIR/baseline"

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
export DATABASE_URL="postgresql://unihub_test:${PASSWORD}@127.0.0.1:${POSTGRES_PORT}/unihub_test"

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

docker exec "$POSTGRES_CONTAINER" \
  pg_dump -U unihub_test -d unihub_test -Fc -f /tmp/pre069.dump
PRE069_DUMP_SHA256="$(
  docker exec "$POSTGRES_CONTAINER" sha256sum /tmp/pre069.dump | awk '{print $1}'
)"
docker exec "$POSTGRES_CONTAINER" createdb -U unihub_test unihub_restore_test
docker exec "$POSTGRES_CONTAINER" \
  pg_restore -U unihub_test -d unihub_restore_test /tmp/pre069.dump

export DATABASE_URL="postgresql://unihub_test:${PASSWORD}@127.0.0.1:${POSTGRES_PORT}/unihub_restore_test"
"$PYTHON" "$ROOT_DIR/backend/scripts/bootstrap_test_db.py" >/dev/null

cd "$ROOT_DIR/backend"
"$PYTEST" tests/test_release_a_schema_069.py -q --junitxml="$JUNIT_PATH"
cd "$ROOT_DIR"

export CURRENT_SHA BASELINE_SHA PRE069_DUMP_SHA256 EVIDENCE_PATH JUNIT_PATH ROOT_DIR
"$PYTHON" - <<'PY'
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess

import asyncpg


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", os.environ["ROOT_DIR"], *args],
        text=True,
    ).strip()


async def database_evidence() -> dict[str, object]:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
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
    return {
        "restored_marker_count": int(marker),
        "migration_count": len(applied),
        "last_migration": str(applied[-1]["filename"]),
        "migration_069_checksum": str(applied[-1]["checksum"]),
        "outbox_event_count": int(outbox_count),
        "schema_catalog_sha256": hashlib.sha256(serialized).hexdigest(),
        "schema_catalog_entry_count": len(catalog_rows),
    }


changed = git("diff", "--name-only", os.environ["BASELINE_SHA"], os.environ["CURRENT_SHA"]).splitlines()
runtime_changes = [
    path
    for path in changed
    if path.startswith(("src/", "ops/", ".github/"))
    or path in {"package.json", "package-lock.json", "vite.config.ts", "tsconfig.json"}
    or (
        path.startswith("backend/")
        and not path.startswith("backend/db/migrations/")
        and not path.startswith("backend/tests/")
    )
]
if runtime_changes:
    raise SystemExit(f"Release-A application scope changed: {runtime_changes}")

database = asyncio.run(database_evidence())
expected_069 = hashlib.sha256(
    (Path(os.environ["ROOT_DIR"]) / "backend/db/migrations/069_ai_cohort_and_transactional_outbox.sql").read_bytes()
).hexdigest()
if database != {
    **database,
    "restored_marker_count": 1,
    "last_migration": "069_ai_cohort_and_transactional_outbox.sql",
    "migration_069_checksum": expected_069,
    "outbox_event_count": 0,
}:
    raise SystemExit("Release-A restored database evidence failed")

manifest_path = Path(os.environ["ROOT_DIR"]) / "backend/db/migrations/manifest.json"
evidence = {
    "schema_version": 1,
    "result": "PASS",
    "baseline_sha": os.environ["BASELINE_SHA"],
    "release_a_sha": os.environ["CURRENT_SHA"],
    "application_runtime_changes": runtime_changes,
    "changed_path_count": len(changed),
    "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "migration_069_sha256": expected_069,
    "pre_069_dump_sha256": os.environ["PRE069_DUMP_SHA256"],
    "junit_sha256": hashlib.sha256(Path(os.environ["JUNIT_PATH"]).read_bytes()).hexdigest(),
    "database": database,
    "assertions": {
        "empty_database_bootstrap_through_068": True,
        "sanitized_dump_restore": True,
        "upgrade_068_to_069": True,
        "baseline_application_source_unchanged": True,
        "release_a_runtime_ready": True,
        "pre_069_manifest_refused": True,
        "outbox_inert": True,
    },
}
path = Path(os.environ["EVIDENCE_PATH"])
path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"result": "PASS", "release_a_sha": os.environ["CURRENT_SHA"]}))
PY
