#!/usr/bin/env bash

set -Eeuo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${BACKEND_DIR}/venv/bin/python"
PYTEST="${BACKEND_DIR}/venv/bin/pytest"
STAMP="${GITHUB_RUN_ID:-local}-$(date +%s)-$$"
CONTAINER="unihub-retail-test-${STAMP}"
VALKEY_CONTAINER="unihub-retail-valkey-test-${STAMP}"
POSTGRES_IMAGE="postgres@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"
VALKEY_IMAGE="valkey/valkey@sha256:b027235326507cfdade9b6684056ec1d0b0c0757412e628245129b5d7b788618"
VISITS_TEST_DIR=""

cleanup() {
  timeout 30 docker rm -f -v "${CONTAINER}" >/dev/null 2>&1 || true
  timeout 30 docker rm -f -v "${VALKEY_CONTAINER}" >/dev/null 2>&1 || true
  if [[ -n "${VISITS_TEST_DIR}" ]]; then
    rm -rf "${VISITS_TEST_DIR}"
  fi
}
trap cleanup EXIT

if [[ ! -x "${PYTHON}" || ! -x "${PYTEST}" ]]; then
  printf 'Missing backend virtualenv. Install requirements in backend/venv first.\n' >&2
  exit 1
fi

password="$(openssl rand -hex 24)"
docker image inspect "${POSTGRES_IMAGE}" "${VALKEY_IMAGE}" >/dev/null \
  || { printf 'Pinned isolated-test images are not pre-provisioned.\n' >&2; exit 1; }
docker run --pull=never -d \
  --name "${CONTAINER}" \
  --label unihub.test=retail \
  -e POSTGRES_USER=unihub_test \
  -e POSTGRES_PASSWORD="${password}" \
  -e POSTGRES_DB=unihub_test \
  -p 127.0.0.1::5432 \
  "${POSTGRES_IMAGE}" >/dev/null

docker run --pull=never -d \
  --name "${VALKEY_CONTAINER}" \
  --label unihub.test=retail \
  -p 127.0.0.1::6379 \
  "${VALKEY_IMAGE}" >/dev/null

port="$(
  docker inspect \
    --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' \
    "${CONTAINER}"
)"
valkey_port="$(
  docker inspect \
    --format '{{(index (index .NetworkSettings.Ports "6379/tcp") 0).HostPort}}' \
    "${VALKEY_CONTAINER}"
)"

postgres_ready=0
for _ in $(seq 1 60); do
  if docker exec "${CONTAINER}" pg_isready -U unihub_test -d unihub_test \
    >/dev/null 2>&1; then
    postgres_ready=$((postgres_ready + 1))
    if [[ "${postgres_ready}" -ge 2 ]]; then
      break
    fi
  else
    postgres_ready=0
  fi
  sleep 1
done
if [[ "${postgres_ready}" -lt 2 ]]; then
  printf 'Isolated PostgreSQL did not become stably ready.\n' >&2
  docker logs "${CONTAINER}" >&2 || true
  exit 1
fi
valkey_ready=0
for _ in $(seq 1 60); do
  if docker exec "${VALKEY_CONTAINER}" valkey-cli ping >/dev/null 2>&1; then
    valkey_ready=$((valkey_ready + 1))
    if [[ "${valkey_ready}" -ge 2 ]]; then
      break
    fi
  else
    valkey_ready=0
  fi
  sleep 1
done
if [[ "${valkey_ready}" -lt 2 ]]; then
  printf 'Isolated Valkey did not become stably ready.\n' >&2
  docker logs "${VALKEY_CONTAINER}" >&2 || true
  exit 1
fi

export DATABASE_URL="postgresql://unihub_test:${password}@127.0.0.1:${port}/unihub_test"
export RATE_LIMIT_TEST_VALKEY_URL="redis://127.0.0.1:${valkey_port}/15"
export UNIHUB_RUNNING_TESTS=1
export UNIHUB_TEST_DATABASE=1
export BACKEND_SENTRY_DSN=
export BACKEND_SENTRY_TRACES_SAMPLE_RATE=0
export SENTRY_DSN=
export SENTRY_TRACES_SAMPLE_RATE=0
export VITE_FRONTEND_GLITCHTIP_DSN=
export DB_POOL_MIN_SIZE=1
export DB_POOL_MAX_SIZE=4
VISITS_TEST_DIR="$(mktemp -d)"
mkdir -p "${VISITS_TEST_DIR}/images"
export VISITS_DB_PATH="${VISITS_TEST_DIR}/visits.db"
export VISITS_IMAGES_DIR="${VISITS_TEST_DIR}/images"

"${PYTHON}" - <<'PY'
import os
import sqlite3

con = sqlite3.connect(os.environ["VISITS_DB_PATH"])
con.execute(
    """
    CREATE TABLE visits (
      id INTEGER PRIMARY KEY,
      data_raport TEXT,
      magazin TEXT,
      completion_pct REAL
    )
    """
)
con.commit()
con.close()
PY

cd "${BACKEND_DIR}"
"${PYTHON}" scripts/bootstrap_test_db.py

if [[ "$#" -eq 0 ]]; then
  set -- tests -q
elif [[ "$1" == -* ]]; then
  set -- tests "$@"
fi
"${PYTEST}" "$@"
