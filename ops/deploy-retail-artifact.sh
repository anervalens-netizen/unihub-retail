#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
TEST_MODE="${RETAIL_DEPLOY_TEST_MODE:-0}"
TEST_FAIL_PHASE="${RETAIL_DEPLOY_TEST_FAIL_PHASE:-}"
TEST_NOW="${RETAIL_DEPLOY_TEST_NOW:-}"
READ_ONLY_MODE=0
[[ "${1:-}" == "validate" ]] && READ_ONLY_MODE=1

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

if [[ "$TEST_MODE" == "1" ]]; then
  [[ "$EUID" -ne 0 ]] || die "test mode must never run as root"
  TEST_ROOT="${RETAIL_DEPLOY_TEST_ROOT:?RETAIL_DEPLOY_TEST_ROOT is required in test mode}"
  LIVE_ROOT="$TEST_ROOT/live"
  OPS_ROOT="$TEST_ROOT/ops"
  SERVICE_USER="$(id -un)"
  SERVICE_GROUP="$(id -gn)"
  LOCK_FILE="$TEST_ROOT/deploy.lock"
elif [[ "$READ_ONLY_MODE" == "1" ]]; then
  [[ -z "${RETAIL_DEPLOY_TEST_ROOT:-}" ]] || die "test root is forbidden outside test mode"
  [[ -z "$TEST_FAIL_PHASE" ]] || die "failure injection is forbidden outside test mode"
  [[ -z "$TEST_NOW" ]] || die "test time is forbidden outside test mode"
  LIVE_ROOT="/opt/Mobiup/unihub-retail"
  OPS_ROOT="/opt/Mobiup/ops"
  SERVICE_USER="$(stat -c %U "$LIVE_ROOT")"
  SERVICE_GROUP="$(stat -c %G "$LIVE_ROOT")"
  LOCK_FILE="${TMPDIR:-/tmp}/unihub-retail-deploy-validate.$(id -u).lock"
else
  [[ "$EUID" -eq 0 ]] || die "production deployment requires root"
  [[ -z "${RETAIL_DEPLOY_TEST_ROOT:-}" ]] || die "test root is forbidden in production mode"
  [[ -z "$TEST_FAIL_PHASE" ]] || die "failure injection is forbidden in production mode"
  [[ -z "$TEST_NOW" ]] || die "test time is forbidden in production mode"
  LIVE_ROOT="/opt/Mobiup/unihub-retail"
  OPS_ROOT="/opt/Mobiup/ops"
  SERVICE_USER="andrei"
  SERVICE_GROUP="andrei"
  LOCK_FILE="/run/lock/unihub-retail-deploy/deploy.lock"
fi

BACKUP_ROOT="$OPS_ROOT/backups/retail-deploy"
if [[ "$TEST_MODE" == "1" ]]; then
  APPROVAL_ROOT="$TEST_ROOT/approval-store"
else
  APPROVAL_ROOT="/var/lib/unihub-retail-deploy/approvals"
fi
BACKUP_COMMAND="$OPS_ROOT/scripts/backup.sh"
MIGRATION_SERVICE="unihub-retail-migrate.service"
BACKEND_SERVICE="unihub-backend.service"
WORKER_SERVICE="unihub-worker.service"
IMPORT_WORKER_SERVICE="unihub-import-worker.service"
GRILE_WORKER_SERVICE="unihub-grile-worker.service"
EXPORT_WORKER_SERVICE="unihub-export-worker.service"
LEGACY_WORKER_SERVICE="unihub-legacy-worker.service"
if [[ "$TEST_MODE" == "1" ]]; then
  SYSTEMD_ROOT="$TEST_ROOT/etc/systemd/system"
  PROMETHEUS_HOST_CONFIG="$TEST_ROOT/prometheus/prometheus.yml"
  PROMETHEUS_RULES_ROOT="$OPS_ROOT/prometheus/rules"
  NODE_EXPORTER_TEXTFILE_ROOT="$TEST_ROOT/node-exporter/textfile"
  RUNTIME_RELEASE_BASE="$TEST_ROOT/runtime-releases"
else
  SYSTEMD_ROOT="/etc/systemd/system"
  PROMETHEUS_HOST_CONFIG="/opt/Mobiup/infra/observability/prometheus/prometheus.yml"
  PROMETHEUS_RULES_ROOT="/opt/Mobiup/infra/observability/prometheus/rules"
  NODE_EXPORTER_TEXTFILE_ROOT="/opt/Mobiup/infra/observability/node-exporter/textfile"
  RUNTIME_RELEASE_BASE="/var/lib/unihub-retail-deploy/runtime-releases"
fi
PROMETHEUS_CONTAINER="unihub-prometheus"
PROMETHEUS_CONTAINER_CONFIG="/etc/prometheus/prometheus.yml"
PROMETHEUS_CONTAINER_SCRAPE_ROOT="/etc/prometheus/scrape.d"
PROMETHEUS_SCRAPE_ROOT="$OPS_ROOT/prometheus/scrape.d"
PROMETHEUS_FRAGMENT="$PROMETHEUS_SCRAPE_ROOT/unihub-retail.yml"
PROMETHEUS_NETWORK_ENV="$OPS_ROOT/prometheus/unihub-retail-network.env"
PROMETHEUS_RETAIL_RULES="$PROMETHEUS_RULES_ROOT/retail-slo-rules.yml"
DEPLOYMENT_METRIC_FILE="$NODE_EXPORTER_TEXTFILE_ROOT/unihub_retail_deploy.prom"
if [[ "$TEST_MODE" != "1" && "${SUDO_USER:-}" == "unihub-deploy" ]]; then
  [[ "$READ_ONLY_MODE" == "0" && "$#" -eq 4 && "$1" == /* ]] \
    || die "deploy runner may invoke only the four-argument production deployment"
fi

if [[ "$TEST_MODE" != "1" && "$READ_ONLY_MODE" == "0" ]]; then
  install -d -m 0700 -o root -g root "$(dirname "$LOCK_FILE")"
  [[ "$(stat -c '%u:%g:%a' "$(dirname "$LOCK_FILE")")" == "0:0:700" ]] \
    || die "deploy lock directory must be root:root mode 0700"
else
  mkdir -p "$(dirname "$LOCK_FILE")"
fi
exec 9>"$LOCK_FILE"
if [[ "$TEST_MODE" != "1" && "$READ_ONLY_MODE" == "0" ]]; then
  chmod 0600 "$LOCK_FILE"
  [[ "$(stat -c '%u:%g:%a' "$LOCK_FILE")" == "0:0:600" ]] \
    || die "deploy lock file must be root:root mode 0600"
fi
flock -n 9 || die "another Retail deployment is active"

run_as_service_user() {
  if [[ "$TEST_MODE" == "1" || "$(id -un)" == "$SERVICE_USER" ]]; then
    "$@"
  else
    sudo --non-interactive -u "$SERVICE_USER" -- "$@"
  fi
}

service_action() {
  local action="$1"
  shift
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST systemctl $action $*"
  else
    systemctl "$action" "$@"
  fi
}

runtime_service_names() {
  printf '%s\n' \
    "$BACKEND_SERVICE" \
    "$WORKER_SERVICE" \
    "$IMPORT_WORKER_SERVICE" \
    "$GRILE_WORKER_SERVICE" \
    "$EXPORT_WORKER_SERVICE"
}

managed_runtime_service_names() {
  runtime_service_names
  printf '%s\n' \
    "$LEGACY_WORKER_SERVICE"
}

runtime_services_expected_active() {
  runtime_service_names
  if service_exists "$LEGACY_WORKER_SERVICE" && service_is_enabled "$LEGACY_WORKER_SERVICE"; then
    printf '%s\n' "$LEGACY_WORKER_SERVICE"
  fi
}

service_exists() {
  local unit="$1"
  if [[ "$TEST_MODE" == "1" ]]; then
    [[ -e "$SYSTEMD_ROOT/$unit" || -L "$SYSTEMD_ROOT/$unit" ]]
  else
    systemctl cat "$unit" >/dev/null 2>&1
  fi
}

service_is_enabled() {
  local unit="$1"
  if [[ "$TEST_MODE" == "1" ]]; then
    [[ -e "$TEST_ROOT/enabled/$unit" ]]
  else
    systemctl is-enabled --quiet "$unit"
  fi
}

set_service_enabled() {
  local unit="$1"
  if [[ "$TEST_MODE" == "1" ]]; then
    mkdir -p "$TEST_ROOT/enabled"
    : >"$TEST_ROOT/enabled/$unit"
  else
    systemctl enable "$unit"
  fi
}

set_service_disabled() {
  local unit="$1"
  if [[ "$TEST_MODE" == "1" ]]; then
    rm -f -- "$TEST_ROOT/enabled/$unit"
  else
    systemctl disable "$unit"
  fi
}

mark_planned_deployment() {
  local temporary="${DEPLOYMENT_METRIC_FILE}.new.$$"
  mkdir -p "$NODE_EXPORTER_TEXTFILE_ROOT"
  {
    printf '# HELP unihub_retail_deployment_in_progress Exact-SHA Retail deployment marker.\n'
    printf '# TYPE unihub_retail_deployment_in_progress gauge\n'
    printf 'unihub_retail_deployment_in_progress 1\n'
    printf '# HELP unihub_retail_deployment_started_timestamp_seconds Retail deployment start time.\n'
    printf '# TYPE unihub_retail_deployment_started_timestamp_seconds gauge\n'
    printf 'unihub_retail_deployment_started_timestamp_seconds %s\n' "$(current_epoch)"
  } >"$temporary"
  chmod 0644 "$temporary"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$temporary"
  fi
  mv -f -- "$temporary" "$DEPLOYMENT_METRIC_FILE"
}

clear_planned_deployment() {
  rm -f -- "$DEPLOYMENT_METRIC_FILE" "${DEPLOYMENT_METRIC_FILE}.new.$$"
}

wait_for_planned_deployment_inhibition() {
  if [[ "$TEST_MODE" == "1" ]]; then
    [[ -s "$DEPLOYMENT_METRIC_FILE" ]]
    return
  fi

  local attempt payload
  for attempt in {1..45}; do
    payload="$(curl --silent --show-error --fail --max-time 5 \
      http://127.0.0.1:9093/api/v2/alerts)" || payload=""
    if python3 -c '
import json
import sys

alerts = json.load(sys.stdin)
if not any(
    item.get("labels", {}).get("alertname") == "UniHubRetailPlannedDeployment"
    and item.get("status", {}).get("state") == "active"
    for item in alerts
):
    raise SystemExit(1)
' <<<"$payload"
    then
      return 0
    fi
    sleep 1
  done
  return 1
}

enable_runtime_services() {
  local unit
  while IFS= read -r unit; do
    service_exists "$unit" || die "runtime service is unavailable after installation: $unit"
    set_service_enabled "$unit"
  done < <(runtime_service_names)
}

set_service_ownership() {
  if [[ "$TEST_MODE" != "1" ]]; then
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$@"
  fi
}

ensure_backup_root() {
  if [[ "$TEST_MODE" == "1" ]]; then
    mkdir -p "$BACKUP_ROOT"
    chmod 0700 "$BACKUP_ROOT"
    return
  fi

  install -d -m 0700 -o root -g root "$BACKUP_ROOT"
  [[ "$(stat -c '%u:%g:%a' "$BACKUP_ROOT")" == "0:0:700" ]] \
    || die "Retail deployment backup root must be root:root mode 0700"
}

validate_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "source SHA must be exactly 40 lowercase hex characters"
}

validate_ci_run_id() {
  [[ "$1" =~ ^[1-9][0-9]{0,19}$ ]] || die "CI run ID must be a positive integer"
}

validate_sha256() {
  [[ "$1" =~ ^[0-9a-f]{64}$ ]] || die "SHA-256 must be exactly 64 lowercase hex characters"
}

current_epoch() {
  if [[ "$TEST_MODE" == "1" && -n "$TEST_NOW" ]]; then
    [[ "$TEST_NOW" =~ ^[0-9]{1,12}$ ]] || die "test timestamp is invalid"
    printf '%s\n' "$TEST_NOW"
  else
    date +%s
  fi
}

validate_artifact_archive() {
  local archive="$1"
  python3 - "$archive" <<'PY'
import pathlib
import sys
import tarfile

archive = pathlib.Path(sys.argv[1])
seen: set[str] = set()
total_size = 0
member_count = 0

with tarfile.open(archive, mode="r:gz") as bundle:
    for member in bundle.getmembers():
        member_count += 1
        if member_count > 10_000:
            raise SystemExit("archive contains too many members")
        name = member.name
        path = pathlib.PurePosixPath(name)
        if not name or path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"unsafe archive path: {name!r}")
        normalized = path.as_posix().removeprefix("./")
        if not normalized or normalized in seen:
            raise SystemExit(f"duplicate archive path: {name!r}")
        seen.add(normalized)
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"unsupported archive member type: {name!r}")
        if member.isfile():
            total_size += member.size
            if total_size > 1_073_741_824:
                raise SystemExit("archive expands beyond the 1 GiB safety limit")

required = {
    "package.json",
    "backend/main.py",
    "dist/index.html",
    "unihub-worker.service",
    "ops/systemd/unihub-backend.service",
    "ops/systemd/unihub-import-worker.service",
    "ops/systemd/unihub-grile-worker.service",
    "ops/systemd/unihub-export-worker.service",
    "ops/systemd/unihub-legacy-worker.service",
    "ops/systemd/unihub-retail-migrate.service",
    "ops/observability/retail-process-scrape.yml",
    "ops/observability/retail-slo-rules.yml",
}
missing = sorted(required - seen)
if missing:
    raise SystemExit("archive is missing required paths: " + ", ".join(missing))
PY
}

git_service() {
  run_as_service_user git -C "$LIVE_ROOT" "$@"
}

assert_live_checkout() {
  [[ -d "$LIVE_ROOT/.git" || -f "$LIVE_ROOT/.git" ]] || die "Retail live root is not a Git checkout"
  [[ "$(git_service rev-parse --show-toplevel)" == "$LIVE_ROOT" ]] || die "unexpected Retail Git root"
  [[ "$(git_service branch --show-current)" == "main" ]] || die "production checkout is not on main"
}

assert_worktree_safe() {
  local line

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    die "production worktree is not clean: $line"
  done < <(git_service status --porcelain=v1 --untracked-files=all)
}

fetch_and_verify_commit() {
  local expected_sha="$1"
  git_service fetch --quiet --prune origin main
  [[ "$(git_service rev-parse origin/main)" == "$expected_sha" ]] || die "expected SHA is not current origin/main"
  git_service cat-file -e "$expected_sha^{commit}"
  local current_sha
  current_sha="$(git_service rev-parse HEAD)"
  git_service merge-base --is-ancestor "$current_sha" "$expected_sha" || die "deployment is not a fast-forward"
}

assert_rollback_migration_compatible() {
  local current_sha="$1"
  local target_sha="$2"
  local work_dir current_manifest target_manifest current_present=0 target_present=0

  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-rollback-manifest.XXXXXX")"
  current_manifest="$work_dir/current.json"
  target_manifest="$work_dir/target.json"
  if git_service show "$current_sha:backend/db/migrations/manifest.json" \
    >"$current_manifest" 2>/dev/null; then
    current_present=1
  fi
  if git_service show "$target_sha:backend/db/migrations/manifest.json" \
    >"$target_manifest" 2>/dev/null; then
    target_present=1
  fi

  if [[ "$current_present" == "0" && "$target_present" == "0" ]]; then
    rm -rf -- "$work_dir"
    return 0
  fi
  if [[ "$current_present" != "1" || "$target_present" != "1" ]]; then
    rm -rf -- "$work_dir"
    die "rollback target has a different migration manifest; use a schema-compatible target or reviewed roll-forward"
  fi

  if ! python3 - "$current_manifest" "$target_manifest" <<'PY'
import json
import re
import sys
from pathlib import Path


def load(path: str) -> dict[str, object]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    baseline = payload.get("baseline")
    migrations = payload.get("migrations")
    if (
        payload.get("version") != 1
        or not isinstance(baseline, dict)
        or not isinstance(migrations, dict)
        or not migrations
        or any(
            not isinstance(name, str)
            or not isinstance(checksum, str)
            or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
            for name, checksum in migrations.items()
        )
    ):
        raise ValueError("invalid migration manifest")
    return payload


try:
    current = load(sys.argv[1])
    target = load(sys.argv[2])
except (OSError, ValueError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid rollback migration manifest: {exc}") from exc

if current != target:
    raise SystemExit("rollback migration manifest differs from the deployed release")
PY
  then
    rm -rf -- "$work_dir"
    die "rollback target has a different migration manifest; use a schema-compatible target or reviewed roll-forward"
  fi
  rm -rf -- "$work_dir"
}

copy_and_verify_artifact() {
  local source_archive="$1"
  local expected_sha="$2"
  local expected_artifact_sha256="$3"
  local work_dir="$4"
  local archive_copy="$work_dir/release.tar.gz"
  local artifact_tree="$work_dir/artifact"
  local tested_dist="$work_dir/tested-dist"
  local git_tree="$work_dir/git-tree"
  local bundle_dir
  bundle_dir="$(dirname -- "$source_archive")"

  python3 - "$bundle_dir" "$(basename -- "$source_archive")" "$expected_sha" "$expected_artifact_sha256" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
archive_name, expected_sha, expected_digest = sys.argv[2:]
required = {"SOURCE_SHA", "SHA256SUMS", "SBOM.cdx.json", "PROVENANCE.json", "RELEASE_MANIFEST.json", archive_name}
for name in required:
    path = root / name
    if not path.is_file() or path.is_symlink():
        raise SystemExit(f"release evidence is missing or unsafe: {name}")
if (root / "SOURCE_SHA").read_text(encoding="utf-8").strip() != expected_sha:
    raise SystemExit("release evidence SOURCE_SHA mismatch")
manifest = json.loads((root / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
if manifest.get("schemaVersion") != 1 or manifest.get("sourceSha") != expected_sha or manifest.get("archive") != archive_name:
    raise SystemExit("release manifest identity mismatch")
if manifest.get("sha256", {}).get(archive_name) != expected_digest:
    raise SystemExit("release manifest artifact digest mismatch")
provenance = json.loads((root / "PROVENANCE.json").read_text(encoding="utf-8"))
subjects = provenance.get("subject", [])
if len(subjects) != 1 or subjects[0].get("name") != archive_name or subjects[0].get("digest", {}).get("sha256") != expected_digest:
    raise SystemExit("release provenance subject mismatch")
sbom = json.loads((root / "SBOM.cdx.json").read_text(encoding="utf-8"))
if sbom.get("bomFormat") != "CycloneDX" or sbom.get("metadata", {}).get("component", {}).get("version") != expected_sha:
    raise SystemExit("release SBOM identity mismatch")
seen = set()
for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    digest, name = line.split(maxsplit=1)
    name = name.lstrip("*")
    if name in seen or name not in required or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise SystemExit(f"release evidence digest mismatch: {name}")
    seen.add(name)
if seen != required - {"SHA256SUMS"}:
    raise SystemExit("release evidence checksum inventory mismatch")
PY

  [[ -f "$source_archive" && ! -L "$source_archive" ]] || die "artifact must be a regular non-symlink file"
  local compressed_size
  compressed_size="$(stat -c %s "$source_archive")"
  [[ "$compressed_size" =~ ^[0-9]+$ && "$compressed_size" -gt 0 && "$compressed_size" -le 268435456 ]] \
    || die "artifact compressed size is outside the 1 byte to 256 MiB safety range"
  install -m 0400 -- "$source_archive" "$archive_copy"
  [[ "$(sha256sum "$archive_copy" | awk '{print $1}')" == "$expected_artifact_sha256" ]] \
    || die "artifact SHA-256 differs from the approved digest"
  validate_artifact_archive "$archive_copy"
  mkdir -p "$artifact_tree" "$git_tree"
  tar -xzf "$archive_copy" --no-same-owner --no-same-permissions -C "$artifact_tree"
  run_as_service_user git -C "$LIVE_ROOT" archive --format=tar "$expected_sha" >"$work_dir/git-tree.tar"
  tar -xf "$work_dir/git-tree.tar" --no-same-owner --no-same-permissions -C "$git_tree"
  mv -- "$artifact_tree/dist" "$tested_dist"
  diff -qr "$git_tree" "$artifact_tree" >/dev/null || die "artifact source differs from the approved Git commit"
  mv -- "$tested_dist" "$artifact_tree/dist"
  [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
    && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
  printf '%s\n' "$artifact_tree"
}

PROMETHEUS_NETWORK_NAME=""
PROMETHEUS_DOCKER_GATEWAY=""
PROMETHEUS_DOCKER_SUBNET=""

validate_prometheus_network_values() {
  local gateway="$1"
  local subnet="$2"
  python3 - "$gateway" "$subnet" <<'PY'
import ipaddress
import sys

gateway = ipaddress.ip_address(sys.argv[1])
subnet = ipaddress.ip_network(sys.argv[2], strict=True)
if (
    not isinstance(gateway, ipaddress.IPv4Address)
    or not isinstance(subnet, ipaddress.IPv4Network)
    or gateway.is_unspecified
    or gateway.is_loopback
    or gateway.is_multicast
    or not gateway.is_private
    or gateway not in subnet
):
    raise SystemExit("Prometheus Docker gateway/subnet is not a private IPv4 bridge")
PY
}

detect_prometheus_network() {
  if [[ "$TEST_MODE" == "1" ]]; then
    PROMETHEUS_NETWORK_NAME="retail-test-net"
    PROMETHEUS_DOCKER_GATEWAY="${RETAIL_DEPLOY_TEST_PROMETHEUS_GATEWAY:-172.23.0.1}"
    PROMETHEUS_DOCKER_SUBNET="${RETAIL_DEPLOY_TEST_PROMETHEUS_SUBNET:-172.23.0.0/16}"
  else
    local inspect_json network_json
    inspect_json="$(docker inspect "$PROMETHEUS_CONTAINER")" \
      || die "Prometheus container is unavailable"
    mapfile -t network_values < <(
      python3 -c '
import json, sys
payload = json.load(sys.stdin)
if len(payload) != 1 or not payload[0].get("State", {}).get("Running"):
    raise SystemExit("Prometheus container is not running")
if payload[0].get("HostConfig", {}).get("NetworkMode") == "host":
    raise SystemExit("Prometheus must remain in Docker bridge mode")
networks = payload[0].get("NetworkSettings", {}).get("Networks", {})
if len(networks) != 1:
    raise SystemExit("Prometheus must have exactly one Docker bridge network")
name, details = next(iter(networks.items()))
if not details.get("IPAddress"):
    raise SystemExit("Prometheus bridge has no IPv4 address")
print(name)
' <<<"$inspect_json"
    )
    [[ "${#network_values[@]}" -eq 1 ]] || die "unable to resolve the Prometheus Docker network"
    PROMETHEUS_NETWORK_NAME="${network_values[0]}"
    network_json="$(docker network inspect "$PROMETHEUS_NETWORK_NAME")" \
      || die "unable to inspect the Prometheus Docker network"
    mapfile -t network_values < <(
      python3 -c '
import ipaddress, json, sys
payload = json.load(sys.stdin)
if len(payload) != 1:
    raise SystemExit("invalid Docker network inspection")
configs = payload[0].get("IPAM", {}).get("Config", [])
ipv4 = []
for item in configs:
    subnet = item.get("Subnet", "")
    gateway = item.get("Gateway", "")
    try:
        parsed = ipaddress.ip_network(subnet, strict=True)
        parsed_gateway = ipaddress.ip_address(gateway)
    except ValueError:
        continue
    if isinstance(parsed, ipaddress.IPv4Network) and isinstance(parsed_gateway, ipaddress.IPv4Address):
        ipv4.append((str(parsed_gateway), str(parsed)))
if len(ipv4) != 1:
    raise SystemExit("Prometheus network must expose exactly one IPv4 gateway/subnet")
print(ipv4[0][0])
print(ipv4[0][1])
' <<<"$network_json"
    )
    [[ "${#network_values[@]}" -eq 2 ]] || die "unable to resolve the Prometheus bridge gateway/subnet"
    PROMETHEUS_DOCKER_GATEWAY="${network_values[0]}"
    PROMETHEUS_DOCKER_SUBNET="${network_values[1]}"
  fi
  validate_prometheus_network_values "$PROMETHEUS_DOCKER_GATEWAY" "$PROMETHEUS_DOCKER_SUBNET"
  log "Prometheus bridge validated: network=$PROMETHEUS_NETWORK_NAME gateway=$PROMETHEUS_DOCKER_GATEWAY subnet=$PROMETHEUS_DOCKER_SUBNET"
}

assert_prometheus_shared_include() {
  [[ -f "$PROMETHEUS_HOST_CONFIG" && ! -L "$PROMETHEUS_HOST_CONFIG" ]] \
    || die "shared Prometheus config is unavailable"
  [[ -d "$PROMETHEUS_SCRAPE_ROOT" && ! -L "$PROMETHEUS_SCRAPE_ROOT" ]] \
    || die "shared Prometheus scrape include directory is unavailable"
  python3 - "$PROMETHEUS_HOST_CONFIG" "$PROMETHEUS_CONTAINER_SCRAPE_ROOT/*.yml" <<'PY'
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
pattern = re.compile(
    r"(?m)^scrape_config_files:\s*$\n(?:^[ \t]+.*\n)*?^[ \t]*-[ \t]*[\"']?"
    + re.escape(sys.argv[2])
    + r"[\"']?[ \t]*$"
)
if pattern.search(text) is None:
    raise SystemExit("shared Prometheus config is missing the Retail scrape include")
if re.search(r"(?m)^\s*-?\s*job_name:\s*[\"']?unihub_retail[\"']?\s*$", text):
    raise SystemExit("shared Prometheus config still contains the legacy Retail scrape job")
PY
  if [[ "$TEST_MODE" == "1" ]]; then
    [[ -f "$TEST_ROOT/prometheus/scrape-mount-ready" ]] \
      || die "test Prometheus scrape mount marker is missing"
    return
  fi
  [[ "$(stat -c '%u:%g:%a' "$(dirname "$PROMETHEUS_SCRAPE_ROOT")")" == "0:0:755" ]] \
    || die "Prometheus host include parent must be root:root mode 0755"
  [[ "$(stat -c '%u:%g:%a' "$PROMETHEUS_SCRAPE_ROOT")" == "0:0:755" ]] \
    || die "Prometheus host include directory must be root:root mode 0755"
  local inspect_json
  inspect_json="$(docker inspect "$PROMETHEUS_CONTAINER")"
  python3 -c '
import json
import pathlib
import sys

payload = json.load(sys.stdin)
mounts = payload[0].get("Mounts", [])

def require_mount(source: str, destination: str) -> None:
    expected = pathlib.Path(source).resolve()
    matches = [item for item in mounts if item.get("Destination") == destination]
    if len(matches) != 1:
        raise SystemExit(f"missing unique Prometheus mount for {destination}")
    item = matches[0]
    if pathlib.Path(item.get("Source", "")).resolve() != expected or item.get("RW") is not False:
        raise SystemExit(f"Prometheus mount for {destination} must be exact and read-only")

require_mount(sys.argv[1], sys.argv[2])
require_mount(sys.argv[3], sys.argv[4])
' "$PROMETHEUS_HOST_CONFIG" "$PROMETHEUS_CONTAINER_CONFIG" \
    "$PROMETHEUS_SCRAPE_ROOT" "$PROMETHEUS_CONTAINER_SCRAPE_ROOT" \
    <<<"$inspect_json"
}

prepare_runtime_release() {
  local artifact_tree="$1"
  local stage_root="$2"
  local unit_source
  rm -rf -- "$stage_root"
  mkdir -p "$stage_root/systemd"
  local -a unit_sources=(
    "ops/systemd/unihub-backend.service"
    "unihub-worker.service"
    "ops/systemd/unihub-import-worker.service"
    "ops/systemd/unihub-grile-worker.service"
    "ops/systemd/unihub-export-worker.service"
    "ops/systemd/unihub-legacy-worker.service"
    "ops/systemd/unihub-retail-migrate.service"
  )
  for unit_source in "${unit_sources[@]}"; do
    [[ -f "$artifact_tree/$unit_source" && ! -L "$artifact_tree/$unit_source" ]] \
      || die "runtime artifact unit is missing: $unit_source"
    install -m 0644 -- "$artifact_tree/$unit_source" "$stage_root/systemd/$(basename "$unit_source")"
  done
  local worker_unit
  for worker_unit in unihub-worker.service unihub-import-worker.service unihub-grile-worker.service unihub-export-worker.service; do
    grep -Fq 'EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env' \
      "$stage_root/systemd/$worker_unit" \
      || die "worker unit is missing the Prometheus network environment"
    if grep -Eq 'WORKER_METRICS_HOST=(0\.0\.0\.0|127\.0\.0\.1|::1)' "$stage_root/systemd/$worker_unit"; then
      die "worker metrics unit contains a forbidden bind address"
    fi
  done
  grep -Fq 'EnvironmentFile=/opt/Mobiup/ops/prometheus/unihub-retail-network.env' \
    "$stage_root/systemd/unihub-backend.service" \
    || die "backend unit is missing the Prometheus network environment"
  if [[ "$TEST_MODE" != "1" ]]; then
    systemd-analyze verify \
      "$stage_root/systemd/unihub-backend.service" \
      "$stage_root/systemd/unihub-worker.service" \
      "$stage_root/systemd/unihub-import-worker.service" \
      "$stage_root/systemd/unihub-grile-worker.service" \
      "$stage_root/systemd/unihub-export-worker.service" \
      "$stage_root/systemd/unihub-legacy-worker.service" \
      "$stage_root/systemd/unihub-retail-migrate.service"
  fi
  {
    printf 'PROMETHEUS_DOCKER_GATEWAY=%s\n' "$PROMETHEUS_DOCKER_GATEWAY"
    printf 'PROMETHEUS_DOCKER_SUBNET=%s\n' "$PROMETHEUS_DOCKER_SUBNET"
    printf 'WORKER_METRICS_HOST=%s\n' "$PROMETHEUS_DOCKER_GATEWAY"
  } >"$stage_root/unihub-retail-network.env"
  chmod 0644 "$stage_root/unihub-retail-network.env"

  local fragment_source="$artifact_tree/ops/observability/retail-process-scrape.yml"
  [[ -f "$fragment_source" && ! -L "$fragment_source" ]] \
    || die "Retail Prometheus scrape template is missing"
  python3 - "$fragment_source" "$stage_root/unihub-retail.yml" "$PROMETHEUS_DOCKER_GATEWAY" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
token = "__PROMETHEUS_DOCKER_GATEWAY__"
if source.count(token) != 5:
    raise SystemExit("Retail scrape template must contain exactly five gateway placeholders")
rendered = source.replace(token, sys.argv[3])
if token in rendered or "0.0.0.0" in rendered or "127.0.0.1" in rendered:
    raise SystemExit("Retail scrape fragment contains a forbidden target")
Path(sys.argv[2]).write_text(rendered, encoding="utf-8")
PY
  chmod 0644 "$stage_root/unihub-retail.yml"

  local rules_source="$artifact_tree/ops/observability/retail-slo-rules.yml"
  [[ -f "$rules_source" && ! -L "$rules_source" ]] \
    || die "Retail Prometheus rules are missing"
  install -m 0644 -- "$rules_source" "$stage_root/retail-slo-rules.yml"
  grep -Fq 'job="unihub-retail-web"' "$stage_root/retail-slo-rules.yml" \
    || die "Retail Prometheus rules do not use the live web scrape job"
  ! grep -Fq 'job="unihub_retail"' "$stage_root/retail-slo-rules.yml" \
    || die "Retail Prometheus rules still use the retired scrape job"
  grep -Fq 'alert: UniHubRetailPlannedDeployment' "$stage_root/retail-slo-rules.yml" \
    || die "Retail Prometheus rules are missing the planned deployment marker"
}

runtime_asset_destinations() {
  printf '%s\n' \
    "$SYSTEMD_ROOT/unihub-backend.service" \
    "$SYSTEMD_ROOT/unihub-worker.service" \
    "$SYSTEMD_ROOT/unihub-import-worker.service" \
    "$SYSTEMD_ROOT/unihub-grile-worker.service" \
    "$SYSTEMD_ROOT/unihub-export-worker.service" \
    "$SYSTEMD_ROOT/unihub-legacy-worker.service" \
    "$SYSTEMD_ROOT/unihub-retail-migrate.service" \
    "$PROMETHEUS_NETWORK_ENV" \
    "$PROMETHEUS_FRAGMENT" \
    "$PROMETHEUS_RETAIL_RULES"
}

backup_runtime_assets() {
  local backup_dir="$1"
  local assets_dir="$backup_dir/runtime-assets"
  local destination name
  mkdir -p "$assets_dir/files"
  : >"$assets_dir/state.env"
  : >"$assets_dir/enabled.env"
  while IFS= read -r destination; do
    name="$(basename "$destination")"
    if [[ -e "$destination" || -L "$destination" ]]; then
      printf '%s=1\n' "$name" >>"$assets_dir/state.env"
      cp -a --no-dereference -- "$destination" "$assets_dir/files/$name"
    else
      printf '%s=0\n' "$name" >>"$assets_dir/state.env"
    fi
  done < <(runtime_asset_destinations)
  while IFS= read -r name; do
    if service_is_enabled "$name"; then
      printf '%s=1\n' "$name" >>"$assets_dir/enabled.env"
    else
      printf '%s=0\n' "$name" >>"$assets_dir/enabled.env"
    fi
  done < <(managed_runtime_service_names)
  chmod 0600 "$assets_dir/state.env"
  chmod 0600 "$assets_dir/enabled.env"
}

atomic_symlink() {
  local target="$1"
  local destination="$2"
  local temporary="${destination}.new.$$"
  ln -s -- "$target" "$temporary"
  mv -Tf -- "$temporary" "$destination"
}

assert_runtime_release_security() {
  local release_root="$1"
  [[ -d "$release_root" && ! -L "$release_root" ]] \
    || die "versioned runtime release is unavailable"
  if [[ "$TEST_MODE" == "1" ]]; then
    return
  fi
  [[ "$(stat -c '%u:%g:%a' "$RUNTIME_RELEASE_BASE")" == "0:0:755" ]] \
    || die "versioned runtime release root must be root:root mode 0755"
  local unsafe
  unsafe="$(find "$release_root" \( ! -user root -o ! -group root -o -type l \) -print -quit)"
  [[ -z "$unsafe" ]] || die "versioned runtime release contains an unsafe path"
}

install_runtime_assets() {
  local stage_root="$1"
  local expected_sha="$2"
  local release_root="$RUNTIME_RELEASE_BASE/$expected_sha"
  local release_tmp="$RUNTIME_RELEASE_BASE/.${expected_sha}.new.$$"
  if [[ -d "$release_root" && ! -L "$release_root" ]]; then
    diff -qr -- "$stage_root" "$release_root" >/dev/null \
      || die "existing versioned runtime release differs from the approved artifact"
  else
    [[ ! -e "$release_root" && ! -L "$release_root" ]] \
      || die "versioned runtime release path is invalid"
    if [[ "$TEST_MODE" == "1" ]]; then
      mkdir -p "$RUNTIME_RELEASE_BASE"
    else
      install -d -m 0755 -o root -g root "$RUNTIME_RELEASE_BASE"
      [[ "$(stat -c '%u:%g:%a' "$RUNTIME_RELEASE_BASE")" == "0:0:755" ]] \
        || die "versioned runtime release root must be root:root mode 0755"
    fi
    rm -rf -- "$release_tmp"
    cp -a -- "$stage_root" "$release_tmp"
    if [[ "$TEST_MODE" != "1" ]]; then
      chown -R root:root "$release_tmp"
    fi
    find "$release_tmp" -type d -exec chmod 0755 {} +
    find "$release_tmp" -type f -exec chmod 0644 {} +
    mv -- "$release_tmp" "$release_root"
  fi
  assert_runtime_release_security "$release_root"
  mkdir -p "$SYSTEMD_ROOT" "$(dirname "$PROMETHEUS_NETWORK_ENV")" "$PROMETHEUS_SCRAPE_ROOT"
  atomic_symlink "$release_root/systemd/unihub-backend.service" "$SYSTEMD_ROOT/unihub-backend.service"
  atomic_symlink "$release_root/systemd/unihub-worker.service" "$SYSTEMD_ROOT/unihub-worker.service"
  atomic_symlink "$release_root/systemd/unihub-import-worker.service" "$SYSTEMD_ROOT/unihub-import-worker.service"
  atomic_symlink "$release_root/systemd/unihub-grile-worker.service" "$SYSTEMD_ROOT/unihub-grile-worker.service"
  atomic_symlink "$release_root/systemd/unihub-export-worker.service" "$SYSTEMD_ROOT/unihub-export-worker.service"
  atomic_symlink "$release_root/systemd/unihub-legacy-worker.service" "$SYSTEMD_ROOT/unihub-legacy-worker.service"
  atomic_symlink "$release_root/systemd/unihub-retail-migrate.service" "$SYSTEMD_ROOT/unihub-retail-migrate.service"
  local network_env_tmp="${PROMETHEUS_NETWORK_ENV}.new.$$"
  install -m 0644 -- "$release_root/unihub-retail-network.env" "$network_env_tmp"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$network_env_tmp"
  fi
  mv -f -- "$network_env_tmp" "$PROMETHEUS_NETWORK_ENV"
  local fragment_tmp="${PROMETHEUS_FRAGMENT}.new.$$"
  install -m 0644 -- "$release_root/unihub-retail.yml" "$fragment_tmp"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$fragment_tmp"
  fi
  mv -f -- "$fragment_tmp" "$PROMETHEUS_FRAGMENT"
  mkdir -p "$PROMETHEUS_RULES_ROOT"
  local rules_tmp="${PROMETHEUS_RETAIL_RULES}.new.$$"
  install -m 0644 -- "$release_root/retail-slo-rules.yml" "$rules_tmp"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$rules_tmp"
  fi
  mv -f -- "$rules_tmp" "$PROMETHEUS_RETAIL_RULES"
  service_action daemon-reload
  if service_is_enabled "$LEGACY_WORKER_SERVICE"; then
    set_service_disabled "$LEGACY_WORKER_SERVICE"
  fi
  enable_runtime_services
}

restore_runtime_assets() {
  local backup_dir="$1"
  local assets_dir="$backup_dir/runtime-assets"
  [[ -f "$assets_dir/state.env" ]] || {
    log "legacy rollback handle has no runtime asset snapshot"
    return 0
  }
  local destination name existed
  while IFS= read -r destination; do
    name="$(basename "$destination")"
    existed="$(sed -n "s/^${name}=//p" "$assets_dir/state.env")"
    [[ "$existed" == "0" || "$existed" == "1" ]] \
      || die "runtime asset backup state is invalid: $name"
    rm -f -- "$destination"
    if [[ "$existed" == "1" ]]; then
      [[ -e "$assets_dir/files/$name" || -L "$assets_dir/files/$name" ]] \
        || die "runtime asset backup is missing: $name"
      cp -a --no-dereference -- "$assets_dir/files/$name" "$destination"
    fi
  done < <(runtime_asset_destinations)
  service_action daemon-reload
  if [[ -f "$assets_dir/enabled.env" ]]; then
    local enabled
    while IFS= read -r name; do
      enabled="$(sed -n "s/^${name}=//p" "$assets_dir/enabled.env")"
      [[ "$enabled" == "0" || "$enabled" == "1" ]] \
        || die "runtime service enablement backup is invalid: $name"
      if [[ "$enabled" == "1" ]] && service_exists "$name"; then
        set_service_enabled "$name"
      elif service_is_enabled "$name"; then
        set_service_disabled "$name"
      fi
    done < <(managed_runtime_service_names)
  fi
}

check_prometheus_config() {
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST Prometheus config check"
    [[ ! -e "$PROMETHEUS_FRAGMENT" ]] && return 0
    ! grep -Eq '__PROMETHEUS_DOCKER_GATEWAY__|0\.0\.0\.0|127\.0\.0\.1' "$PROMETHEUS_FRAGMENT"
    return
  fi
  docker exec "$PROMETHEUS_CONTAINER" promtool check config "$PROMETHEUS_CONTAINER_CONFIG"
}

reload_prometheus() {
  check_prometheus_config
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST Prometheus HUP"
    [[ "$TEST_FAIL_PHASE" != "prometheus" ]]
    return
  fi
  docker kill --signal HUP "$PROMETHEUS_CONTAINER" >/dev/null
}

verify_prometheus_targets() {
  if [[ "$TEST_MODE" == "1" ]]; then
    [[ -s "$PROMETHEUS_FRAGMENT" ]]
    return
  fi
  local attempt payload
  for attempt in {1..30}; do
    payload="$(curl --silent --show-error --fail --max-time 5 \
      http://127.0.0.1:9090/api/v1/targets)" || payload=""
    if python3 -c '
import json
import sys

required = set(sys.argv[1:])
payload = json.load(sys.stdin)
active = payload.get("data", {}).get("activeTargets", [])
healthy = {
    item.get("labels", {}).get("job")
    for item in active
    if item.get("health") == "up"
}
if not required <= healthy:
    raise SystemExit(1)
' unihub-retail-web unihub-retail-operations unihub-retail-imports unihub-retail-grile unihub-retail-exports <<<"$payload"
    then
      return 0
    fi
    sleep 2
  done
  return 1
}

verify_active_runtime_assets() {
  local expected_sha="$1"
  local release_root="$RUNTIME_RELEASE_BASE/$expected_sha"
  assert_runtime_release_security "$release_root"
  local destination expected
  local -a names=(
    unihub-backend.service
    unihub-worker.service
    unihub-import-worker.service
    unihub-grile-worker.service
    unihub-export-worker.service
    unihub-legacy-worker.service
    unihub-retail-migrate.service
  )
  for destination in "${names[@]}"; do
    expected="$release_root/systemd/$destination"
    [[ -L "$SYSTEMD_ROOT/$destination" && "$(readlink -f "$SYSTEMD_ROOT/$destination")" == "$expected" ]] \
      || die "active systemd unit is not the expected version: $destination"
  done
  ! service_is_enabled "$LEGACY_WORKER_SERVICE" \
    || die "retired legacy worker must stay disabled"
  if [[ "$TEST_MODE" != "1" ]]; then
    ! systemctl is-active --quiet "$LEGACY_WORKER_SERVICE" \
      || die "retired legacy worker must stay inactive"
  fi
  diff -q -- "$PROMETHEUS_NETWORK_ENV" "$release_root/unihub-retail-network.env" >/dev/null \
    || die "active Prometheus network environment differs from the expected version"
  diff -q -- "$PROMETHEUS_FRAGMENT" "$release_root/unihub-retail.yml" >/dev/null \
    || die "active Retail scrape fragment differs from the expected version"
  diff -q -- "$PROMETHEUS_RETAIL_RULES" "$release_root/retail-slo-rules.yml" >/dev/null \
    || die "active Retail Prometheus rules differ from the expected version"
  grep -Fxq "PROMETHEUS_DOCKER_GATEWAY=$PROMETHEUS_DOCKER_GATEWAY" "$PROMETHEUS_NETWORK_ENV"
  grep -Fxq "PROMETHEUS_DOCKER_SUBNET=$PROMETHEUS_DOCKER_SUBNET" "$PROMETHEUS_NETWORK_ENV"
  grep -Fxq "WORKER_METRICS_HOST=$PROMETHEUS_DOCKER_GATEWAY" "$PROMETHEUS_NETWORK_ENV"
  check_prometheus_config
  verify_prometheus_targets
}

read_approval_value() {
  local approval_file="$1"
  local key="$2"
  local value
  value="$(sed -n "s/^${key}=//p" "$approval_file")"
  [[ -n "$value" && "$value" != *$'\n'* ]] || die "approval field is missing or duplicated: $key"
  printf '%s\n' "$value"
}

APPROVAL_CLAIM=""
CLAIMED_APPROVAL_ID=""
CLAIMED_APPROVER=""

claim_approval() {
  local ci_run_id="$1"
  local source_sha="$2"
  local artifact_sha256="$3"
  local prefix="${ci_run_id}-${source_sha}-${artifact_sha256}"

  [[ -d "$APPROVAL_ROOT" && ! -L "$APPROVAL_ROOT" ]] || die "approval store is unavailable"
  if [[ "$TEST_MODE" != "1" ]]; then
    [[ "$(stat -c '%u:%g:%a' "$APPROVAL_ROOT")" == "0:0:700" ]] \
      || die "approval store must be root:root mode 0700"
  fi

  exec 8>"$APPROVAL_ROOT/.approval.lock"
  flock -x 8
  shopt -s nullglob
  local -a matches=("$APPROVAL_ROOT/${prefix}-"*.approved)
  shopt -u nullglob
  [[ "${#matches[@]}" -eq 1 ]] || die "exactly one active one-time approval is required"

  local approval_file="${matches[0]}"
  [[ -f "$approval_file" && ! -L "$approval_file" ]] || die "approval record is invalid"
  if [[ "$TEST_MODE" != "1" ]]; then
    [[ "$(stat -c '%u:%g:%a' "$approval_file")" == "0:0:600" ]] \
      || die "approval record must be root:root mode 0600"
  fi

  APPROVAL_CLAIM="${approval_file%.approved}.claimed.$$"
  mv -- "$approval_file" "$APPROVAL_CLAIM"
  flock -u 8
  exec 8>&-

  local record_run_id record_source_sha record_artifact_sha256 approval_id approver approved_at expires_at state now
  approval_id="$(read_approval_value "$APPROVAL_CLAIM" approval_id)"
  record_run_id="$(read_approval_value "$APPROVAL_CLAIM" ci_run_id)"
  record_source_sha="$(read_approval_value "$APPROVAL_CLAIM" source_sha)"
  record_artifact_sha256="$(read_approval_value "$APPROVAL_CLAIM" artifact_sha256)"
  approver="$(read_approval_value "$APPROVAL_CLAIM" approved_by_os)"
  approved_at="$(read_approval_value "$APPROVAL_CLAIM" approved_at_epoch)"
  expires_at="$(read_approval_value "$APPROVAL_CLAIM" expires_at_epoch)"
  state="$(read_approval_value "$APPROVAL_CLAIM" state)"
  now="$(current_epoch)"

  [[ "$record_run_id" == "$ci_run_id" ]] || die "approval CI run mismatch"
  [[ "$record_source_sha" == "$source_sha" ]] || die "approval source SHA mismatch"
  [[ "$record_artifact_sha256" == "$artifact_sha256" ]] || die "approval artifact SHA mismatch"
  [[ "$approval_id" == "$(basename "${APPROVAL_CLAIM%.claimed.*}")" ]] || die "approval ID mismatch"
  [[ "$approver" =~ ^[a-z_][a-z0-9_-]{0,31}$ && "$approver" != "root" && "$approver" != "unihub-deploy" ]] \
    || die "approval has an invalid human identity"
  [[ "$approved_at" =~ ^[0-9]{1,12}$ && "$expires_at" =~ ^[0-9]{1,12}$ ]] \
    || die "approval timestamps are invalid"
  [[ "$state" == "approved" ]] || die "approval is not active"
  [[ "$approved_at" -le "$now" && "$now" -lt "$expires_at" ]] || {
    local rejected_file="${APPROVAL_CLAIM%.claimed.*}.rejected"
    local rejected_tmp="${APPROVAL_CLAIM}.rejecting"
    {
      sed '/^state=/d' "$APPROVAL_CLAIM"
      printf 'state=rejected\n'
      printf 'rejected_at_epoch=%s\n' "$now"
      printf 'rejection_reason=not_currently_valid_at_claim\n'
    } >"$rejected_tmp"
    chmod 0600 "$rejected_tmp"
    mv -- "$rejected_tmp" "$rejected_file"
    rm -f -- "$APPROVAL_CLAIM"
    APPROVAL_CLAIM=""
    die "approval is not currently valid"
  }
  [[ "$((expires_at - approved_at))" -le 3600 ]] || die "approval validity window is too long"

  CLAIMED_APPROVAL_ID="$approval_id"
  CLAIMED_APPROVER="$approver"
  log "claimed one-time approval from $approver for CI run $ci_run_id"
}

write_approval_link() {
  local backup_dir="$1"
  local ci_run_id="$2"
  local source_sha="$3"
  local artifact_sha256="$4"
  [[ -n "$CLAIMED_APPROVAL_ID" && -n "$CLAIMED_APPROVER" ]] || die "approval audit identity is missing"
  local tmp_file="$backup_dir/approval.env.tmp"
  {
    printf 'approval_id=%s\n' "$CLAIMED_APPROVAL_ID"
    printf 'approved_by_os=%s\n' "$CLAIMED_APPROVER"
    printf 'ci_run_id=%s\n' "$ci_run_id"
    printf 'source_sha=%s\n' "$source_sha"
    printf 'artifact_sha256=%s\n' "$artifact_sha256"
    printf 'claimed_at_epoch=%s\n' "$(current_epoch)"
  } >"$tmp_file"
  chmod 0600 "$tmp_file"
  mv -- "$tmp_file" "$backup_dir/approval.env"
}

finalize_approval() {
  local final_state="$1"
  local backup_handle="$2"
  [[ -n "$APPROVAL_CLAIM" && -f "$APPROVAL_CLAIM" ]] || die "claimed approval record is missing"
  [[ "$final_state" == "consumed" || "$final_state" == "failed" ]] || die "invalid approval final state"
  local final_file="${APPROVAL_CLAIM%.claimed.*}.${final_state}"
  local tmp_file="${APPROVAL_CLAIM}.tmp"
  {
    sed '/^state=/d' "$APPROVAL_CLAIM"
    printf 'state=%s\n' "$final_state"
    printf 'finalized_at_epoch=%s\n' "$(current_epoch)"
    printf 'backup_handle=%s\n' "$backup_handle"
  } >"$tmp_file"
  chmod 0600 "$tmp_file"
  mv -- "$tmp_file" "$final_file"
  rm -f -- "$APPROVAL_CLAIM"
  APPROVAL_CLAIM=""
}

verify_completed_deploy_record() {
  local ci_run_id="$1"
  local source_sha="$2"
  local artifact_sha256="$3"
  local prefix="${ci_run_id}-${source_sha}-${artifact_sha256}"

  [[ -d "$APPROVAL_ROOT" && ! -L "$APPROVAL_ROOT" ]] || die "approval store is unavailable"
  if [[ "$TEST_MODE" != "1" ]]; then
    [[ "$(stat -c '%u:%g:%a' "$APPROVAL_ROOT")" == "0:0:700" ]] \
      || die "approval store must be root:root mode 0700"
  fi

  shopt -s nullglob
  local -a matches=("$APPROVAL_ROOT/${prefix}-"*.consumed)
  shopt -u nullglob
  [[ "${#matches[@]}" -ge 1 ]] || die "a consumed approval is required to reverify an existing deploy"

  local record approval_id approver backup_handle canonical_handle release_manifest approval_link
  local active_records=0
  for record in "${matches[@]}"; do
    [[ -f "$record" && ! -L "$record" ]] || die "consumed approval record is invalid"
    if [[ "$TEST_MODE" != "1" ]]; then
      [[ "$(stat -c '%u:%g:%a' "$record")" == "0:0:600" ]] \
        || die "consumed approval record must be root:root mode 0600"
    fi
    [[ "$(read_approval_value "$record" state)" == "consumed" ]] || die "completed approval state is invalid"
    [[ "$(read_approval_value "$record" ci_run_id)" == "$ci_run_id" ]] || die "completed approval CI run mismatch"
    [[ "$(read_approval_value "$record" source_sha)" == "$source_sha" ]] || die "completed approval source SHA mismatch"
    [[ "$(read_approval_value "$record" artifact_sha256)" == "$artifact_sha256" ]] || die "completed approval artifact mismatch"
    approval_id="$(read_approval_value "$record" approval_id)"
    [[ "$approval_id" == "$(basename "${record%.consumed}")" ]] || die "completed approval ID mismatch"
    approver="$(read_approval_value "$record" approved_by_os)"
    [[ "$approver" =~ ^[a-z_][a-z0-9_-]{0,31}$ && "$approver" != "root" && "$approver" != "unihub-deploy" ]] \
      || die "completed approval has an invalid human identity"

    backup_handle="$(read_approval_value "$record" backup_handle)"
    [[ -d "$backup_handle" && ! -L "$backup_handle" ]] || die "completed deploy backup handle is invalid"
    canonical_handle="$(realpath -e -- "$backup_handle")"
    [[ "$(dirname "$canonical_handle")" == "$BACKUP_ROOT" ]] || die "completed deploy backup handle is outside the backup root"
    [[ "$(basename "$canonical_handle")" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-to-[0-9a-f]{12}-[0-9a-f]{16}$ ]] \
      || die "completed deploy backup handle name is invalid"
    release_manifest="$canonical_handle/release.env"
    approval_link="$canonical_handle/approval.env"
    [[ -f "$release_manifest" && -f "$approval_link" ]] || die "completed deploy audit link is missing"
    [[ "$(read_approval_value "$release_manifest" NEW_SHA)" == "$source_sha" ]] || die "completed deploy manifest SHA mismatch"
    [[ "$(read_approval_value "$approval_link" approval_id)" == "$approval_id" ]] || die "completed deploy approval link mismatch"
    [[ "$(read_approval_value "$approval_link" ci_run_id)" == "$ci_run_id" ]] || die "completed deploy linked CI run mismatch"
    [[ "$(read_approval_value "$approval_link" source_sha)" == "$source_sha" ]] || die "completed deploy linked SHA mismatch"
    [[ "$(read_approval_value "$approval_link" artifact_sha256)" == "$artifact_sha256" ]] || die "completed deploy linked artifact mismatch"
    if [[ "$(read_approval_value "$release_manifest" STATE)" == "deployed" ]]; then
      active_records=$((active_records + 1))
    fi
  done

  [[ "$active_records" -eq 1 ]] || die "exactly one deployed audit record is required for reverification"
}

find_retryable_forward_handle() {
  local ci_run_id="$1"
  local source_sha="$2"
  local artifact_sha256="$3"
  local prefix="${ci_run_id}-${source_sha}-${artifact_sha256}"

  shopt -s nullglob
  local -a matches=("$APPROVAL_ROOT/${prefix}-"*.failed)
  shopt -u nullglob
  [[ "${#matches[@]}" -ge 1 ]] || return 1

  local record approval_id backup_handle canonical_handle release_manifest approval_link
  declare -A retryable_handles=()
  for record in "${matches[@]}"; do
    [[ -f "$record" && ! -L "$record" ]] || die "failed approval record is invalid"
    if [[ "$TEST_MODE" != "1" ]]; then
      [[ "$(stat -c '%u:%g:%a' "$record")" == "0:0:600" ]] \
        || die "failed approval record must be root:root mode 0600"
    fi
    [[ "$(read_approval_value "$record" state)" == "failed" ]] || die "failed approval state is invalid"
    [[ "$(read_approval_value "$record" ci_run_id)" == "$ci_run_id" ]] || die "failed approval CI run mismatch"
    [[ "$(read_approval_value "$record" source_sha)" == "$source_sha" ]] || die "failed approval source SHA mismatch"
    [[ "$(read_approval_value "$record" artifact_sha256)" == "$artifact_sha256" ]] || die "failed approval artifact mismatch"
    approval_id="$(read_approval_value "$record" approval_id)"
    [[ "$approval_id" == "$(basename "${record%.failed}")" ]] || die "failed approval ID mismatch"

    backup_handle="$(read_approval_value "$record" backup_handle)"
    [[ -d "$backup_handle" && ! -L "$backup_handle" ]] || die "failed deploy backup handle is invalid"
    canonical_handle="$(realpath -e -- "$backup_handle")"
    [[ "$(dirname "$canonical_handle")" == "$BACKUP_ROOT" ]] || die "failed deploy backup handle is outside the backup root"
    [[ "$(basename "$canonical_handle")" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-to-[0-9a-f]{12}-[0-9a-f]{16}$ ]] \
      || die "failed deploy backup handle name is invalid"
    release_manifest="$canonical_handle/release.env"
    approval_link="$canonical_handle/approval.env"
    [[ -f "$release_manifest" && -f "$approval_link" ]] || die "failed deploy audit link is missing"
    [[ "$(read_approval_value "$release_manifest" NEW_SHA)" == "$source_sha" ]] || die "failed deploy manifest SHA mismatch"
    [[ "$(read_approval_value "$approval_link" ci_run_id)" == "$ci_run_id" ]] || die "failed deploy linked CI run mismatch"
    [[ "$(read_approval_value "$approval_link" source_sha)" == "$source_sha" ]] || die "failed deploy linked SHA mismatch"
    [[ "$(read_approval_value "$approval_link" artifact_sha256)" == "$artifact_sha256" ]] || die "failed deploy linked artifact mismatch"
    if [[ "$(read_approval_value "$release_manifest" STATE)" == "recovery_required" \
      && "$(read_approval_value "$approval_link" approval_id)" == "$approval_id" ]]; then
      retryable_handles["$canonical_handle"]=1
    fi
  done

  [[ "${#retryable_handles[@]}" -ne 0 ]] || return 1
  [[ "${#retryable_handles[@]}" -eq 1 ]] || die "exactly one recovery-required deploy record is required"
  printf '%s\n' "${!retryable_handles[@]}"
}

recover_forward_release() {
  local source_archive="$1"
  local expected_sha="$2"
  local ci_run_id="$3"
  local expected_artifact_sha256="$4"
  local backup_dir="$5"
  local manifest="$backup_dir/release.env"
  local old_sha state work_dir artifact_tree next_dist failed_dist prior_link prior_approval_id stage_root

  old_sha="$(read_manifest_value "$manifest" OLD_SHA)"
  state="$(read_manifest_value "$manifest" STATE)"
  validate_sha "$old_sha"
  [[ "$(read_manifest_value "$manifest" NEW_SHA)" == "$expected_sha" ]] || die "recovery manifest SHA mismatch"
  [[ "$state" == "recovery_required" ]] || die "deploy record is not recovery-required"

  local approval_claimed=0
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-forward-recovery.XXXXXX")"
  on_recovery_error() {
    local rc=$?
    trap - EXIT ERR
    clear_planned_deployment || true
    start_runtime || true
    log "forward recovery failed; release remains recovery_required and requires a fresh one-time approval"
    if [[ "$approval_claimed" == "1" && -n "$APPROVAL_CLAIM" ]]; then
      finalize_approval failed "$backup_dir" || true
    fi
    rm -rf -- "$work_dir"
    exit "$rc"
  }
  trap on_recovery_error ERR
  trap on_recovery_error EXIT

  approval_claimed=1
  claim_approval "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root"
  next_dist="$backup_dir/dist.recovery.next"
  rm -rf -- "$next_dist"
  mkdir -p "$next_dist"
  cp -a "$artifact_tree/dist/." "$next_dist/"
  set_service_ownership "$next_dist"
  [[ -f "$next_dist/index.html" && ! -L "$next_dist/index.html" && -s "$next_dist/index.html" ]] \
    || die "recovery frontend is invalid"

  prior_link="$backup_dir/approval.env"
  prior_approval_id="$(read_approval_value "$prior_link" approval_id)"
  [[ ! -e "$backup_dir/approval.failed.${prior_approval_id}.env" ]] || die "archived failed approval link already exists"
  mv -- "$prior_link" "$backup_dir/approval.failed.${prior_approval_id}.env"
  write_approval_link "$backup_dir" "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"

  mark_planned_deployment
  wait_for_planned_deployment_inhibition \
    || die "planned deployment inhibition did not become active"
  stop_runtime
  install_runtime_assets "$stage_root" "$expected_sha"
  if ! diff -qr -- "$LIVE_ROOT/dist" "$next_dist" >/dev/null; then
    failed_dist="$backup_dir/dist.recovery.failed.$(date -u +%Y%m%dT%H%M%SZ)"
    mv -- "$LIVE_ROOT/dist" "$failed_dist"
    mv -- "$next_dist" "$LIVE_ROOT/dist"
    set_service_ownership "$LIVE_ROOT/dist"
  else
    rm -rf -- "$next_dist"
  fi
  run_migrations
  start_runtime
  verify_local_health
  reload_prometheus
  verify_prometheus_targets
  verify_public_release
  [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]] || die "recovered Git SHA mismatch"

  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "deployed"
  finalize_approval consumed "$backup_dir"
  clear_planned_deployment
  approval_claimed=0
  trap - EXIT ERR
  rm -rf -- "$work_dir"
  log "recovery deployment verified with a fresh one-time approval: $expected_sha"
  log "rollback handle: $backup_dir"
}

run_verified_backup() {
  local started_at="$1"
  if [[ "$TEST_MODE" == "1" ]]; then
    mkdir -p "$OPS_ROOT/backups/manifests"
    {
      printf 'status=success\n'
      printf 'completed_at=%s\n' "$((started_at + 1))"
      printf 'checksum_ok=1\n'
    } >"$OPS_ROOT/backups/manifests/last-run.env"
  else
    [[ -x "$BACKUP_COMMAND" ]] || die "verified backup command is unavailable"
    run_as_service_user "$BACKUP_COMMAND"
  fi

  local status completed_at checksum_ok
  local result_file="$OPS_ROOT/backups/manifests/last-run.env"
  [[ -r "$result_file" ]] || die "backup completion manifest is missing"
  status="$(sed -n 's/^status=//p' "$result_file")"
  completed_at="$(sed -n 's/^completed_at=//p' "$result_file")"
  checksum_ok="$(sed -n 's/^checksum_ok=//p' "$result_file")"
  [[ "$status" == "success" && "$checksum_ok" == "1" ]] || die "backup did not finish verified"
  [[ "$completed_at" =~ ^[0-9]+$ && "$completed_at" -ge "$started_at" ]] || die "backup manifest is stale"
}

write_release_manifest() {
  local backup_dir="$1"
  local old_sha="$2"
  local new_sha="$3"
  local state="$4"
  local tmp="$backup_dir/release.env.tmp"
  {
    printf 'OLD_SHA=%s\n' "$old_sha"
    printf 'NEW_SHA=%s\n' "$new_sha"
    printf 'STATE=%s\n' "$state"
    printf 'UPDATED_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } >"$tmp"
  mv -f "$tmp" "$backup_dir/release.env"
  chmod 0600 "$backup_dir/release.env"
}

read_manifest_value() {
  local manifest="$1"
  local key="$2"
  sed -n "s/^${key}=//p" "$manifest"
}

prepare_tested_dist() {
  local artifact_tree="$1"
  local backup_dir="$2"
  local next_dist="$backup_dir/dist.next"
  [[ "$(stat -c %d "$backup_dir")" == "$(stat -c %d "$LIVE_ROOT")" ]] \
    || die "frontend staging and live checkout must share a filesystem"
  rm -rf -- "$next_dist"
  mkdir -p "$next_dist"
  cp -a "$artifact_tree/dist/." "$next_dist/"
  set_service_ownership "$next_dist"
  [[ -f "$next_dist/index.html" && ! -L "$next_dist/index.html" && -s "$next_dist/index.html" ]] \
    || die "staged frontend is invalid"
  printf '%s\n' "$next_dist"
}

switch_dist() {
  local next_dist="$1"
  [[ -d "$LIVE_ROOT/dist" ]] || die "current frontend directory is missing"
  [[ -f "$next_dist/index.html" && ! -L "$next_dist/index.html" && -s "$next_dist/index.html" ]] \
    || die "staged frontend is invalid"
  mv -- "$LIVE_ROOT/dist" "$2/dist.pre-switch"
  mv -- "$next_dist" "$LIVE_ROOT/dist"
}

backup_current_dist() {
  local backup_dir="$1"
  [[ -d "$LIVE_ROOT/dist" && -f "$LIVE_ROOT/dist/index.html" \
    && ! -L "$LIVE_ROOT/dist/index.html" && -s "$LIVE_ROOT/dist/index.html" ]] \
    || die "current frontend is invalid"
  cp -a -- "$LIVE_ROOT/dist" "$backup_dir/dist"
  diff -qr "$LIVE_ROOT/dist" "$backup_dir/dist" >/dev/null || die "frontend backup verification failed"
}

restore_dist() {
  local backup_dir="$1"
  local failed_dist
  failed_dist="$backup_dir/dist.failed.$(date -u +%Y%m%dT%H%M%SZ)"
  [[ -d "$backup_dir/dist" ]] || die "rollback frontend backup is missing"
  if [[ -e "$LIVE_ROOT/dist" || -L "$LIVE_ROOT/dist" ]]; then
    mv -- "$LIVE_ROOT/dist" "$failed_dist"
  fi
  mv -- "$backup_dir/dist" "$LIVE_ROOT/dist"
  set_service_ownership "$LIVE_ROOT/dist"
}

stop_runtime() {
  local unit
  local -a existing=()
  while IFS= read -r unit; do
    service_exists "$unit" && existing+=("$unit")
  done < <(managed_runtime_service_names)
  ((${#existing[@]} > 0)) && service_action stop "${existing[@]}"
}

start_runtime() {
  local unit
  local -a existing=()
  while IFS= read -r unit; do
    service_exists "$unit" && existing+=("$unit")
  done < <(runtime_services_expected_active)
  ((${#existing[@]} > 0)) || die "no Retail runtime services are installed"
  service_action restart "${existing[@]}"
}

run_migrations() {
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST migration service"
  else
    service_action start "$MIGRATION_SERVICE"
  fi
}

verify_local_health() {
  if [[ "$TEST_MODE" == "1" ]]; then
    if [[ "$TEST_FAIL_PHASE" == "health" && ! -e "$TEST_ROOT/.health-failure-consumed" ]]; then
      : >"$TEST_ROOT/.health-failure-consumed"
      return 1
    fi
    [[ -f "$LIVE_ROOT/dist/index.html" && ! -L "$LIVE_ROOT/dist/index.html" \
      && -s "$LIVE_ROOT/dist/index.html" ]]
    return
  fi

  local attempt unit all_active
  for attempt in {1..30}; do
    all_active=1
    while IFS= read -r unit; do
      if service_exists "$unit" && ! systemctl is-active --quiet "$unit"; then
        all_active=0
        break
      fi
    done < <(runtime_services_expected_active)
    if [[ "$all_active" == "1" ]] \
      && curl --silent --show-error --fail --max-time 5 http://127.0.0.1:9898/health >/dev/null \
      && curl --silent --show-error --fail --max-time 5 http://127.0.0.1:9898/readyz >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

verify_public_release() {
  if [[ "$TEST_MODE" == "1" ]]; then
    if [[ "$TEST_FAIL_PHASE" == "public_health" && ! -e "$TEST_ROOT/.public-health-failure-consumed" ]]; then
      : >"$TEST_ROOT/.public-health-failure-consumed"
      return 1
    fi
    return 0
  fi

  probe_public_release() {
    curl --silent --show-error --fail --max-time 10 \
      https://retail.unihub.ro/health >/dev/null || return 1
    curl --silent --show-error --fail --max-time 10 \
      https://retail.unihub.ro/readyz >/dev/null || return 1

    local path status
    for path in /metrics /docs /redoc /openapi.json /api/__release_missing__; do
      status="$(curl --silent --show-error --output /dev/null \
        --write-out '%{http_code}' --max-time 10 \
        "https://retail.unihub.ro${path}")" || return 1
      [[ "$status" == "404" ]] || return 1
    done
  }

  local attempt
  for attempt in 1 2 3 4 5 6; do
    if probe_public_release; then
      return 0
    fi
    if [[ "$attempt" -lt 6 ]]; then
      sleep 5
    fi
  done
  return 1
}

rollback_from_backup() {
  local backup_dir="$1"
  local expected_current_sha="$2"
  local old_sha="$3"
  local migrations_may_have_applied="${4:-1}"

  [[ "$migrations_may_have_applied" == "0" || "$migrations_may_have_applied" == "1" ]] \
    || die "invalid rollback migration boundary state"
  if [[ "$migrations_may_have_applied" == "1" ]]; then
    assert_rollback_migration_compatible "$expected_current_sha" "$old_sha"
  fi

  log "rolling back code from $expected_current_sha to $old_sha"
  stop_runtime || true
  git_service reset --hard "$old_sha"
  restore_dist "$backup_dir"
  restore_runtime_assets "$backup_dir"
  start_runtime
  verify_local_health || die "rollback completed but local health failed"
  reload_prometheus || die "rollback completed but Prometheus reload failed"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_current_sha" "rolled_back"
  log "rollback verified at $old_sha; additive database migrations remain in place"
}

deploy_release() {
  local source_archive="$1"
  local expected_sha="$2"
  local ci_run_id="$3"
  local expected_artifact_sha256="$4"
  validate_sha "$expected_sha"
  validate_ci_run_id "$ci_run_id"
  validate_sha256 "$expected_artifact_sha256"
  assert_live_checkout
  assert_worktree_safe

  local old_sha stamp backup_dir work_dir artifact_tree backup_started next_dist backup_nonce stage_root
  old_sha="$(git_service rev-parse HEAD)"
  if [[ "$old_sha" == "$expected_sha" ]]; then
    local recovery_handle=""
    if recovery_handle="$(find_retryable_forward_handle "$ci_run_id" "$expected_sha" "$expected_artifact_sha256")"; then
      git_service fetch --quiet --prune origin main
      git_service merge-base --is-ancestor "$expected_sha" origin/main \
        || die "recovery SHA is no longer an ancestor of current origin/main"
      recover_forward_release \
        "$source_archive" "$expected_sha" "$ci_run_id" \
        "$expected_artifact_sha256" "$recovery_handle"
      return 0
    fi
  fi

  fetch_and_verify_commit "$expected_sha"
  if [[ "$old_sha" == "$expected_sha" ]]; then
    verify_completed_deploy_record "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
    work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-reverify.XXXXXX")"
    trap 'rm -rf -- "$work_dir"' RETURN
    artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
    [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
      && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
    diff -qr -- "$LIVE_ROOT/dist" "$artifact_tree/dist" >/dev/null \
      || die "live frontend differs from the tested release artifact"
    detect_prometheus_network
    assert_prometheus_shared_include
    verify_active_runtime_assets "$expected_sha"
    verify_local_health
    verify_public_release
    log "existing deployment reverified without mutation: $expected_sha"
    return 0
  fi
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_nonce="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  backup_dir="$BACKUP_ROOT/${stamp}-${old_sha:0:12}-to-${expected_sha:0:12}-${backup_nonce}"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN

  local runtime_touched=0
  local rollback_needed=0
  local approval_claimed=0
  local migrations_may_have_applied=0
  on_deploy_error() {
    local rc=$?
    trap - EXIT ERR
    if [[ "$rollback_needed" == "1" ]]; then
      log "deployment failed after switch; starting automatic rollback"
      if ! (rollback_from_backup "$backup_dir" "$expected_sha" "$old_sha" "$migrations_may_have_applied"); then
        log "ERROR: automatic rollback did not restore healthy runtime" >&2
        if [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]]; then
          write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "recovery_required"
          start_runtime || true
          log "deployment remains on the expected SHA and requires a fresh one-time approval for forward recovery"
        fi
      fi
    else
      if [[ "$runtime_touched" == "1" ]]; then
        start_runtime || true
      fi
    fi
    clear_planned_deployment || true
    if [[ "$approval_claimed" == "1" && -n "$APPROVAL_CLAIM" ]]; then
      finalize_approval failed "$backup_dir" || true
    fi
    exit "$rc"
  }
  # ERR performs rollback while deploy_release locals are still in scope.
  # EXIT is the fail-safe for explicit exits (for example, validation via die).
  # The handler clears both traps before cleanup, so it can run only once.
  trap on_deploy_error ERR
  trap on_deploy_error EXIT

  approval_claimed=1
  claim_approval "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root"
  ensure_backup_root
  mkdir -p "$backup_dir"
  chmod 0700 "$backup_dir"
  git_service archive --format=tar.gz "$old_sha" >"$backup_dir/source-${old_sha}.tar.gz"
  sha256sum "$backup_dir/source-${old_sha}.tar.gz" >"$backup_dir/source.sha256"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "preparing"
  write_approval_link "$backup_dir" "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  backup_started="$(date +%s)"
  run_verified_backup "$backup_started"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "backed_up"
  next_dist="$(prepare_tested_dist "$artifact_tree" "$backup_dir")"
  backup_current_dist "$backup_dir"
  backup_runtime_assets "$backup_dir"
  rollback_needed=1

  runtime_touched=1
  mark_planned_deployment
  wait_for_planned_deployment_inhibition \
    || die "planned deployment inhibition did not become active"
  stop_runtime
  install_runtime_assets "$stage_root" "$expected_sha"
  switch_dist "$next_dist" "$backup_dir"
  git_service merge --ff-only "$expected_sha"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "switched"
  migrations_may_have_applied=1
  run_migrations
  start_runtime
  verify_local_health
  reload_prometheus
  verify_prometheus_targets
  verify_public_release
  [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]] || die "deployed Git SHA mismatch"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "deployed"
  finalize_approval consumed "$backup_dir"
  clear_planned_deployment
  trap - EXIT ERR
  log "deployment verified: $expected_sha"
  log "rollback handle: $backup_dir"
}

manual_rollback() {
  if [[ "$TEST_MODE" != "1" && "${SUDO_USER:-}" == "unihub-deploy" ]]; then
    die "the deploy runner is not authorized to invoke manual rollback"
  fi
  local requested_backup_dir="$1"
  [[ -d "$requested_backup_dir" && ! -L "$requested_backup_dir" ]] || die "rollback handle is invalid"
  local backup_dir
  backup_dir="$(realpath -e -- "$requested_backup_dir")"
  [[ "$(dirname "$backup_dir")" == "$BACKUP_ROOT" ]] || die "rollback handle is outside the Retail backup root"
  [[ "$(basename "$backup_dir")" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-to-[0-9a-f]{12}-[0-9a-f]{16}$ ]] \
    || die "rollback handle name is invalid"
  local manifest="$backup_dir/release.env"
  [[ -f "$manifest" ]] || die "rollback manifest is missing"
  local old_sha new_sha state
  old_sha="$(read_manifest_value "$manifest" OLD_SHA)"
  new_sha="$(read_manifest_value "$manifest" NEW_SHA)"
  state="$(read_manifest_value "$manifest" STATE)"
  validate_sha "$old_sha"
  validate_sha "$new_sha"
  [[ "$state" == "deployed" ]] || die "rollback handle is not in deployed state"
  assert_live_checkout
  [[ "$(git_service rev-parse HEAD)" == "$new_sha" ]] || die "current SHA does not match rollback manifest"
  assert_worktree_safe
  rollback_from_backup "$backup_dir" "$new_sha" "$old_sha" 1
}

validate_release() {
  local source_archive="$1"
  local expected_sha="$2"
  validate_sha "$expected_sha"
  assert_live_checkout
  assert_worktree_safe
  fetch_and_verify_commit "$expected_sha"
  local work_dir artifact_tree artifact_sha256 stage_root
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-validate.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN
  artifact_sha256="$(sha256sum "$source_archive" | awk '{print $1}')"
  validate_sha256 "$artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$artifact_sha256" "$work_dir")"
  [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
    && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root"
  log "artifact and runtime topology match the approved source without mutation: $expected_sha"
}

case "${1:-}" in
  validate)
    [[ "$#" -eq 3 ]] || die "usage: $PROGRAM validate <artifact.tar.gz> <source-sha>"
    validate_release "$2" "$3"
    ;;
  rollback)
    [[ "$#" -eq 2 ]] || die "usage: $PROGRAM rollback <backup-handle>"
    manual_rollback "$2"
    ;;
  deploy)
    [[ "$#" -eq 5 ]] || die "usage: $PROGRAM deploy <artifact.tar.gz> <source-sha> <ci-run-id> <artifact-sha256>"
    deploy_release "$2" "$3" "$4" "$5"
    ;;
  *)
    [[ "$#" -eq 4 ]] || die "usage: $PROGRAM <artifact.tar.gz> <source-sha> <ci-run-id> <artifact-sha256>"
    if [[ "$TEST_MODE" != "1" && "${SUDO_USER:-}" == "unihub-deploy" ]]; then
      [[ "$1" == /* ]] || die "deploy runner artifact path must be absolute"
    fi
    deploy_release "$1" "$2" "$3" "$4"
    ;;
esac
