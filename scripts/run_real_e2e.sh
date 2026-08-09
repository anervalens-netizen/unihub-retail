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

cleanup() {
  for pid in "${WORKER_PID}" "${BACKEND_PID}" "${OIDC_PID}"; do
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
docker exec "${PG_CONTAINER}" psql -U unihub_test -d unihub_test -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE fieldops_visits (asm text, data_raport date, completion_pct numeric, durata_vizita_ore numeric, magazin text, curatenie boolean, imagine boolean, uniforma boolean, afise boolean, produse_promo boolean, status text); INSERT INTO import_snapshots (import_month, filename, status, rows_in_file, rows_imported) VALUES ('2026-07', 'real-e2e.xlsx', 'completed', 0, 0)" \
  >/dev/null

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

"${PYTHON}" backend/scripts/run_mixed_load_gate.py \
  --base-url "${REAL_E2E_BASE_URL}" --token-url "${OIDC_STUB_ORIGIN}/test-token/admin" \
  --output test-results/real-e2e-load-gate.json

docker exec "${PG_CONTAINER}" pg_dump -U unihub_test -Fc unihub_test >"${RUNTIME_DIR}/retail.dump"
docker exec "${PG_CONTAINER}" createdb -U unihub_test unihub_restore
docker exec -i "${PG_CONTAINER}" pg_restore -U unihub_test -d unihub_restore <"${RUNTIME_DIR}/retail.dump"
source_count="$(docker exec "${PG_CONTAINER}" psql -U unihub_test -d unihub_test -Atc 'select count(*) from schema_migrations')"
restore_count="$(docker exec "${PG_CONTAINER}" psql -U unihub_test -d unihub_restore -Atc 'select count(*) from schema_migrations')"
if [[ "${source_count}" != "${restore_count}" ]]; then printf 'Restore migration count mismatch.\n' >&2; exit 1; fi
printf '{"status":"passed","source_migrations":%s,"restored_migrations":%s}\n' \
  "${source_count}" "${restore_count}" >test-results/real-e2e-restore-drill.json

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
