#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-/opt/Mobiup/unihub-retail}"
EXPECTED_SHA="${2:-}"

if [[ ! "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "usage: $0 [runtime-root] <40-char-source-sha>" >&2
  exit 64
fi

test -d "$ROOT"
test "$(git -C "$ROOT" rev-parse HEAD)" = "$EXPECTED_SHA"

cd "$ROOT"
PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}" \
  backend/venv/bin/python -c \
  'from db.migration_runner import load_migration_manifest, verify_migration_files; verify_migration_files(load_migration_manifest())'

systemctl is-active --quiet unihub-backend.service
systemctl is-active --quiet unihub-worker.service
systemctl is-active --quiet unihub-import-worker.service
systemctl is-active --quiet unihub-grile-worker.service
systemctl is-active --quiet unihub-export-worker.service
systemctl is-active --quiet unihub-legacy-worker.service
for unit in \
  unihub-backend.service \
  unihub-worker.service \
  unihub-import-worker.service \
  unihub-grile-worker.service \
  unihub-export-worker.service \
  unihub-legacy-worker.service; do
  systemctl is-enabled --quiet "$unit"
done

curl --fail --silent --show-error --max-time 10 http://127.0.0.1:9898/livez >/dev/null
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:9898/readyz >/dev/null

network_env=/opt/Mobiup/ops/prometheus/unihub-retail-network.env
test -r "$network_env"
gateway="$(sed -n 's/^PROMETHEUS_DOCKER_GATEWAY=//p' "$network_env")"
subnet="$(sed -n 's/^PROMETHEUS_DOCKER_SUBNET=//p' "$network_env")"
worker_host="$(sed -n 's/^WORKER_METRICS_HOST=//p' "$network_env")"
backend/venv/bin/python - "$gateway" "$subnet" "$worker_host" <<'PY'
import ipaddress
import sys

gateway = ipaddress.ip_address(sys.argv[1])
subnet = ipaddress.ip_network(sys.argv[2], strict=True)
if not isinstance(gateway, ipaddress.IPv4Address) or gateway not in subnet:
    raise SystemExit("invalid Prometheus bridge environment")
if sys.argv[1] != sys.argv[3] or gateway.is_loopback or gateway.is_unspecified:
    raise SystemExit("worker metrics bind differs from the Prometheus gateway")
PY

for unit in \
  unihub-backend.service \
  unihub-worker.service \
  unihub-import-worker.service \
  unihub-grile-worker.service \
  unihub-export-worker.service \
  unihub-legacy-worker.service \
  unihub-retail-migrate.service; do
  test "$(readlink "/etc/systemd/system/$unit")" = \
    "/var/lib/unihub-retail-deploy/runtime-releases/$EXPECTED_SHA/systemd/$unit"
done

listeners="$(ss -H -ltn '( sport = :9901 or sport = :9902 or sport = :9903 or sport = :9904 )')"
grep -Fq "$gateway:9901" <<<"$listeners"
grep -Fq "$gateway:9902" <<<"$listeners"
grep -Fq "$gateway:9903" <<<"$listeners"
grep -Fq "$gateway:9904" <<<"$listeners"
! grep -Eq '(^|[[:space:]])(0\.0\.0\.0|127\.0\.0\.1):990[1-4]([[:space:]]|$)' <<<"$listeners"

status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --max-time 10 http://127.0.0.1:9898/metrics)"
test "$status" = "404"

targets="$(curl --fail --silent --show-error --max-time 10 \
  http://127.0.0.1:9090/api/v1/targets)"
backend/venv/bin/python -c '
import json
import sys

required = set(sys.argv[1:])
active = json.load(sys.stdin).get("data", {}).get("activeTargets", [])
healthy = {
    item.get("labels", {}).get("job")
    for item in active
    if item.get("health") == "up"
}
if not required <= healthy:
    raise SystemExit("Retail Prometheus targets are not all UP")
' unihub-retail-web unihub-retail-operations unihub-retail-imports \
  unihub-retail-grile unihub-retail-exports <<<"$targets"

for path in /metrics /docs /redoc /openapi.json; do
  status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --max-time 10 "https://retail.unihub.ro${path}")"
  test "$status" = "404"
done

printf 'forensic remediation runtime verified: %s\n' "$EXPECTED_SHA"
