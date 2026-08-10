#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT_DIR}/backend/venv/bin/python"
STAMP="${GITHUB_RUN_ID:-local}-$$"
PG_CONTAINER="unihub-retail-real-e2e-pg-${STAMP}"
VALKEY_CONTAINER="unihub-retail-real-e2e-valkey-${STAMP}"
RUNTIME_DIR="$(mktemp -d)"
BACKEND_PID=""
OIDC_PID=""
WORKER_PID=""
EXPORT_WORKER_PID=""
RESTORE_BACKEND_PID=""

cleanup() {
  for pid in "${EXPORT_WORKER_PID}" "${RESTORE_BACKEND_PID}" "${WORKER_PID}" "${BACKEND_PID}" "${OIDC_PID}"; do
    if [[ -n "${pid}" ]]; then kill "${pid}" >/dev/null 2>&1 || true; fi
  done
  timeout 30 docker rm -f -v "${PG_CONTAINER}" >/dev/null 2>&1 || true
  timeout 30 docker rm -f -v "${VALKEY_CONTAINER}" >/dev/null 2>&1 || true
  rm -rf "${RUNTIME_DIR}"
}
trap cleanup EXIT

if [[ ! -x "${PYTHON}" ]]; then
  printf 'Missing backend virtualenv.\n' >&2
  exit 1
fi
mkdir -p "${ROOT_DIR}/test-results/real-e2e-runtime"

password="$(openssl rand -hex 24)"
docker run -d --name "${PG_CONTAINER}" --label unihub.test=retail \
  -e POSTGRES_USER=unihub_test -e POSTGRES_PASSWORD="${password}" \
  -e POSTGRES_DB=unihub_test -p 127.0.0.1::5432 postgres:18-alpine >/dev/null
docker run -d --name "${VALKEY_CONTAINER}" --label unihub.test=retail \
  -p 127.0.0.1::6379 valkey/valkey:8.1.7-alpine >/dev/null

for _ in $(seq 1 60); do
  docker exec "${PG_CONTAINER}" pg_isready -U unihub_test -d unihub_test >/dev/null 2>&1 && break
  sleep 1
done
for _ in $(seq 1 60); do
  docker exec "${VALKEY_CONTAINER}" valkey-cli ping >/dev/null 2>&1 && break
  sleep 1
done
pg_port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "${PG_CONTAINER}")"
valkey_port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "6379/tcp") 0).HostPort}}' "${VALKEY_CONTAINER}")"
backend_port="$(${PYTHON} -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
oidc_port="$(${PYTHON} -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"

export DATABASE_URL="postgresql://unihub_test:${password}@127.0.0.1:${pg_port}/unihub_test"
export UNIHUB_RUNNING_TESTS=1 UNIHUB_TEST_DATABASE=1 UNIHUB_ENV=development
export DB_POOL_MIN_SIZE=1 DB_POOL_MAX_SIZE=8
export VALKEY_URL="redis://127.0.0.1:${valkey_port}/0"
export SESSION_VALKEY_URL="redis://127.0.0.1:${valkey_port}/1"
export RATE_LIMIT_VALKEY_URL="redis://127.0.0.1:${valkey_port}/2"
export TRUSTED_PROXY_CIDRS="127.0.0.1/32"
export RATE_LIMIT_CLIENT_IP_HEADER=none
export RATE_LIMIT_KEY_HMAC_SECRET=rrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrrr
export RATE_LIMIT_FAILURE_MODE=closed
export RATE_LIMIT_REPORT_EXPORT=100000
export RATE_LIMIT_REPORT_EXPORT_WINDOW=86400
export OIDC_STUB_ORIGIN="http://127.0.0.1:${oidc_port}"
export OIDC_ISSUER="${OIDC_STUB_ORIGIN}/application/o/retail/"
export OIDC_JWKS_URL="${OIDC_STUB_ORIGIN}/jwks"
export OIDC_AUDIENCE=retail-api OIDC_CLIENT_ID=retail-client
export OIDC_CLIENT_SECRET=synthetic-real-e2e-secret
export SESSION_ENCRYPTION_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=
export SESSION_PUBLIC_ORIGIN="http://127.0.0.1:${backend_port}"
export OIDC_STUB_REDIRECT_URI="${SESSION_PUBLIC_ORIGIN}/auth/callback"
export SESSION_TTL_SECONDS=900
export REAL_E2E_BASE_URL="${SESSION_PUBLIC_ORIGIN}"
export REAL_E2E_OIDC_ORIGIN="${OIDC_STUB_ORIGIN}"
export BACKEND_SENTRY_DSN=""
export SENTRY_DSN=""
export VITE_FRONTEND_GLITCHTIP_DSN=""

cd "${ROOT_DIR}/backend"
"${PYTHON}" scripts/bootstrap_test_db.py
docker exec -i "${PG_CONTAINER}" psql -U unihub_test -d unihub_test \
  -v ON_ERROR_STOP=1 >/dev/null <<'SQL'
CREATE TABLE fieldops_visits (
  asm text, data_raport date, completion_pct numeric, durata_vizita_ore numeric,
  magazin text, curatenie boolean, imagine boolean, uniforma boolean,
  afise boolean, produse_promo boolean, status text
);
INSERT INTO fieldops_visits VALUES
  ('ASM Restore', '2098-01-02', 100, 1.5, 'Restore Store', true, true, true, true, true, 'approved');
INSERT INTO stores (site_code, locatie, firma, regional, asm, first_seen_month, last_seen_month)
VALUES ('RESTORE-1', 'Restore Store', 'Mobiup', 'RM Restore', 'ASM Restore', '2098-01', '2098-01');
INSERT INTO import_snapshots (
  import_month, filename, status, rows_in_file, rows_imported, source_sha256,
  cutoff_date, generation_token, owner_id, lease_until
) VALUES (
  '2098-01', 'restore-drill.xlsx', 'processing', 1, 1, repeat('a', 64),
  '2098-01-02', '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222', now() + interval '1 hour'
);
INSERT INTO sales_import_stage_rows (
  snapshot_id, row_number, import_month, sale_date, site_code, locatie, firma,
  regional, asm, bon_nr, item_code, item_name, quantity, unit_price,
  total_value, agent, is_cartela, is_return
)
SELECT id, 1, '2098-01', '2098-01-02', 'RESTORE-1', 'Restore Store', 'Mobiup',
  'RM Restore', 'ASM Restore', 'RESTORE-BON', 'RESTORE-SKU', 'Restore Item',
  1, 10, 10, 'Restore Agent', false, false
FROM import_snapshots WHERE filename = 'restore-drill.xlsx';
UPDATE import_snapshots
SET manifest = jsonb_build_object(
      'generation_state', 'promoted',
      'stage_rows_sha256', sales_stage_rows_sha256(id),
      'rows_imported', 1,
      'store_count', 1,
      'total_quantity', 1,
      'total_value', 10,
      'max_sale_date', '2098-01-02',
      'anomalies', '[]'::jsonb
    ),
    manifest_sha256 = repeat('b', 64)
WHERE filename = 'restore-drill.xlsx';
INSERT INTO sales_transactions (
  import_month, sale_date, site_code, bon_nr, item_code, item_name,
  quantity, unit_price, total_value, agent, snapshot_id
)
SELECT '2098-01', '2098-01-02', 'RESTORE-1', 'RESTORE-BON', 'RESTORE-SKU',
  'Restore Item', 1, 10, 10, 'Restore Agent', id
FROM import_snapshots WHERE filename = 'restore-drill.xlsx';
INSERT INTO store_targets (import_month, site_code, target_value, source_file)
VALUES ('2098-01', 'RESTORE-1', 100, 'restore-drill');
INSERT INTO salary_private.people (person_id, normalized_name, identity_source)
VALUES ('sp1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'restore person', 'name');
INSERT INTO salary_records (
  year, month, full_name, total_salary, company_name, site_code, locatie, person_id
) VALUES (
  2098, 1, 'Restore Person', 4000, 'Mobiup', 'RESTORE-1', 'Restore Store',
  'sp1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
);
INSERT INTO tasks (title, assignee, site_code, status, source)
VALUES ('Restore drill task', 'Restore Agent', 'RESTORE-1', 'deschis', 'restore-drill');
INSERT INTO grile_monthly_operations (op, closing_month, dry_run, status, result)
VALUES ('archive', '2098-01', true, 'completed', '{"restore_drill":true}');
INSERT INTO sales_generation_heads (import_month, snapshot_id, revision)
SELECT '2098-01', id, 1 FROM import_snapshots WHERE filename = 'restore-drill.xlsx';
UPDATE import_snapshots
SET status = 'completed', promoted_at = now(), lease_until = NULL
WHERE filename = 'restore-drill.xlsx';
SQL

"${PYTHON}" -m uvicorn scripts.oidc_e2e_stub:app --host 127.0.0.1 --port "${oidc_port}" \
  >"${ROOT_DIR}/test-results/real-e2e-runtime/oidc.log" 2>&1 &
OIDC_PID=$!
"${PYTHON}" -m uvicorn main:app --host 127.0.0.1 --port "${backend_port}" \
  >"${ROOT_DIR}/test-results/real-e2e-runtime/backend.log" 2>&1 &
BACKEND_PID=$!
for _ in $(seq 1 60); do
  curl -fsS "${OIDC_STUB_ORIGIN}/jwks" >/dev/null 2>&1 \
    && curl -fsS "${REAL_E2E_BASE_URL}/readyz" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "${OIDC_STUB_ORIGIN}/jwks" >/dev/null
curl -fsS "${REAL_E2E_BASE_URL}/readyz" >/dev/null

cd "${ROOT_DIR}"
npx playwright test --config=playwright.real.config.ts

export EXPORT_ARTIFACT_DIR="${RUNTIME_DIR}/export-artifacts"
RETAIL_WORKER_ROLE=exports "${PYTHON}" backend/worker.py \
  >test-results/real-e2e-runtime/export-worker.log 2>&1 &
EXPORT_WORKER_PID=$!
sleep 3
if ! kill -0 "${EXPORT_WORKER_PID}" 2>/dev/null; then
  printf 'Export worker failed to start.\n' >&2
  cat test-results/real-e2e-runtime/export-worker.log >&2
  exit 1
fi
"${PYTHON}" backend/scripts/run_mixed_load_gate.py \
  --base-url "${REAL_E2E_BASE_URL}" --token-url "${OIDC_STUB_ORIGIN}/test-token/admin" \
  --output test-results/real-e2e-load-gate.json
kill "${EXPORT_WORKER_PID}"
wait "${EXPORT_WORKER_PID}" || true
EXPORT_WORKER_PID=""
if rg -n 'Traceback|Config invalid|Worker startup failed|ERROR' \
  test-results/real-e2e-runtime/export-worker.log; then
  printf 'Export worker emitted an error.\n' >&2
  exit 1
fi

docker exec "${PG_CONTAINER}" pg_dump -U unihub_test -Fc unihub_test >"${RUNTIME_DIR}/retail.dump"
docker exec "${PG_CONTAINER}" createdb -U unihub_test unihub_restore_test
docker exec -i "${PG_CONTAINER}" pg_restore --exit-on-error -U unihub_test -d unihub_restore_test <"${RUNTIME_DIR}/retail.dump"

critical_tables=(schema_migrations stores import_snapshots sales_import_stage_rows sales_transactions store_targets salary_records tasks grile_monthly_operations sales_generation_heads fieldops_visits)
business_state() {
  local database="$1" output="$2" table state
  : >"$output"
  for table in "${critical_tables[@]}"; do
    state="$(docker exec "${PG_CONTAINER}" psql -U unihub_test -d "$database" -Atc \
      "SELECT count(*) || E'\\t' || md5(COALESCE(string_agg(row_hash, '' ORDER BY row_hash), '')) FROM (SELECT md5((to_jsonb(t) - 'cnp')::text) AS row_hash FROM ${table} AS t) AS rows")"
    [[ "${state%%$'\t'*}" -gt 0 ]] || { printf 'Restore drill table is empty: %s\n' "$table" >&2; exit 1; }
    printf '%s\t%s\n' "$table" "$state" >>"$output"
  done
}

source_state="${RUNTIME_DIR}/restore-source.tsv"
restored_state="${RUNTIME_DIR}/restore-target.tsv"
business_state unihub_test "$source_state"
business_state unihub_restore_test "$restored_state"
cmp "$source_state" "$restored_state" || { printf 'Restore business hashes differ.\n' >&2; exit 1; }

restore_backend_port="$(${PYTHON} -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
restore_database_url="postgresql://unihub_test:${password}@127.0.0.1:${pg_port}/unihub_restore_test"
DATABASE_URL="$restore_database_url" SESSION_PUBLIC_ORIGIN="http://127.0.0.1:${restore_backend_port}" \
  "${PYTHON}" -m uvicorn main:app --app-dir "${ROOT_DIR}/backend" \
  --host 127.0.0.1 --port "$restore_backend_port" \
  >test-results/real-e2e-runtime/restore-backend.log 2>&1 &
RESTORE_BACKEND_PID=$!
for _ in $(seq 1 30); do
  curl -fsS "http://127.0.0.1:${restore_backend_port}/readyz" >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS "http://127.0.0.1:${restore_backend_port}/readyz" >/dev/null
kill "$RESTORE_BACKEND_PID"
wait "$RESTORE_BACKEND_PID" || true
RESTORE_BACKEND_PID=""

"${PYTHON}" - "$source_state" test-results/real-e2e-restore-drill.json <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys

state = Path(sys.argv[1]).read_text(encoding="utf-8")
tables = {}
for line in state.splitlines():
    table, count, digest = line.split("\t")
    tables[table] = {"rows": int(count), "business_hash": digest}
evidence = {
    "status": "passed",
    "restored_app_ready": True,
    "critical_tables": tables,
    "business_state_sha256": sha256(state.encode("utf-8")).hexdigest(),
}
Path(sys.argv[2]).write_text(json.dumps(evidence, sort_keys=True) + "\n", encoding="utf-8")
PY
sha256sum test-results/real-e2e-restore-drill.json >test-results/real-e2e-restore-drill.json.sha256

export RETAIL_WORKER_ROLE=operations
"${PYTHON}" backend/worker.py >test-results/real-e2e-runtime/worker-first.log 2>&1 &
WORKER_PID=$!
sleep 3
kill "${WORKER_PID}"
wait "${WORKER_PID}" || true
"${PYTHON}" backend/worker.py >test-results/real-e2e-runtime/worker-restarted.log 2>&1 &
WORKER_PID=$!
sleep 3
kill "${WORKER_PID}"
wait "${WORKER_PID}" || true
WORKER_PID=""
if rg -n 'Traceback|Config invalid|ERROR' test-results/real-e2e-runtime/worker-*.log; then
  printf 'Worker recovery emitted an error.\n' >&2
  exit 1
fi
printf '{"status":"passed","role":"operations","restart_count":1}\n' \
  >test-results/real-e2e-worker-recovery.json

PYTHONPATH="${ROOT_DIR}/backend" "${PYTHON}" backend/scripts/run_import_overlap_gate.py \
  test-results/real-e2e-import-overlap.json
if ! rg -q 'ImportAlreadyRunningError: Exista deja un import in curs pentru luna 2099-11' \
  test-results/real-e2e-runtime/import-overlap-worker-*.log; then
  printf 'Import worker overlap gate did not record exactly one expected lease conflict.\n' >&2
  exit 1
fi
if rg -n 'Config invalid|Worker startup failed' \
  test-results/real-e2e-runtime/import-overlap-worker-*.log; then
  printf 'Import worker overlap gate emitted a startup error.\n' >&2
  exit 1
fi
