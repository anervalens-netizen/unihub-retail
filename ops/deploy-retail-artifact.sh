#!/usr/bin/bash -p

set -Eeuo pipefail
umask 077
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONSTARTUP PYTHONINSPECT || true
export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1
unset PYTHONHOME PYTHONPATH MYPYPATH MYPY_CONFIG_FILE

PROGRAM="$(basename "$0")"
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PYTHON_BASE="/usr/bin/python3.12"
PYTHON_BASE_SHA256="1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
PYTHON_VERSION="3.12.3"
SYSTEM_SITECUSTOMIZE="/usr/lib/python3.12/sitecustomize.py"
SYSTEM_SITECUSTOMIZE_RESOLVED="/etc/python3.12/sitecustomize.py"
SYSTEM_SITECUSTOMIZE_SHA256="43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e"
PYTHON_RUNTIME_TREE_PROPERTY="unihub:python-runtime:site-packages-tree-sha256:v1"
PYTHON_RUNTIME_REQUIREMENTS_NAME="PYTHON_RUNTIME_REQUIREMENTS.lock"
PYTHON_RUNTIME_WHEELS_NAME="PYTHON_RUNTIME_WHEELS.tar.gz"
PYTHON_RUNTIME_SUPPLY_NAME="PYTHON_RUNTIME_SUPPLY.json"
TEST_MODE="${RETAIL_DEPLOY_TEST_MODE:-0}"
TEST_FAIL_PHASE="${RETAIL_DEPLOY_TEST_FAIL_PHASE:-}"
TEST_NOW="${RETAIL_DEPLOY_TEST_NOW:-}"
SHARED_DIRECTORY_MODE=2770
FRONTEND_DIRECTORY_MODE=0750
FRONTEND_FILE_MODE=0640
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
  # The isolated CI runner deliberately forbids chmod with setgid bits.
  # Production never enters this branch and retains the exact 2770 contract.
  SHARED_DIRECTORY_MODE=770
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

if [[ "$TEST_MODE" == "1" ]]; then
  IMPORT_DIRECTORY_USER="$SERVICE_USER"
  IMPORT_FILE_USER="$SERVICE_USER"
  IMPORT_SPOOL_FILE_USER="${RETAIL_DEPLOY_TEST_IMPORT_FILE_USER:-$IMPORT_FILE_USER}"
  WEB_FILE_USER="${RETAIL_DEPLOY_TEST_WEB_FILE_USER:-$SERVICE_USER}"
  FRONTEND_FILE_USER="$SERVICE_USER"
  FRONTEND_FILE_GROUP="$SERVICE_GROUP"
  IMPORT_SPOOL_GROUP="$SERVICE_GROUP"
  PROMO_ARTIFACT_GROUP="$SERVICE_GROUP"
  GRILE_FILE_USER="$SERVICE_USER"
  GRILE_ARTIFACT_GROUP="$SERVICE_GROUP"
  EXPORT_FILE_USER="$SERVICE_USER"
  SALARY_EXPORT_FILE_USER="$SERVICE_USER"
  EXPORT_ARTIFACT_GROUP="$SERVICE_GROUP"
else
  [[ -z "${RETAIL_DEPLOY_TEST_IMPORT_FILE_USER:-}" ]] \
    || die "test import file identity is forbidden outside test mode"
  [[ -z "${RETAIL_DEPLOY_TEST_WEB_FILE_USER:-}" ]] \
    || die "test web file identity is forbidden outside test mode"
  IMPORT_DIRECTORY_USER="unihub-import"
  IMPORT_FILE_USER="unihub-import"
  IMPORT_SPOOL_FILE_USER="$IMPORT_FILE_USER"
  WEB_FILE_USER="unihub-web"
  FRONTEND_FILE_USER="root"
  FRONTEND_FILE_GROUP="unihub-web"
  IMPORT_SPOOL_GROUP="unihub-import-spool"
  PROMO_ARTIFACT_GROUP="unihub-promo-artifacts"
  GRILE_FILE_USER="unihub-grile"
  GRILE_ARTIFACT_GROUP="unihub-grile-artifacts"
  EXPORT_FILE_USER="unihub-export"
  SALARY_EXPORT_FILE_USER="unihub-salary-export"
  EXPORT_ARTIFACT_GROUP="unihub-export-artifacts"
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
SALARY_EXPORT_WORKER_SERVICE="unihub-salary-export-worker.service"
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
    "$EXPORT_WORKER_SERVICE" \
    "$SALARY_EXPORT_WORKER_SERVICE"
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
    if "$PYTHON_BASE" -I -S -c '
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

assert_regular_tree() {
  local root="$1"
  local unsafe
  [[ -d "$root" && ! -L "$root" ]] || die "runtime artifact tree is unavailable or unsafe: $root"
  unsafe="$(find "$root" -xdev ! -type d ! -type f -print -quit)"
  [[ -z "$unsafe" ]] || die "runtime artifact tree contains a symlink or special file: $unsafe"
}

set_frontend_permissions() {
  local root="$1"
  assert_regular_tree "$root"
  if [[ "$TEST_MODE" != "1" ]]; then
    find "$root" -xdev -type d -exec chown "$FRONTEND_FILE_USER:$FRONTEND_FILE_GROUP" {} +
    find "$root" -xdev -type f -exec chown "$FRONTEND_FILE_USER:$FRONTEND_FILE_GROUP" {} +
  fi
  find "$root" -xdev -type d -exec chmod "$FRONTEND_DIRECTORY_MODE" {} +
  find "$root" -xdev -type f -exec chmod "$FRONTEND_FILE_MODE" {} +
  verify_frontend_permissions "$root"
}

verify_frontend_permissions() {
  local root="$1"
  local path actual expected
  assert_regular_tree "$root"
  while IFS= read -r -d '' path; do
    if [[ -d "$path" ]]; then
      expected="$FRONTEND_FILE_USER:$FRONTEND_FILE_GROUP:750"
    else
      expected="$FRONTEND_FILE_USER:$FRONTEND_FILE_GROUP:640"
    fi
    actual="$(stat -c '%U:%G:%a' "$path")"
    [[ "$actual" == "$expected" ]] \
      || die "frontend permission contract is invalid: $path ($actual)"
  done < <(find "$root" -xdev \( -type d -o -type f \) -print0)
}

apply_shared_tree_contract() {
  local root="$1"
  local owner="$2"
  local group="$3"
  local excluded="${4:-}"
  local -a scope=(find "$root" -xdev)
  if [[ -n "$excluded" ]]; then
    scope+=( -path "$excluded" -prune -o )
  fi
  if [[ "$TEST_MODE" != "1" ]]; then
    "${scope[@]}" -type d -exec chown "$owner:$group" {} +
    "${scope[@]}" -type f -exec chown "$owner:$group" {} +
  fi
  "${scope[@]}" -type d -exec chmod "$SHARED_DIRECTORY_MODE" {} +
  "${scope[@]}" -type f -exec chmod 0660 {} +
}

verify_shared_tree_contract() {
  local root="$1"
  local owner="$2"
  local group="$3"
  local excluded="${4:-}"
  local file_owners="${5:-$owner}"
  local path expected_mode actual actual_owner actual_group actual_mode allowed_owner
  local -a allowed_file_owners
  IFS=, read -r -a allowed_file_owners <<<"$file_owners"
  [[ "${#allowed_file_owners[@]}" -gt 0 ]] \
    || die "runtime artifact file owner contract is empty: $root"
  local -a scope=(find "$root" -xdev)
  if [[ -n "$excluded" ]]; then
    scope+=( -path "$excluded" -prune -o )
  fi
  while IFS= read -r -d '' path; do
    if [[ -d "$path" ]]; then
      expected_mode="$SHARED_DIRECTORY_MODE"
    else
      expected_mode=660
    fi
    actual="$(stat -c '%U:%G:%a' "$path")"
    IFS=: read -r actual_owner actual_group actual_mode <<<"$actual"
    if [[ -d "$path" ]]; then
      [[ "$actual" == "$owner:$group:$expected_mode" ]] \
        || die "runtime artifact permission contract is invalid: $path ($actual)"
      continue
    fi
    [[ "$actual_group:$actual_mode" == "$group:$expected_mode" ]] \
      || die "runtime artifact permission contract is invalid: $path ($actual)"
    for allowed_owner in "${allowed_file_owners[@]}"; do
      if [[ -n "$allowed_owner" && "$actual_owner" == "$allowed_owner" ]]; then
        continue 2
      fi
    done
    die "runtime artifact file owner is invalid: $path ($actual)"
  done < <("${scope[@]}" \( -type d -o -type f \) -print0)
}

ensure_export_artifact_namespaces() {
  local artifact_root="$LIVE_ROOT/data/export_artifacts"
  local salary_root="$artifact_root/salary"
  [[ ! -L "$LIVE_ROOT/data" && ! -L "$artifact_root" && ! -L "$salary_root" ]] \
    || die "export artifact namespace must not contain symlinks"
  if [[ "$TEST_MODE" == "1" ]]; then
    mkdir -p "$salary_root"
    chmod "$SHARED_DIRECTORY_MODE" "$artifact_root" "$salary_root"
  else
    install -d -m "$SHARED_DIRECTORY_MODE" -o "$EXPORT_FILE_USER" -g "$EXPORT_ARTIFACT_GROUP" \
      "$artifact_root"
    install -d -m "$SHARED_DIRECTORY_MODE" -o "$SALARY_EXPORT_FILE_USER" -g "$EXPORT_ARTIFACT_GROUP" \
      "$salary_root"
  fi
}

apply_runtime_identity_filesystem() {
  local import_root="$LIVE_ROOT/data/import_spool"
  local promo_root="$LIVE_ROOT/data/promo_generations"
  local grile_root="$LIVE_ROOT/backend/outputs/grile"
  local export_root="$LIVE_ROOT/data/export_artifacts"
  local salary_root="$export_root/salary"

  ensure_export_artifact_namespaces
  if [[ "$TEST_MODE" == "1" ]]; then
    mkdir -p "$import_root" "$promo_root" "$grile_root"
  else
    install -d -m "$SHARED_DIRECTORY_MODE" -o "$IMPORT_FILE_USER" -g "$IMPORT_SPOOL_GROUP" "$import_root"
    install -d -m "$SHARED_DIRECTORY_MODE" -o "$IMPORT_FILE_USER" -g "$PROMO_ARTIFACT_GROUP" "$promo_root"
    install -d -m "$SHARED_DIRECTORY_MODE" -o "$GRILE_FILE_USER" -g "$GRILE_ARTIFACT_GROUP" "$grile_root"
  fi
  assert_regular_tree "$import_root"
  assert_regular_tree "$promo_root"
  assert_regular_tree "$grile_root"
  assert_regular_tree "$export_root"
  apply_shared_tree_contract "$import_root" "$IMPORT_FILE_USER" "$IMPORT_SPOOL_GROUP"
  apply_shared_tree_contract "$promo_root" "$IMPORT_FILE_USER" "$PROMO_ARTIFACT_GROUP"
  apply_shared_tree_contract "$grile_root" "$GRILE_FILE_USER" "$GRILE_ARTIFACT_GROUP"
  apply_shared_tree_contract "$export_root" "$EXPORT_FILE_USER" "$EXPORT_ARTIFACT_GROUP" "$salary_root"
  apply_shared_tree_contract "$salary_root" "$SALARY_EXPORT_FILE_USER" "$EXPORT_ARTIFACT_GROUP"
}

verify_runtime_identity_filesystem() {
  local import_root="$LIVE_ROOT/data/import_spool"
  local promo_root="$LIVE_ROOT/data/promo_generations"
  local grile_root="$LIVE_ROOT/backend/outputs/grile"
  local export_root="$LIVE_ROOT/data/export_artifacts"
  local salary_root="$export_root/salary"
  local root
  for root in "$import_root" "$promo_root" "$grile_root" "$export_root" "$salary_root"; do
    assert_regular_tree "$root"
  done
  verify_shared_tree_contract \
    "$import_root" "$IMPORT_DIRECTORY_USER" "$IMPORT_SPOOL_GROUP" "" \
    "$IMPORT_SPOOL_FILE_USER,$WEB_FILE_USER"
  verify_shared_tree_contract "$promo_root" "$IMPORT_FILE_USER" "$PROMO_ARTIFACT_GROUP"
  verify_shared_tree_contract "$grile_root" "$GRILE_FILE_USER" "$GRILE_ARTIFACT_GROUP"
  verify_shared_tree_contract "$export_root" "$EXPORT_FILE_USER" "$EXPORT_ARTIFACT_GROUP" "$salary_root"
  verify_shared_tree_contract "$salary_root" "$SALARY_EXPORT_FILE_USER" "$EXPORT_ARTIFACT_GROUP"
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

verify_python_base() {
  [[ -x "$PYTHON_BASE" && ! -L "$PYTHON_BASE" ]] \
    || die "pinned Python base interpreter is unavailable or unsafe"
  [[ "$(sha256sum "$PYTHON_BASE" | awk '{print $1}')" == "$PYTHON_BASE_SHA256" ]] \
    || die "pinned Python base interpreter digest mismatch"
  [[ "$($PYTHON_BASE -I -S -c 'import platform; print(platform.python_version())')" == "$PYTHON_VERSION" ]] \
    || die "pinned Python base interpreter version mismatch"
  [[ -f "$SYSTEM_SITECUSTOMIZE" && ! -L "$SYSTEM_SITECUSTOMIZE_RESOLVED" \
    && "$(readlink -f "$SYSTEM_SITECUSTOMIZE")" == "$SYSTEM_SITECUSTOMIZE_RESOLVED" \
    && "$(sha256sum "$SYSTEM_SITECUSTOMIZE" | awk '{print $1}')" == "$SYSTEM_SITECUSTOMIZE_SHA256" ]] \
    || die "system sitecustomize identity mismatch"
}

validate_artifact_archive() {
  local archive="$1"
  "$PYTHON_BASE" -I -S - "$archive" <<'PY'
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
    "ops/systemd/unihub-salary-export-worker.service",
    "ops/systemd/unihub-legacy-worker.service",
    "ops/systemd/unihub-retail-migrate.service",
    "ops/provision-retail-service-identities.sh",
    "ops/provision-retail-salary-export-database.sh",
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

validate_tracked_path() {
  local path="$1"
  [[ -n "$path" && "$path" != /* ]] || die "invalid tracked source path"
  case "/$path/" in
    */../*|*/./*) die "unsafe tracked source path: $path" ;;
  esac
}

normalize_tracked_parent_directories() {
  local path="$1"
  local parent
  parent="$(dirname -- "$path")"
  while [[ "$parent" != "." ]]; do
    [[ -d "$LIVE_ROOT/$parent" && ! -L "$LIVE_ROOT/$parent" ]] \
      || die "tracked source parent is unavailable or unsafe: $parent"
    chmod 0755 "$LIVE_ROOT/$parent"
    parent="$(dirname -- "$parent")"
  done
}

normalize_tracked_source_permissions() {
  local entry metadata mode object stage path expected
  [[ -d "$LIVE_ROOT" && ! -L "$LIVE_ROOT" ]] || die "Retail live root is unsafe"
  chmod 0755 "$LIVE_ROOT"
  if [[ "$TEST_MODE" == "1" && "$TEST_FAIL_PHASE" == "source_permissions" ]]; then
    log "TEST tracked source permission failure"
    return 1
  fi
  while IFS= read -r -d '' entry; do
    metadata="${entry%%$'\t'*}"
    path="${entry#*$'\t'}"
    read -r mode object stage <<<"$metadata"
    [[ "$object" =~ ^[0-9a-f]{40,64}$ && "$stage" == "0" ]] \
      || die "tracked source index entry is invalid: $path"
    validate_tracked_path "$path"
    case "$mode" in
      100644) expected=0644 ;;
      100755) expected=0755 ;;
      *) die "unsupported tracked source mode $mode: $path" ;;
    esac
    [[ -f "$LIVE_ROOT/$path" && ! -L "$LIVE_ROOT/$path" ]] \
      || die "tracked source file is unavailable or unsafe: $path"
    normalize_tracked_parent_directories "$path"
    chmod "$expected" "$LIVE_ROOT/$path"
  done < <(git_service ls-files --stage -z)
  verify_tracked_source_permissions
  git_service diff --quiet --ignore-submodules -- \
    || die "tracked source content changed while normalizing permissions"
  git_service diff --cached --quiet --ignore-submodules -- \
    || die "tracked source index changed while normalizing permissions"
}

verify_tracked_source_permissions() {
  local entry metadata mode object stage path expected parent actual
  [[ "$(stat -c '%a' "$LIVE_ROOT")" == "755" ]] \
    || die "Retail live root must be mode 0755"
  while IFS= read -r -d '' entry; do
    metadata="${entry%%$'\t'*}"
    path="${entry#*$'\t'}"
    read -r mode object stage <<<"$metadata"
    [[ "$object" =~ ^[0-9a-f]{40,64}$ && "$stage" == "0" ]] \
      || die "tracked source index entry is invalid: $path"
    validate_tracked_path "$path"
    case "$mode" in
      100644) expected=644 ;;
      100755) expected=755 ;;
      *) die "unsupported tracked source mode $mode: $path" ;;
    esac
    [[ -f "$LIVE_ROOT/$path" && ! -L "$LIVE_ROOT/$path" ]] \
      || die "tracked source file is unavailable or unsafe: $path"
    actual="$(stat -c '%a' "$LIVE_ROOT/$path")"
    [[ "$actual" == "$expected" ]] \
      || die "tracked source mode is invalid: $path ($actual)"
    parent="$(dirname -- "$path")"
    while [[ "$parent" != "." ]]; do
      [[ -d "$LIVE_ROOT/$parent" && ! -L "$LIVE_ROOT/$parent" \
        && "$(stat -c '%a' "$LIVE_ROOT/$parent")" == "755" ]] \
        || die "tracked source parent mode is invalid: $parent"
      parent="$(dirname -- "$parent")"
    done
  done < <(git_service ls-files --stage -z)
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

verify_service_account_contract() {
  local user="$1"
  local primary_group="$2"
  local supplementary_csv="$3"
  local entry name _password uid _gid _gecos home shell
  entry="$(getent passwd "$user")" || die "required runtime service user is absent: $user"
  IFS=: read -r name _password uid _gid _gecos home shell <<<"$entry"
  [[ "$name" == "$user" && "$uid" =~ ^[1-9][0-9]*$ \
    && "$home" == "/nonexistent" && "$shell" == "/usr/sbin/nologin" ]] \
    || die "runtime service user contract is invalid: $user"
  [[ "$(id -gn "$user")" == "$primary_group" ]] \
    || die "runtime service user primary group is invalid: $user"
  diff -u \
    <({ printf '%s\n' "$primary_group"; tr ',' '\n' <<<"$supplementary_csv"; } | sed '/^$/d' | sort -u) \
    <(id -nG "$user" | tr ' ' '\n' | sort -u) >/dev/null \
    || die "runtime service user memberships are invalid: $user"
  [[ "$(passwd -S "$user" | awk '{print $2}')" == "L" ]] \
    || die "runtime service user password is not locked: $user"
}

verify_runtime_identity_prerequisites() {
  [[ "$TEST_MODE" == "1" ]] && return
  verify_service_account_contract \
    unihub-web unihub-web \
    unihub-import-spool,unihub-promo-artifacts,unihub-grile-artifacts,unihub-export-artifacts
  verify_service_account_contract unihub-operations unihub-operations ""
  verify_service_account_contract \
    unihub-import unihub-import unihub-import-spool,unihub-promo-artifacts
  verify_service_account_contract \
    unihub-grile unihub-grile unihub-operations,unihub-grile-artifacts
  verify_service_account_contract \
    unihub-export unihub-export unihub-operations,unihub-export-artifacts
  verify_service_account_contract \
    unihub-salary-export unihub-salary-export unihub-export-artifacts
  verify_service_account_contract unihub-migrate unihub-migrate ""

  local group
  for group in \
    unihub-web unihub-operations unihub-import unihub-grile unihub-export \
    unihub-salary-export unihub-migrate unihub-import-spool \
    unihub-promo-artifacts unihub-grile-artifacts unihub-export-artifacts; do
    id -nG andrei | tr ' ' '\n' | grep -Fxq "$group" \
      || die "operator lacks rollback-compatible runtime group: $group"
  done

  local file expected
  while IFS='|' read -r file expected; do
    [[ -f "$LIVE_ROOT/$file" && ! -L "$LIVE_ROOT/$file" ]] \
      || die "runtime environment file is absent or unsafe: $file"
    [[ "$(stat -c '%U:%G:%a' "$LIVE_ROOT/$file")" == "$expected" ]] \
      || die "runtime environment ownership contract is invalid: $file"
  done <<'EOF'
.env|root:unihub-web:640
.env.worker|root:unihub-operations:640
.env.import-worker|root:unihub-import:640
.env.salary-export-worker|root:unihub-salary-export:640
.env.migrations|root:unihub-migrate:640
EOF
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

  if ! "$PYTHON_BASE" -I -S - "$current_manifest" "$target_manifest" <<'PY'
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

  "$PYTHON_BASE" -I -S - "$bundle_dir" "$(basename -- "$source_archive")" "$expected_sha" "$expected_artifact_sha256" <<'PY'
import hashlib
import json
import pathlib
import sys
import uuid

root = pathlib.Path(sys.argv[1])
archive_name, expected_sha, expected_digest = sys.argv[2:]
required = {
    "SOURCE_SHA", "SHA256SUMS", "SBOM.cdx.json", "SBOM.npm.cdx.json",
    "SBOM.python.cdx.json", "PROVENANCE.json", "RELEASE_MANIFEST.json",
    "PYTHON_RUNTIME_REQUIREMENTS.lock", "PYTHON_RUNTIME_SUPPLY.json",
    "PYTHON_RUNTIME_WHEELS.tar.gz",
    archive_name,
}
release_a_evidence = {
    "schema-gate.json",
    "release-a-schema-empty.xml",
    "release-a-schema-restored.xml",
}
present_release_a_evidence = {
    name for name in release_a_evidence if (root / name).exists()
}
if present_release_a_evidence and present_release_a_evidence != release_a_evidence:
    raise SystemExit("Release-A evidence inventory is incomplete")
required.update(present_release_a_evidence)
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
manifest_sha256 = manifest.get("sha256")
expected_manifest_files = required - {"SHA256SUMS", "RELEASE_MANIFEST.json"}
if (
    not isinstance(manifest_sha256, dict)
    or set(manifest_sha256) != expected_manifest_files
    or any(
    manifest_sha256.get(name) != hashlib.sha256((root / name).read_bytes()).hexdigest()
    for name in expected_manifest_files
    )
):
    raise SystemExit("release manifest evidence digest mismatch")
release_a_manifest = manifest.get("releaseAEvidence")
if present_release_a_evidence:
    expected_release_a_manifest = {
        "sourceSha": expected_sha,
        "workflowRunId": str(release_a_manifest.get("workflowRunId", ""))
        if isinstance(release_a_manifest, dict)
        else "",
        "files": {name: manifest_sha256[name] for name in sorted(release_a_evidence)},
    }
    if (
        not isinstance(release_a_manifest, dict)
        or not expected_release_a_manifest["workflowRunId"].isdigit()
        or release_a_manifest != expected_release_a_manifest
    ):
        raise SystemExit("Release-A evidence manifest is invalid")
elif release_a_manifest is not None:
    raise SystemExit("Release-A evidence manifest has no matching files")
provenance = json.loads((root / "PROVENANCE.json").read_text(encoding="utf-8"))
subjects = provenance.get("subject", [])
if len(subjects) != 1 or subjects[0].get("name") != archive_name or subjects[0].get("digest", {}).get("sha256") != expected_digest:
    raise SystemExit("release provenance subject mismatch")
if (
    provenance.get("predicate", {})
    .get("buildDefinition", {})
    .get("externalParameters", {})
    .get("releaseAEvidence")
    != release_a_manifest
):
    raise SystemExit("Release-A provenance evidence mismatch")
sbom = json.loads((root / "SBOM.cdx.json").read_text(encoding="utf-8"))
if sbom.get("bomFormat") != "CycloneDX" or sbom.get("metadata", {}).get("component", {}).get("version") != expected_sha:
    raise SystemExit("release SBOM identity mismatch")
serial_number = sbom.get("serialNumber", "")
try:
    if not serial_number.startswith("urn:uuid:"):
        raise ValueError
    uuid.UUID(serial_number.removeprefix("urn:uuid:"))
except (AttributeError, ValueError):
    raise SystemExit("release SBOM serialNumber is missing or invalid")
if not sbom.get("components") or not sbom.get("dependencies"):
    raise SystemExit("release SBOM inventory or dependency graph is empty")
if any("node_modules" in str(item.get("purl", "")) for item in sbom["components"]):
    raise SystemExit("release SBOM contains an invalid node_modules PURL")
root_ref = sbom.get("metadata", {}).get("component", {}).get("bom-ref")
if not any(
    item.get("aggregate") == "complete" and root_ref in item.get("assemblies", [])
    for item in sbom.get("compositions", [])
):
    raise SystemExit("release SBOM completeness declaration is missing")
for component in sbom["components"]:
    purl = str(component.get("purl", ""))
    if component.get("scope") not in {"required", "optional", "excluded"}:
        raise SystemExit(f"release SBOM component scope is missing: {purl}")
    hashes = list(component.get("hashes", []))
    for reference in component.get("externalReferences", []):
        hashes.extend(reference.get("hashes", []))
    if (
        component.get("type") != "application"
        and purl.startswith(("pkg:npm/", "pkg:pypi/"))
        and not any(item.get("alg") and item.get("content") for item in hashes)
    ):
        raise SystemExit(f"release SBOM component hash evidence is missing: {purl}")
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

  local supply_root="$work_dir/python-runtime-supply"
  mkdir -p "$supply_root/wheels"
  install -m 0400 -- "$bundle_dir/$PYTHON_RUNTIME_REQUIREMENTS_NAME" \
    "$supply_root/$PYTHON_RUNTIME_REQUIREMENTS_NAME"
  install -m 0400 -- "$bundle_dir/$PYTHON_RUNTIME_SUPPLY_NAME" \
    "$supply_root/$PYTHON_RUNTIME_SUPPLY_NAME"
  install -m 0400 -- "$bundle_dir/SBOM.python.cdx.json" \
    "$supply_root/SBOM.python.cdx.json"
  "$PYTHON_BASE" -I -S - \
    "$bundle_dir/$PYTHON_RUNTIME_WHEELS_NAME" \
    "$supply_root/wheels" \
    "$supply_root/$PYTHON_RUNTIME_SUPPLY_NAME" \
    "$supply_root/$PYTHON_RUNTIME_REQUIREMENTS_NAME" \
    "$supply_root/SBOM.python.cdx.json" \
    "$PYTHON_BASE" "$PYTHON_BASE_SHA256" "$PYTHON_VERSION" \
    "$PYTHON_RUNTIME_TREE_PROPERTY" <<'PY'
import hashlib
import json
import pathlib
import re
import sys
import tarfile

(
    archive_value,
    output_value,
    supply_value,
    requirements_value,
    sbom_value,
    python_path,
    python_sha256,
    python_version,
    tree_property,
) = sys.argv[1:]
archive = pathlib.Path(archive_value)
output = pathlib.Path(output_value)
supply_path = pathlib.Path(supply_value)
requirements = pathlib.Path(requirements_value)
sbom_path = pathlib.Path(sbom_value)
if any(path.is_symlink() or not path.is_file() for path in (archive, supply_path, requirements, sbom_path)):
    raise SystemExit("Python runtime supply inputs are unsafe")
supply = json.loads(supply_path.read_text(encoding="utf-8"))
sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
tree_values = [
    str(item.get("value", ""))
    for item in sbom.get("metadata", {}).get("properties", [])
    if isinstance(item, dict) and item.get("name") == tree_property
]
wheels = supply.get("wheels")
wheel_archive = supply.get("wheelArchive")
if (
    supply.get("schemaVersion") != 1
    or supply.get("python")
    != {"path": python_path, "sha256": python_sha256, "version": python_version}
    or supply.get("requirements")
    != {
        "name": requirements.name,
        "sha256": hashlib.sha256(requirements.read_bytes()).hexdigest(),
    }
    or supply.get("sbom")
    != {"name": sbom_path.name, "sha256": hashlib.sha256(sbom_path.read_bytes()).hexdigest()}
    or supply.get("bootstrapDistributions") != {"pip": "24.0"}
    or len(tree_values) != 1
    or supply.get("sitePackages")
    != {"property": tree_property, "sha256": tree_values[0]}
    or not isinstance(wheels, list)
    or not wheels
    or len(wheels) > 512
    or not isinstance(wheel_archive, dict)
    or wheel_archive.get("name") != archive.name
    or wheel_archive.get("sha256") != hashlib.sha256(archive.read_bytes()).hexdigest()
    or wheel_archive.get("fileCount") != len(wheels)
):
    raise SystemExit("Python runtime supply manifest identity mismatch")
expected = {}
total = 0
for item in wheels:
    if not isinstance(item, dict):
        raise SystemExit("Python runtime wheel manifest entry is invalid")
    name = item.get("name")
    digest = item.get("sha256")
    size = item.get("size")
    if (
        not isinstance(name, str)
        or pathlib.PurePosixPath(name).name != name
        or re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", name) is None
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not isinstance(size, int)
        or size <= 0
        or name in expected
    ):
        raise SystemExit("Python runtime wheel manifest entry is unsafe")
    expected[name] = (digest, size)
    total += size
if total != wheel_archive.get("totalBytes") or total > 536_870_912:
    raise SystemExit("Python runtime wheel manifest size mismatch")
seen = set()
with tarfile.open(archive, mode="r:gz") as bundle:
    for member in bundle.getmembers():
        normalized = pathlib.PurePosixPath(member.name).as_posix()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in {"", "."}:
            if not member.isdir():
                raise SystemExit("Python runtime wheel archive root is invalid")
            continue
        if member.isdir():
            raise SystemExit("Python runtime wheel archive contains an unexpected directory")
        if not member.isfile() or pathlib.PurePosixPath(normalized).name != normalized or normalized in seen:
            raise SystemExit("Python runtime wheel archive member is unsafe")
        if normalized not in expected or member.size != expected[normalized][1]:
            raise SystemExit("Python runtime wheel archive inventory mismatch")
        handle = bundle.extractfile(member)
        if handle is None:
            raise SystemExit("Python runtime wheel archive member is unreadable")
        payload = handle.read()
        if len(payload) != member.size or hashlib.sha256(payload).hexdigest() != expected[normalized][0]:
            raise SystemExit("Python runtime wheel archive digest mismatch")
        target = output / normalized
        target.write_bytes(payload)
        target.chmod(0o400)
        seen.add(normalized)
if seen != set(expected):
    raise SystemExit("Python runtime wheel archive is incomplete")
PY
  cmp -s -- "$artifact_tree/backend/requirements.lock" \
    "$supply_root/$PYTHON_RUNTIME_REQUIREMENTS_NAME" \
    || die "Python runtime supply lock differs from approved source"
  printf '%s\n' "$supply_root" >"$work_dir/python-runtime-supply.path"
  printf '%s\n' "$artifact_tree"
}

PROMETHEUS_NETWORK_NAME=""
PROMETHEUS_DOCKER_GATEWAY=""
PROMETHEUS_DOCKER_SUBNET=""

validate_prometheus_network_values() {
  local gateway="$1"
  local subnet="$2"
  "$PYTHON_BASE" -I -S - "$gateway" "$subnet" <<'PY'
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
      "$PYTHON_BASE" -I -S -c '
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
      "$PYTHON_BASE" -I -S -c '
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
  "$PYTHON_BASE" -I -S - "$PROMETHEUS_HOST_CONFIG" "$PROMETHEUS_CONTAINER_SCRAPE_ROOT/*.yml" <<'PY'
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
  "$PYTHON_BASE" -I -S -c '
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
  local supply_root="$3"
  local unit_source
  rm -rf -- "$stage_root"
  mkdir -p "$stage_root/systemd"
  local -a unit_sources=(
    "ops/systemd/unihub-backend.service"
    "unihub-worker.service"
    "ops/systemd/unihub-import-worker.service"
    "ops/systemd/unihub-grile-worker.service"
    "ops/systemd/unihub-export-worker.service"
    "ops/systemd/unihub-salary-export-worker.service"
    "ops/systemd/unihub-legacy-worker.service"
    "ops/systemd/unihub-retail-migrate.service"
  )
  for unit_source in "${unit_sources[@]}"; do
    [[ -f "$artifact_tree/$unit_source" && ! -L "$artifact_tree/$unit_source" ]] \
      || die "runtime artifact unit is missing: $unit_source"
    install -m 0644 -- "$artifact_tree/$unit_source" "$stage_root/systemd/$(basename "$unit_source")"
  done
  assert_unit_identity() {
    local unit="$1"
    local user="$2"
    local group="$3"
    local supplementary="$4"
    local umask="$5"
    [[ "$(grep -Ec '^User=' "$unit")" -eq 1 && "$(grep -Fxc "User=$user" "$unit")" -eq 1 ]] \
      || die "runtime unit has an invalid service user: $(basename "$unit")"
    [[ "$(grep -Ec '^Group=' "$unit")" -eq 1 && "$(grep -Fxc "Group=$group" "$unit")" -eq 1 ]] \
      || die "runtime unit has an invalid primary group: $(basename "$unit")"
    if [[ -n "$supplementary" ]]; then
      [[ "$(grep -Ec '^SupplementaryGroups=' "$unit")" -eq 1 \
        && "$(grep -Fxc "SupplementaryGroups=$supplementary" "$unit")" -eq 1 ]] \
        || die "runtime unit has invalid supplementary groups: $(basename "$unit")"
    else
      ! grep -Eq '^SupplementaryGroups=' "$unit" \
        || die "runtime unit has unexpected supplementary groups: $(basename "$unit")"
    fi
    [[ "$(grep -Ec '^UMask=' "$unit")" -eq 1 && "$(grep -Fxc "UMask=$umask" "$unit")" -eq 1 ]] \
      || die "runtime unit has an invalid umask: $(basename "$unit")"
  }
  assert_unit_identity "$stage_root/systemd/unihub-backend.service" \
    unihub-web unihub-web \
    "unihub-import-spool unihub-promo-artifacts unihub-grile-artifacts unihub-export-artifacts" 0007
  assert_unit_identity "$stage_root/systemd/unihub-worker.service" \
    unihub-operations unihub-operations "" 0077
  assert_unit_identity "$stage_root/systemd/unihub-import-worker.service" \
    unihub-import unihub-import "unihub-import-spool unihub-promo-artifacts" 0007
  assert_unit_identity "$stage_root/systemd/unihub-grile-worker.service" \
    unihub-grile unihub-grile "unihub-operations unihub-grile-artifacts" 0007
  assert_unit_identity "$stage_root/systemd/unihub-export-worker.service" \
    unihub-export unihub-export "unihub-operations unihub-export-artifacts" 0007
  assert_unit_identity "$stage_root/systemd/unihub-salary-export-worker.service" \
    unihub-salary-export unihub-salary-export "unihub-export-artifacts" 0007
  assert_unit_identity "$stage_root/systemd/unihub-retail-migrate.service" \
    unihub-migrate unihub-migrate "" 0077
  local worker_unit
  for worker_unit in unihub-worker.service unihub-import-worker.service unihub-grile-worker.service \
    unihub-export-worker.service unihub-salary-export-worker.service; do
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
      "$stage_root/systemd/unihub-salary-export-worker.service" \
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
  "$PYTHON_BASE" -I -S - "$fragment_source" "$stage_root/unihub-retail.yml" "$PROMETHEUS_DOCKER_GATEWAY" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
token = "__PROMETHEUS_DOCKER_GATEWAY__"
if source.count(token) != 6:
    raise SystemExit("Retail scrape template must contain exactly six gateway placeholders")
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

  [[ -d "$supply_root" && ! -L "$supply_root" \
    && -d "$supply_root/wheels" && ! -L "$supply_root/wheels" ]] \
    || die "verified Python runtime supply is missing"
  cp -a -- "$supply_root" "$stage_root/python-runtime-supply"
}

runtime_asset_destinations() {
  printf '%s\n' \
    "$SYSTEMD_ROOT/unihub-backend.service" \
    "$SYSTEMD_ROOT/unihub-worker.service" \
    "$SYSTEMD_ROOT/unihub-import-worker.service" \
    "$SYSTEMD_ROOT/unihub-grile-worker.service" \
    "$SYSTEMD_ROOT/unihub-export-worker.service" \
    "$SYSTEMD_ROOT/unihub-salary-export-worker.service" \
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
  atomic_symlink "$release_root/systemd/unihub-salary-export-worker.service" "$SYSTEMD_ROOT/unihub-salary-export-worker.service"
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

python_runtime_tree_digest() {
  local venv_root="$1"
  "$PYTHON_BASE" -I -S - "$venv_root" <<'PY'
import hashlib
import json
import pathlib
import sys

site = pathlib.Path(sys.argv[1]) / "lib/python3.12/site-packages"
if not site.is_dir() or site.is_symlink():
    raise SystemExit("Python runtime site-packages is unavailable or unsafe")

def stable(path: pathlib.Path) -> bytes:
    payload = path.read_bytes()
    if path.name != "RECORD":
        return payload
    lines = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if len(fields) != 3:
            raise SystemExit("installed Python RECORD is not canonical CSV")
        if fields[0].startswith("../../../bin/"):
            continue
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()

entries = [
    [str(path.relative_to(site)), hashlib.sha256(stable(path)).hexdigest()]
    for path in sorted(site.rglob("*"))
    if path.is_file() and not path.is_symlink() and path.suffix != ".pyc"
]
print(hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest())
PY
}

verify_runtime_venv() {
  local venv_root="$1"
  local supply_root="$2"
  local expected_path="$3"
  local evidence_path="${4:-}"
  local staged="${5:-0}"
  [[ "$staged" == "0" || "$staged" == "1" || "$staged" == "2" ]] \
    || die "invalid Python runtime location mode"
  "$PYTHON_BASE" -I -S - \
    "$venv_root" "$supply_root" "$expected_path" \
    "$PYTHON_BASE" "$PYTHON_BASE_SHA256" "$PYTHON_VERSION" \
    "$SYSTEM_SITECUSTOMIZE" "$SYSTEM_SITECUSTOMIZE_RESOLVED" \
    "$SYSTEM_SITECUSTOMIZE_SHA256" "$PYTHON_RUNTIME_TREE_PROPERTY" \
    "$evidence_path" "$staged" <<'PY'
import base64
import hashlib
import importlib.metadata
import json
import pathlib
import re
import sys

(
    venv_value,
    supply_value,
    expected_path_value,
    python_value,
    python_sha256,
    python_version,
    sitecustomize_value,
    sitecustomize_resolved_value,
    sitecustomize_sha256,
    tree_property,
    evidence_value,
    staged_value,
) = sys.argv[1:]
venv = pathlib.Path(venv_value)
supply = pathlib.Path(supply_value)
expected_path = pathlib.Path(expected_path_value)
python = pathlib.Path(python_value)
sitecustomize = pathlib.Path(sitecustomize_value)
sitecustomize_resolved = pathlib.Path(sitecustomize_resolved_value)
requirements = supply / "PYTHON_RUNTIME_REQUIREMENTS.lock"
supply_manifest = supply / "PYTHON_RUNTIME_SUPPLY.json"
sbom_path = supply / "SBOM.python.cdx.json"
site = venv / "lib/python3.12/site-packages"
bin_dir = venv / "bin"
config_path = venv / "pyvenv.cfg"
if (
    not venv.is_dir()
    or venv.is_symlink()
    or not site.is_dir()
    or site.is_symlink()
    or not bin_dir.is_dir()
    or bin_dir.is_symlink()
    or not config_path.is_file()
    or config_path.is_symlink()
    or any(not path.is_file() or path.is_symlink() for path in (requirements, supply_manifest, sbom_path))
):
    raise SystemExit("Python runtime verification inputs are unsafe")
if expected_path.is_symlink():
    raise SystemExit("Python runtime canonical path is a symlink")
if staged_value == "0" and venv.resolve() != expected_path:
    raise SystemExit("Python runtime is not installed at its canonical non-symlink path")
if staged_value == "1" and venv.parent.resolve() != expected_path.parent.resolve():
    raise SystemExit("Python runtime staging path is outside the canonical filesystem boundary")
if (
    not python.is_file()
    or python.is_symlink()
    or hashlib.sha256(python.read_bytes()).hexdigest() != python_sha256
    or not sitecustomize.is_file()
    or sitecustomize.resolve() != sitecustomize_resolved
    or sitecustomize_resolved.is_symlink()
    or hashlib.sha256(sitecustomize.read_bytes()).hexdigest() != sitecustomize_sha256
):
    raise SystemExit("Python runtime base identity mismatch")
config = {
    key.strip().lower(): value.strip()
    for line in config_path.read_text(encoding="utf-8").splitlines()
    if "=" in line
    for key, value in (line.split("=", 1),)
}
expected_config = {
    "home": "/usr/bin",
    "include-system-site-packages": "false",
    "version": python_version,
    "executable": str(python),
    "command": f"{python} -m venv {expected_path}",
}
if config != expected_config:
    raise SystemExit("Python runtime pyvenv.cfg identity mismatch")

expected_interpreter_links = {
    venv / "bin/python": pathlib.Path("python3.12"),
    venv / "bin/python3": pathlib.Path("python3.12"),
    venv / "bin/python3.12": python,
}
for link, target in expected_interpreter_links.items():
    if (
        not link.is_symlink()
        or link.readlink() != target
        or link.resolve(strict=True) != python
    ):
        raise SystemExit(f"Python runtime interpreter link is invalid: {link.name}")
if set(bin_dir.iterdir()) != set(expected_interpreter_links):
    raise SystemExit("Python runtime bin inventory is not interpreter-only")

canonical = lambda value: re.sub(r"[-_.]+", "-", value).lower()
expected = {}
for raw in requirements.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;\\]+)", raw)
    if match:
        name = canonical(match.group(1))
        if name in expected:
            raise SystemExit("duplicate Python runtime lock distribution")
        expected[name] = match.group(2)
if not expected:
    raise SystemExit("Python runtime lock is empty")
dists = {
    canonical(dist.metadata["Name"]): dist
    for dist in importlib.metadata.distributions(path=[str(site)])
    if dist.metadata.get("Name")
}
versions = {name: dist.version for name, dist in dists.items()}
manifest = json.loads(supply_manifest.read_text(encoding="utf-8"))
bootstrap = manifest.get("bootstrapDistributions")
if not isinstance(bootstrap, dict) or versions != expected | bootstrap:
    raise SystemExit("Python runtime distribution inventory mismatch")

claimed = set()
record_failures = []
for name, dist in sorted(dists.items()):
    files = tuple(dist.files or ())
    if not files or not any(pathlib.Path(str(file)).name == "RECORD" for file in files):
        record_failures.append(f"{name}:missing_RECORD")
        continue
    for file in files:
        target = pathlib.Path(dist.locate_file(file))
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError):
            record_failures.append(f"{name}:{file}:missing_or_unsafe")
            continue
        if target.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(venv.resolve()):
            record_failures.append(f"{name}:{file}:outside_or_symlink")
            continue
        if resolved.is_relative_to(site.resolve()):
            claimed.add(resolved)
        if file.hash is None:
            if pathlib.Path(str(file)).name != "RECORD":
                record_failures.append(f"{name}:{file}:unhashed")
            continue
        if file.hash.mode != "sha256":
            record_failures.append(f"{name}:{file}:unsupported_hash")
            continue
        actual = base64.urlsafe_b64encode(hashlib.sha256(resolved.read_bytes()).digest()).decode().rstrip("=")
        if actual != file.hash.value:
            record_failures.append(f"{name}:{file}:hash_mismatch")
pyc = [path for path in site.rglob("*.pyc") if path.is_file()]
allowed_symlinks = set(expected_interpreter_links)
symlinks = [
    path for path in venv.rglob("*")
    if path.is_symlink() and path not in allowed_symlinks
]
unowned = [
    path for path in site.rglob("*")
    if path.is_file() and not path.is_symlink() and path.resolve() not in claimed
]
if record_failures or pyc or symlinks or unowned:
    raise SystemExit(
        f"Python runtime tree is unsafe: record={record_failures[:5]}, "
        f"pyc={len(pyc)}, symlinks={len(symlinks)}, unowned={len(unowned)}"
    )

def stable(path: pathlib.Path) -> bytes:
    payload = path.read_bytes()
    if path.name != "RECORD":
        return payload
    lines = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if len(fields) != 3:
            raise SystemExit("installed Python RECORD is not canonical CSV")
        if fields[0].startswith("../../../bin/"):
            continue
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()

entries = [
    [str(path.relative_to(site)), hashlib.sha256(stable(path)).hexdigest()]
    for path in sorted(site.rglob("*"))
    if path.is_file() and not path.is_symlink() and path.suffix != ".pyc"
]
tree = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
tree_values = [
    str(item.get("value", ""))
    for item in sbom.get("metadata", {}).get("properties", [])
    if isinstance(item, dict) and item.get("name") == tree_property
]
if len(tree_values) != 1 or tree != tree_values[0] or manifest.get("sitePackages", {}).get("sha256") != tree:
    raise SystemExit("Python runtime tree differs from signed SBOM")
payload = {
    "schemaVersion": 1,
    "path": str(expected_path),
    "pythonSha256": python_sha256,
    "requirementsSha256": hashlib.sha256(requirements.read_bytes()).hexdigest(),
    "sbomSha256": hashlib.sha256(sbom_path.read_bytes()).hexdigest(),
    "sitePackagesTreeSha256": tree,
    "distributionCount": len(versions),
    "sitePackagesFileCount": len(entries),
}
if evidence_value:
    pathlib.Path(evidence_value).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
print(tree)
PY
}

stage_runtime_venv() {
  local supply_root="$1"
  local stage_path="$2"
  local canonical_path="$LIVE_ROOT/backend/venv"
  verify_python_base
  [[ ! -e "$stage_path" && ! -L "$stage_path" ]] \
    || die "Python runtime staging path already exists"
  [[ "$(stat -c %d "$(dirname "$stage_path")")" == "$(stat -c %d "$LIVE_ROOT/backend")" ]] \
    || die "Python runtime staging and live path must share a filesystem"
  "$PYTHON_BASE" -I -m venv "$stage_path"
  env -i \
    PATH=/usr/bin:/bin \
    LANG=C.UTF-8 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    "$stage_path/bin/python" -B -I -m pip install \
      --disable-pip-version-check --no-index \
      --find-links "$supply_root/wheels" --no-compile --require-hashes \
      -r "$supply_root/$PYTHON_RUNTIME_REQUIREMENTS_NAME"
  env -i \
    PATH=/usr/bin:/bin \
    LANG=C.UTF-8 \
    PYTHONNOUSERSITE=1 \
    PYTHONSAFEPATH=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    "$stage_path/bin/python" -B -I -m pip check
  "$PYTHON_BASE" -I -S - "$stage_path" "$canonical_path" <<'PY'
import csv
import io
import pathlib
import sys

stage = pathlib.Path(sys.argv[1])
canonical = pathlib.Path(sys.argv[2])
config_path = stage / "pyvenv.cfg"
text = config_path.read_text(encoding="utf-8")
lines = []
found = 0
for line in text.splitlines():
    if line.lower().startswith("command ="):
        lines.append(f"command = /usr/bin/python3.12 -m venv {canonical}")
        found += 1
    else:
        lines.append(line)
if found != 1:
    raise SystemExit("Python runtime pyvenv.cfg command is missing or duplicated")
config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
# The production runtime invokes modules through the three pinned interpreter
# links only. Remove path-bound console scripts and their RECORD rows so no
# unsigned executable surface remains under venv/bin.
site = stage / "lib/python3.12/site-packages"
for record in sorted(site.glob("*.dist-info/RECORD")):
    rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    kept = []
    for row in rows:
        if len(row) != 3:
            raise SystemExit(f"non-canonical RECORD row: {record.name}")
        if not row[0].startswith("../../../bin/"):
            kept.append(row)
    if kept != rows:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerows(kept)
        record.write_text(buffer.getvalue(), encoding="utf-8")
for entry in (stage / "bin").iterdir():
    if entry.is_file() and not entry.is_symlink():
        entry.unlink()
PY
  find "$stage_path" -type f -name '*.pyc' -delete
  find "$stage_path" -depth -type d -name __pycache__ -empty -delete
  if [[ -L "$stage_path/lib64" ]]; then
    [[ "$(readlink -- "$stage_path/lib64")" == "lib" ]] \
      || die "Python runtime lib64 link is non-canonical"
    unlink -- "$stage_path/lib64"
  elif [[ -e "$stage_path/lib64" ]]; then
    die "Python runtime lib64 entry is non-canonical"
  fi
  find "$stage_path" -type d -exec chmod 0755 {} +
  find "$stage_path" -type f -exec chmod 0644 {} +
  find "$stage_path/bin" -type f -exec chmod 0755 {} +
  if [[ "$TEST_MODE" != "1" ]]; then
    chown -R root:root "$stage_path"
  fi
  verify_runtime_venv "$stage_path" "$supply_root" "$canonical_path" "" 1
}

switch_runtime_venv() {
  local staged_venv="$1"
  local backup_dir="$2"
  local current_venv="$LIVE_ROOT/backend/venv"
  local prior_venv="$backup_dir/venv.pre-switch"
  [[ -d "$staged_venv" && ! -L "$staged_venv" ]] \
    || die "staged Python runtime is unavailable or unsafe"
  [[ -d "$current_venv" && ! -L "$current_venv" ]] \
    || die "current Python runtime is unavailable or unsafe"
  [[ ! -e "$prior_venv" && ! -L "$prior_venv" ]] \
    || die "Python runtime switch backup already exists"
  mv --no-copy -- "$current_venv" "$prior_venv"
  if [[ "$TEST_MODE" == "1" && "$TEST_FAIL_PHASE" == "venv_after_old_move" ]]; then
    die "TEST Python runtime failure after old runtime move"
  fi
  mv --no-copy -- "$staged_venv" "$current_venv"
  if [[ "$TEST_MODE" == "1" && "$TEST_FAIL_PHASE" == "venv_after_swap" ]]; then
    die "TEST Python runtime failure after new runtime swap"
  fi
}

backup_runtime_venv_identity() {
  local backup_dir="$1"
  local live_venv="$LIVE_ROOT/backend/venv"
  local evidence="$backup_dir/venv-before.json"
  local live_supply="$backup_dir/python-runtime-supply.old"
  local current_sha current_supply
  current_sha="$(git_service rev-parse HEAD)"
  current_supply="$RUNTIME_RELEASE_BASE/$current_sha/python-runtime-supply"
  [[ -d "$live_venv" && ! -L "$live_venv" ]] \
    || die "current Python runtime is unavailable or unsafe"
  mkdir -p "$live_supply"
  if [[ -f "$LIVE_ROOT/backend/requirements.lock" ]]; then
    cp -- "$LIVE_ROOT/backend/requirements.lock" "$live_supply/$PYTHON_RUNTIME_REQUIREMENTS_NAME"
  fi
  # A legacy pre-contract venv is accepted as an opaque rollback asset; all
  # contract-managed handles additionally bind the signed tree below.
  if [[ -d "$RUNTIME_RELEASE_BASE/$current_sha" && ! -L "$RUNTIME_RELEASE_BASE/$current_sha" \
    && ! -f "$current_supply/PYTHON_RUNTIME_SUPPLY.json" ]]; then
    die "contract-managed current release is missing its signed Python runtime supply"
  fi
  if [[ -f "$current_supply/PYTHON_RUNTIME_SUPPLY.json" ]]; then
    cp -a -- "$current_supply/." "$live_supply/"
    verify_runtime_venv "$live_venv" "$live_supply" "$live_venv" "$evidence"
  else
    "$PYTHON_BASE" -I -S - "$live_venv" "$evidence" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
if not root.is_dir() or root.is_symlink():
    raise SystemExit("legacy Python runtime backup source is unsafe")
entries = []
for path in sorted(root.rglob("*")):
    if path.is_symlink():
        entries.append([str(path.relative_to(root)), "symlink", path.readlink().as_posix()])
    elif path.is_file():
        entries.append([str(path.relative_to(root)), "file", hashlib.sha256(path.read_bytes()).hexdigest()])
digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
pathlib.Path(sys.argv[2]).write_text(
    json.dumps({"schemaVersion": 1, "legacyOpaque": True, "treeSha256": digest}, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
  fi
  chmod 0600 "$evidence"
}

verify_legacy_runtime_venv_identity() {
  local venv_root="$1"
  local evidence="$2"
  "$PYTHON_BASE" -I -S - "$venv_root" "$evidence" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
evidence_path = pathlib.Path(sys.argv[2])
if (
    not root.is_dir()
    or root.is_symlink()
    or not evidence_path.is_file()
    or evidence_path.is_symlink()
):
    raise SystemExit("legacy Python runtime rollback inputs are unsafe")
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
if set(evidence) != {"schemaVersion", "legacyOpaque", "treeSha256"} or evidence.get("schemaVersion") != 1 or evidence.get("legacyOpaque") is not True:
    raise SystemExit("legacy Python runtime rollback evidence is invalid")
entries = []
for path in sorted(root.rglob("*")):
    if path.is_symlink():
        entries.append([str(path.relative_to(root)), "symlink", path.readlink().as_posix()])
    elif path.is_file():
        entries.append([str(path.relative_to(root)), "file", hashlib.sha256(path.read_bytes()).hexdigest()])
digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
if digest != evidence.get("treeSha256"):
    raise SystemExit("legacy Python runtime rollback identity mismatch")
PY
}

preflight_runtime_venv_restore() {
  local backup_dir="$1"
  local current_venv="$LIVE_ROOT/backend/venv"
  local prior_venv="$backup_dir/venv.pre-switch"
  local evidence="$backup_dir/venv-before.json"
  local old_supply="$backup_dir/python-runtime-supply.old"
  local candidate mode generated
  [[ -f "$evidence" && ! -L "$evidence" ]] \
    || die "rollback Python runtime evidence is unavailable or unsafe"
  if [[ -d "$prior_venv" && ! -L "$prior_venv" ]]; then
    candidate="$prior_venv"
  elif [[ -d "$current_venv" && ! -L "$current_venv" ]]; then
    candidate="$current_venv"
  else
    die "rollback Python runtime backup is unavailable or unsafe"
  fi
  mode="$("$PYTHON_BASE" -I -S - "$evidence" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
if not path.is_file() or path.is_symlink():
    raise SystemExit("rollback Python runtime evidence is unsafe")
payload = json.loads(path.read_text(encoding="utf-8"))
if payload.get("schemaVersion") != 1:
    raise SystemExit("rollback Python runtime evidence schema is invalid")
print("legacy" if payload.get("legacyOpaque") is True else "managed")
PY
)"
  if [[ "$mode" == "legacy" ]]; then
    verify_legacy_runtime_venv_identity "$candidate" "$evidence"
    return
  fi
  [[ "$mode" == "managed" ]] || die "rollback Python runtime evidence mode is invalid"
  [[ -d "$old_supply" && ! -L "$old_supply" \
    && -f "$old_supply/PYTHON_RUNTIME_SUPPLY.json" \
    && ! -L "$old_supply/PYTHON_RUNTIME_SUPPLY.json" ]] \
    || die "managed rollback Python runtime supply is unavailable or unsafe"
  generated="$(mktemp "$backup_dir/.venv-restore-preflight.XXXXXX")"
  if ! verify_runtime_venv \
    "$candidate" "$old_supply" "$current_venv" "$generated" 2 >/dev/null; then
    rm -f -- "$generated"
    die "managed rollback Python runtime verification failed"
  fi
  if ! cmp -s -- "$generated" "$evidence"; then
    rm -f -- "$generated"
    die "managed rollback Python runtime evidence mismatch"
  fi
  rm -f -- "$generated"
}

restore_runtime_venv() {
  local backup_dir="$1"
  local current_venv="$LIVE_ROOT/backend/venv"
  local prior_venv="$backup_dir/venv.pre-switch"
  local failed_venv
  preflight_runtime_venv_restore "$backup_dir"
  failed_venv="$backup_dir/venv.failed.$(date -u +%Y%m%dT%H%M%SZ)"
  if [[ -d "$prior_venv" && ! -L "$prior_venv" ]]; then
    if [[ -e "$current_venv" || -L "$current_venv" ]]; then
      mv --no-copy -- "$current_venv" "$failed_venv"
    fi
    mv --no-copy -- "$prior_venv" "$current_venv"
  elif [[ ! -d "$current_venv" || -L "$current_venv" ]]; then
    die "rollback Python runtime backup is unavailable or unsafe"
  fi
  preflight_runtime_venv_restore "$backup_dir"
}

check_prometheus_config() {
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST Prometheus config check"
    [[ ! -e "$PROMETHEUS_FRAGMENT" ]] && return 0
    if grep -Eq '__PROMETHEUS_DOCKER_GATEWAY__|0\.0\.0\.0|127\.0\.0\.1' "$PROMETHEUS_FRAGMENT"; then
      return 1
    fi
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
    if "$PYTHON_BASE" -I -S -c '
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
' unihub-retail-web unihub-retail-operations unihub-retail-imports unihub-retail-grile \
    unihub-retail-exports unihub-retail-salary-exports <<<"$payload"
    then
      return 0
    fi
    sleep 2
  done
  return 1
}

verify_prometheus_recording_series() {
  if [[ "$TEST_MODE" == "1" ]]; then
    test "$(grep -c '^      - record: unihub_retail:' "$PROMETHEUS_RETAIL_RULES")" -eq 4
    return
  fi
  local attempt payload
  for attempt in {1..30}; do
    curl --silent --output /dev/null --max-time 2 \
      http://127.0.0.1:9898/api/dashboard/all || true
    payload="$(curl --silent --show-error --fail --max-time 5 --get \
      --data-urlencode 'query=count({__name__=~"unihub_retail:(http_requests_excluding_probes|http_5xx_ratio|http_latency_p95_seconds|dashboard_latency_p95_seconds):rate5m"}) by (__name__)' \
      http://127.0.0.1:9090/api/v1/query)" || payload=""
    if "$PYTHON_BASE" -I -S -c '
import json
import sys

required = {
    "unihub_retail:http_requests_excluding_probes:rate5m",
    "unihub_retail:http_5xx_ratio:rate5m",
    "unihub_retail:http_latency_p95_seconds:rate5m",
    "unihub_retail:dashboard_latency_p95_seconds:rate5m",
}
result = json.load(sys.stdin).get("data", {}).get("result", [])
present = {item.get("metric", {}).get("__name__") for item in result}
if not required <= present:
    raise SystemExit(1)
' <<<"$payload"
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
    unihub-salary-export-worker.service
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
  local old_sha state work_dir artifact_tree next_dist failed_dist prior_link prior_approval_id stage_root supply_root staged_venv

  old_sha="$(read_manifest_value "$manifest" OLD_SHA)"
  state="$(read_manifest_value "$manifest" STATE)"
  validate_sha "$old_sha"
  [[ "$(read_manifest_value "$manifest" NEW_SHA)" == "$expected_sha" ]] || die "recovery manifest SHA mismatch"
  [[ "$state" == "recovery_required" ]] || die "deploy record is not recovery-required"

  local approval_claimed=0
  local runtime_transition_started=0
  local recovery_owner_pid="$BASHPID"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-forward-recovery.XXXXXX")"
  on_recovery_error() {
    local rc=$?
    if [[ "$BASHPID" != "$recovery_owner_pid" ]]; then
      trap - ERR EXIT
      exit "$rc"
    fi
    trap - EXIT ERR
    if [[ "$runtime_transition_started" == "1" ]]; then
      stop_runtime || true
      log "forward recovery runtime remains stopped after an incomplete transition"
    fi
    clear_planned_deployment || true
    log "forward recovery failed; release remains recovery_required and requires a fresh one-time approval"
    if [[ "$approval_claimed" == "1" && -n "$APPROVAL_CLAIM" ]]; then
      finalize_approval failed "$backup_dir" || true
    fi
    if [[ -n "${staged_venv:-}" && "$staged_venv" == "$LIVE_ROOT/backend/.venv."* \
      && -d "$staged_venv" && ! -L "$staged_venv" ]]; then
      rm -rf -- "$staged_venv"
    fi
    rm -rf -- "$work_dir"
    exit "$rc"
  }
  trap on_recovery_error ERR
  trap on_recovery_error EXIT

  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
  approval_claimed=1
  claim_approval "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  supply_root="$(<"$work_dir/python-runtime-supply.path")"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root" "$supply_root"
  staged_venv="$LIVE_ROOT/backend/.venv.${expected_sha}.recovery.$$.${RANDOM}"
  stage_runtime_venv "$supply_root" "$staged_venv"
  next_dist="$backup_dir/dist.recovery.next"
  rm -rf -- "$next_dist"
  mkdir -p "$next_dist"
  cp -a "$artifact_tree/dist/." "$next_dist/"
  set_frontend_permissions "$next_dist"
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
  preflight_runtime_venv_restore "$backup_dir"
  runtime_transition_started=1
  stop_runtime
  restore_runtime_venv "$backup_dir"
  switch_runtime_venv "$staged_venv" "$backup_dir"
  apply_runtime_identity_filesystem
  verify_runtime_identity_filesystem
  install_runtime_assets "$stage_root" "$expected_sha"
  verify_runtime_venv \
    "$LIVE_ROOT/backend/venv" \
    "$RUNTIME_RELEASE_BASE/$expected_sha/python-runtime-supply" \
    "$LIVE_ROOT/backend/venv"
  if ! diff -qr -- "$LIVE_ROOT/dist" "$next_dist" >/dev/null; then
    failed_dist="$backup_dir/dist.recovery.failed.$(date -u +%Y%m%dT%H%M%SZ)"
    mv -- "$LIVE_ROOT/dist" "$failed_dist"
    mv -- "$next_dist" "$LIVE_ROOT/dist"
  else
    rm -rf -- "$next_dist"
  fi
  set_frontend_permissions "$LIVE_ROOT/dist"
  normalize_tracked_source_permissions
  run_migrations
  start_runtime
  verify_local_health
  reload_prometheus
  verify_prometheus_targets
  verify_prometheus_recording_series
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
  set_frontend_permissions "$next_dist"
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
  set_frontend_permissions "$LIVE_ROOT/dist"
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

upgrade_promo_generation() {
  if [[ "$TEST_MODE" == "1" ]]; then
    log "TEST promo generation ownership upgrade"
    return
  fi
  local script="$LIVE_ROOT/backend/scripts/migrate_promo_generation_v1_to_v2.py"
  local python="$LIVE_ROOT/backend/venv/bin/python"
  [[ -f "$script" && ! -L "$script" && -x "$python" ]] \
    || die "promo generation migration runtime is unavailable"
  local -a command=(
    /usr/bin/env -i
    PATH=/usr/bin:/bin
    PYTHONNOUSERSITE=1
    PYTHONSAFEPATH=1
    PYTHONDONTWRITEBYTECODE=1
    "$python" -B -I "$script"
    --data-dir "$LIVE_ROOT/data"
  )
  sudo --non-interactive -u "$IMPORT_FILE_USER" -- "${command[@]}" --apply
  local result
  result="$(sudo --non-interactive -u "$IMPORT_FILE_USER" -- "${command[@]}")"
  [[ "$result" == promo-v1-v2:\ status=already_v2* ]] \
    || die "promo generation ownership verification failed"
  log "promo generation ownership verified"
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
  preflight_runtime_venv_restore "$backup_dir"
  stop_runtime || true
  restore_runtime_venv "$backup_dir"
  git_service reset --hard "$old_sha"
  normalize_tracked_source_permissions
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
  verify_python_base
  assert_live_checkout
  assert_worktree_safe
  verify_runtime_identity_prerequisites

  local old_sha stamp backup_dir work_dir artifact_tree backup_started next_dist backup_nonce stage_root supply_root staged_venv
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
    verify_runtime_venv \
      "$LIVE_ROOT/backend/venv" \
      "$RUNTIME_RELEASE_BASE/$expected_sha/python-runtime-supply" \
      "$LIVE_ROOT/backend/venv"
    verify_runtime_identity_filesystem
    verify_tracked_source_permissions
    verify_frontend_permissions "$LIVE_ROOT/dist"
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
  local deploy_owner_pid="$BASHPID"
  on_deploy_error() {
    local rc=$?
    if [[ "$BASHPID" != "$deploy_owner_pid" ]]; then
      trap - ERR EXIT
      exit "$rc"
    fi
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
    if [[ -n "${staged_venv:-}" && "$staged_venv" == "$LIVE_ROOT/backend/.venv."* \
      && -d "$staged_venv" && ! -L "$staged_venv" ]]; then
      rm -rf -- "$staged_venv"
    fi
    exit "$rc"
  }
  # ERR performs rollback while deploy_release locals are still in scope.
  # EXIT is the fail-safe for explicit exits (for example, validation via die).
  # The handler clears both traps before cleanup, so it can run only once.
  trap on_deploy_error ERR
  trap on_deploy_error EXIT

  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
  approval_claimed=1
  claim_approval "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  supply_root="$(<"$work_dir/python-runtime-supply.path")"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root" "$supply_root"
  staged_venv="$LIVE_ROOT/backend/.venv.${expected_sha}.staged.$$.${RANDOM}"
  stage_runtime_venv "$supply_root" "$staged_venv"
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
  backup_runtime_venv_identity "$backup_dir"
  rollback_needed=1

  runtime_touched=1
  mark_planned_deployment
  wait_for_planned_deployment_inhibition \
    || die "planned deployment inhibition did not become active"
  stop_runtime
  switch_runtime_venv "$staged_venv" "$backup_dir"
  apply_runtime_identity_filesystem
  verify_runtime_identity_filesystem
  install_runtime_assets "$stage_root" "$expected_sha"
  verify_runtime_venv \
    "$LIVE_ROOT/backend/venv" \
    "$RUNTIME_RELEASE_BASE/$expected_sha/python-runtime-supply" \
    "$LIVE_ROOT/backend/venv"
  switch_dist "$next_dist" "$backup_dir"
  git_service merge --ff-only "$expected_sha"
  normalize_tracked_source_permissions
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "switched"
  migrations_may_have_applied=1
  run_migrations
  upgrade_promo_generation
  start_runtime
  verify_local_health
  reload_prometheus
  verify_prometheus_targets
  verify_prometheus_recording_series
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
  verify_python_base
  assert_live_checkout
  assert_worktree_safe
  fetch_and_verify_commit "$expected_sha"
  local work_dir artifact_tree artifact_sha256 stage_root supply_root
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-validate.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN
  artifact_sha256="$(sha256sum "$source_archive" | awk '{print $1}')"
  validate_sha256 "$artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$artifact_sha256" "$work_dir")"
  supply_root="$(<"$work_dir/python-runtime-supply.path")"
  [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
    && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
  detect_prometheus_network
  assert_prometheus_shared_include
  stage_root="$work_dir/runtime-release"
  prepare_runtime_release "$artifact_tree" "$stage_root" "$supply_root"
  log "artifact and runtime topology match the approved source without mutation: $expected_sha"
}

bootstrap_entrypoint() {
  local source_release_sha="$1"
  local source_artifact_sha256="$2"
  validate_sha "$source_release_sha"
  validate_sha256 "$source_artifact_sha256"
  [[ "$EUID" -eq 0 || "$TEST_MODE" == "1" ]] \
    || die "deploy entrypoint bootstrap requires root"
  [[ "${SUDO_USER:-}" != "unihub-deploy" ]] \
    || die "deploy runner cannot bootstrap its own privileged entrypoint"
  verify_python_base
  local target backup_root evidence_root new_sha old_sha="" stamp temp backup="" evidence
  if [[ "$TEST_MODE" == "1" ]]; then
    target="$OPS_ROOT/scripts/deploy-retail-artifact.sh"
    backup_root="$OPS_ROOT/backups/retail-deploy-entrypoints"
    evidence_root="$OPS_ROOT/release-evidence/deploy-entrypoint-bootstrap"
  else
    target="/opt/Mobiup/ops/scripts/deploy-retail-artifact.sh"
    backup_root="/opt/Mobiup/ops/backups/retail-deploy-entrypoints"
    evidence_root="/var/lib/unihub-retail-deploy/bootstrap-evidence"
  fi
  [[ -f "$SCRIPT_PATH" && ! -L "$SCRIPT_PATH" ]] \
    || die "bootstrap source must be a regular non-symlink file"
  new_sha="$(sha256sum "$SCRIPT_PATH" | awk '{print $1}')"
  validate_sha256 "$new_sha"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$(dirname "$target")" "$backup_root" "$evidence_root"
  evidence="$evidence_root/${new_sha}.json"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$(dirname "$target")" "$backup_root" "$evidence_root"
    chmod 0755 "$(dirname "$target")"
    chmod 0700 "$backup_root" "$evidence_root"
  fi
  if [[ -e "$target" || -L "$target" ]]; then
    [[ -f "$target" && ! -L "$target" ]] \
      || die "existing deploy entrypoint is unsafe"
    old_sha="$(sha256sum "$target" | awk '{print $1}')"
    if [[ "$old_sha" == "$new_sha" ]]; then
      [[ -f "$evidence" && ! -L "$evidence" ]] \
        || die "idempotent deploy entrypoint bootstrap lacks durable evidence"
      "$PYTHON_BASE" -I -S - "$evidence" "$target" "$new_sha" <<'PY'
import json,pathlib,re,sys
evidence,target,new_sha=sys.argv[1:]
payload=json.loads(pathlib.Path(evidence).read_text(encoding="utf-8"))
if (
    payload.get("schema_version") != 1
    or payload.get("result") != "PASS"
    or payload.get("target") != target
    or payload.get("new_sha256") != new_sha
    or payload.get("root_owned") is not True
    or payload.get("mode") != "0755"
    or re.fullmatch(r"[0-9a-f]{40}", str(payload.get("source_release_sha", ""))) is None
    or re.fullmatch(r"[0-9a-f]{64}", str(payload.get("source_artifact_sha256", ""))) is None
):
    raise SystemExit("durable deploy entrypoint bootstrap evidence is invalid")
PY
      log "root-owned deploy entrypoint already matches durable bootstrap evidence: $new_sha"
      return 0
    fi
    if [[ "$old_sha" != "$new_sha" ]]; then
      backup="$backup_root/${stamp}-${old_sha}.sh"
      [[ ! -e "$backup" && ! -L "$backup" ]] \
        || die "deploy entrypoint backup already exists"
      install -m 0400 -- "$target" "$backup"
      [[ -f "$backup" && ! -L "$backup" \
        && "$(sha256sum "$backup" | awk '{print $1}')" == "$old_sha" ]] \
        || die "deploy entrypoint backup digest mismatch"
      if [[ "$TEST_MODE" != "1" ]]; then
        [[ "$(stat -c '%u:%g:%a' "$backup")" == "0:0:400" ]] \
          || die "deploy entrypoint backup ownership/mode mismatch"
      fi
    fi
  fi
  [[ ! -e "$evidence" && ! -L "$evidence" ]] \
    || die "deploy entrypoint bootstrap evidence already exists"
  temp="$(dirname "$target")/.deploy-retail-artifact.${new_sha}.new.$$"
  [[ ! -e "$temp" && ! -L "$temp" ]] || die "bootstrap temporary path exists"
  install -m 0755 -- "$SCRIPT_PATH" "$temp"
  if [[ "$TEST_MODE" != "1" ]]; then
    chown root:root "$temp"
  fi
  [[ "$(sha256sum "$temp" | awk '{print $1}')" == "$new_sha" ]] \
    || die "bootstrap temporary entrypoint digest mismatch"
  mv -f -- "$temp" "$target"
  [[ "$(sha256sum "$target" | awk '{print $1}')" == "$new_sha" ]] \
    || die "installed deploy entrypoint digest mismatch"
  if [[ "$TEST_MODE" != "1" ]]; then
    [[ "$(stat -c '%u:%g:%a' "$target")" == "0:0:755" ]] \
      || die "installed deploy entrypoint ownership/mode mismatch"
  fi
  "$PYTHON_BASE" -I -S - \
    "$evidence" "$target" "$new_sha" "$old_sha" "$backup" "$stamp" \
    "$source_release_sha" "$source_artifact_sha256" <<'PY'
import json,pathlib,sys
output,target,new_sha,old_sha,backup,installed_at,source_release_sha,source_artifact_sha256=sys.argv[1:]
payload={"schema_version":1,"result":"PASS","target":target,"new_sha256":new_sha,"old_sha256":old_sha or None,"backup_path":backup or None,"installed_at":installed_at,"source_release_sha":source_release_sha,"source_artifact_sha256":source_artifact_sha256,"root_owned":True,"mode":"0755"}
path=pathlib.Path(output)
path.write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
path.chmod(0o600)
PY
  log "root-owned deploy entrypoint bootstrapped: $new_sha"
  log "bootstrap evidence: $evidence"
}

case "${1:-}" in
  bootstrap-entrypoint)
    [[ "$#" -eq 3 ]] \
      || die "usage: $PROGRAM bootstrap-entrypoint <source-sha> <artifact-sha256>"
    bootstrap_entrypoint "$2" "$3"
    ;;
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
