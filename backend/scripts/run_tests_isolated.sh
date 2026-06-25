#!/usr/bin/env bash

set -Eeuo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${BACKEND_DIR}/venv/bin/python"
PYTEST="${BACKEND_DIR}/venv/bin/pytest"
STAMP="${GITHUB_RUN_ID:-local}-$(date +%s)-$$"
CONTAINER="unihub-retail-test-${STAMP}"

cleanup() {
  timeout 30 docker rm -f -v "${CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ ! -x "${PYTHON}" || ! -x "${PYTEST}" ]]; then
  printf 'Missing backend virtualenv. Install requirements in backend/venv first.\n' >&2
  exit 1
fi

password="$(openssl rand -hex 24)"
docker run -d \
  --name "${CONTAINER}" \
  --label unihub.test=retail \
  -e POSTGRES_USER=unihub_test \
  -e POSTGRES_PASSWORD="${password}" \
  -e POSTGRES_DB=unihub_test \
  -p 127.0.0.1::5432 \
  postgres:18-alpine >/dev/null

port="$(
  docker inspect \
    --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' \
    "${CONTAINER}"
)"

for _ in $(seq 1 60); do
  if docker exec "${CONTAINER}" pg_isready -U unihub_test -d unihub_test \
    >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${CONTAINER}" pg_isready -U unihub_test -d unihub_test >/dev/null

export DATABASE_URL="postgresql://unihub_test:${password}@127.0.0.1:${port}/unihub_test"
export UNIHUB_RUNNING_TESTS=1
export UNIHUB_TEST_DATABASE=1
export SENTRY_DSN=
export VITE_GLITCHTIP_DSN=
export DB_POOL_MIN_SIZE=1
export DB_POOL_MAX_SIZE=4

cd "${BACKEND_DIR}"
"${PYTHON}" scripts/bootstrap_test_db.py

if [[ "$#" -eq 0 ]]; then
  set -- tests -q
elif [[ "$1" == -* ]]; then
  set -- tests "$@"
fi
"${PYTEST}" "$@"
