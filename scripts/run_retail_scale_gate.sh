#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${UNIHUB_SCALE_PYTHON:-$ROOT/backend/venv/bin/python}"
POSTGRES_IMAGE="postgres@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"
[[ -x "$PYTHON" ]] || PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3

if [[ "${1:-}" == "--self-test" ]]; then
  UNIHUB_TEST_DATABASE=1 UNIHUB_RUNNING_TESTS=1 "$PYTHON" "$ROOT/backend/scripts/run_retail_scale_profile.py" --self-test
  exit 0
fi

seed=20260812
profiles=2x,5x
exact_max_upload=33554432
evidence="$ROOT/evidence/ac-13"
while (($#)); do
  case "$1" in
    --seed) seed="$2"; shift 2 ;;
    --profiles) profiles="$2"; shift 2 ;;
    --exact-max-upload) exact_max_upload="$2"; shift 2 ;;
    --evidence) evidence="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$seed" == 20260812 && "$profiles" == 2x,5x && "$exact_max_upload" == 33554432 ]] || { echo "AC-13 exact contract required" >&2; exit 2; }
blocked() {
  mkdir -p "$evidence"
  local target="$evidence/ac-13-scale-evidence.json" temporary="$evidence/.ac-13-scale-evidence.tmp"
  printf '{"result":"BLOCKED","reason":"%s","available_bytes":%s,"required_bytes":%s}\n' "$1" "$2" "$3" >"$temporary"
  mv "$temporary" "$target"; echo "AC-13 BLOCKED: $1; evidence=$target" >&2; exit 1
}
command -v docker >/dev/null || blocked docker_unavailable 0 1
docker image inspect "$POSTGRES_IMAGE" >/dev/null \
  || blocked pinned_postgres_image_unavailable 0 1
available_kib="$(df -Pk "${DOCKER_ROOT_DIR:-/var/lib/docker}" 2>/dev/null | awk 'NR==2{print $4}' || df -Pk / | awk 'NR==2{print $4}')"
available_mem_kib="$(awk '/MemAvailable:/{print $2}' /proc/meminfo)"
(( available_kib >= 41943040 )) || blocked insufficient_docker_storage "$((available_kib*1024))" 42949672960
(( available_mem_kib >= 8388608 )) || blocked insufficient_available_ram "$((available_mem_kib*1024))" 8589934592

container="unihub-retail-ac13-${RANDOM}-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT INT TERM
docker run --pull=never -d --rm --name "$container" --label unihub.retail.scale.authority=ac13 \
  -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=test_scale_admin \
  -p 127.0.0.1::5432 "$POSTGRES_IMAGE" >/dev/null
for _ in {1..60}; do
  docker exec "$container" pg_isready -U postgres -d test_scale_admin >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$container" pg_isready -U postgres -d test_scale_admin >/dev/null
port="$(docker port "$container" 5432/tcp | sed -E 's/.*:([0-9]+)$/\1/')"
[[ "$port" =~ ^[0-9]+$ && "$port" != 5432 ]] || { echo "AC-13 unsafe Docker port" >&2; exit 1; }
mkdir -p "$evidence"
export UNIHUB_TEST_DATABASE=1 UNIHUB_RUNNING_TESTS=1
export UNIHUB_SCALE_ADMIN_DSN="postgresql://postgres@127.0.0.1:${port}/test_scale_admin"
"$PYTHON" "$ROOT/backend/scripts/run_retail_scale_profile.py" \
  --seed "$seed" --profiles "$profiles" --exact-max-upload "$exact_max_upload" --evidence "$evidence"
