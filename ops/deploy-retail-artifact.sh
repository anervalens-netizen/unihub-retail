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
  LOCK_FILE="/run/lock/unihub-retail-deploy.lock"
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
ALLOWED_UNTRACKED=(
  "docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md"
  "docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md"
)

if [[ "$TEST_MODE" != "1" && "${SUDO_USER:-}" == "unihub-deploy" ]]; then
  [[ "$READ_ONLY_MODE" == "0" && "$#" -eq 4 && "$1" == /* ]] \
    || die "deploy runner may invoke only the four-argument production deployment"
fi

mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
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

required = {"package.json", "backend/main.py", "dist/index.html"}
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
  local line path allowed allowed_path

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    [[ "$line" == "?? "* ]] || die "tracked production change blocks deploy: $line"
    path="${line#\?\? }"
    allowed=0
    for allowed_path in "${ALLOWED_UNTRACKED[@]}"; do
      if [[ "$path" == "$allowed_path" ]]; then
        allowed=1
        break
      fi
    done
    [[ "$allowed" == "1" ]] || die "unexpected untracked production content blocks deploy: $path"
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

copy_and_verify_artifact() {
  local source_archive="$1"
  local expected_sha="$2"
  local expected_artifact_sha256="$3"
  local work_dir="$4"
  local archive_copy="$work_dir/release.tar.gz"
  local artifact_tree="$work_dir/artifact"
  local tested_dist="$work_dir/tested-dist"
  local git_tree="$work_dir/git-tree"

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
  [[ -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
  printf '%s\n' "$artifact_tree"
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
    mv -- "$APPROVAL_CLAIM" "${APPROVAL_CLAIM%.claimed.*}.rejected"
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

preserve_untracked_documents() {
  local backup_dir="$1"
  local path hash
  mkdir -p "$backup_dir/untracked"
  : >"$backup_dir/untracked.sha256"
  for path in "${ALLOWED_UNTRACKED[@]}"; do
    if [[ -f "$LIVE_ROOT/$path" ]]; then
      mkdir -p "$backup_dir/untracked/$(dirname "$path")"
      install -m 0600 -- "$LIVE_ROOT/$path" "$backup_dir/untracked/$path"
      hash="$(sha256sum "$LIVE_ROOT/$path" | awk '{print $1}')"
      [[ "$(sha256sum "$backup_dir/untracked/$path" | awk '{print $1}')" == "$hash" ]] || die "untracked document backup mismatch"
      printf '%s  %s\n' "$hash" "$path" >>"$backup_dir/untracked.sha256"
      rm -- "$LIVE_ROOT/$path"
    fi
  done
}

restore_untracked_documents() {
  local backup_dir="$1"
  local path expected actual
  [[ -f "$backup_dir/untracked.sha256" ]] || return 0
  while read -r expected path; do
    [[ -n "$path" ]] || continue
    [[ -f "$backup_dir/untracked/$path" ]] || die "preserved untracked document is missing"
    mkdir -p "$LIVE_ROOT/$(dirname "$path")"
    if [[ "$TEST_MODE" == "1" ]]; then
      install -m 0600 -- "$backup_dir/untracked/$path" "$LIVE_ROOT/$path"
    else
      install -m 0600 -o "$SERVICE_USER" -g "$SERVICE_GROUP" -- "$backup_dir/untracked/$path" "$LIVE_ROOT/$path"
    fi
    actual="$(sha256sum "$LIVE_ROOT/$path" | awk '{print $1}')"
    [[ "$actual" == "$expected" ]] || die "restored untracked document hash mismatch"
  done <"$backup_dir/untracked.sha256"
}

prepare_tested_dist() {
  local artifact_tree="$1"
  local next_dist="$LIVE_ROOT/.dist.deploy.$$"
  rm -rf -- "$next_dist"
  mkdir -p "$next_dist"
  cp -a "$artifact_tree/dist/." "$next_dist/"
  set_service_ownership "$next_dist"
  [[ -s "$next_dist/index.html" ]] || die "staged frontend is invalid"
  printf '%s\n' "$next_dist"
}

switch_dist() {
  local next_dist="$1"
  [[ -d "$LIVE_ROOT/dist" ]] || die "current frontend directory is missing"
  [[ -s "$next_dist/index.html" ]] || die "staged frontend is invalid"
  mv -- "$LIVE_ROOT/dist" "$2/dist.pre-switch"
  mv -- "$next_dist" "$LIVE_ROOT/dist"
}

backup_current_dist() {
  local backup_dir="$1"
  [[ -d "$LIVE_ROOT/dist" && -s "$LIVE_ROOT/dist/index.html" ]] || die "current frontend is invalid"
  cp -a -- "$LIVE_ROOT/dist" "$backup_dir/dist"
  diff -qr "$LIVE_ROOT/dist" "$backup_dir/dist" >/dev/null || die "frontend backup verification failed"
}

restore_dist() {
  local backup_dir="$1"
  local failed_dist="$backup_dir/dist.failed.$(date -u +%Y%m%dT%H%M%SZ)"
  [[ -d "$backup_dir/dist" ]] || die "rollback frontend backup is missing"
  if [[ -e "$LIVE_ROOT/dist" || -L "$LIVE_ROOT/dist" ]]; then
    mv -- "$LIVE_ROOT/dist" "$failed_dist"
  fi
  mv -- "$backup_dir/dist" "$LIVE_ROOT/dist"
  set_service_ownership "$LIVE_ROOT/dist"
}

stop_runtime() {
  service_action stop "$WORKER_SERVICE" "$BACKEND_SERVICE"
}

start_runtime() {
  service_action restart "$BACKEND_SERVICE" "$WORKER_SERVICE"
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
    [[ -s "$LIVE_ROOT/dist/index.html" ]]
    return
  fi

  local attempt
  for attempt in {1..30}; do
    if systemctl is-active --quiet "$BACKEND_SERVICE" "$WORKER_SERVICE" \
      && curl --silent --show-error --fail --max-time 5 http://127.0.0.1:9898/health >/dev/null \
      && curl --silent --show-error --fail --max-time 5 http://127.0.0.1:9898/readyz >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

rollback_from_backup() {
  local backup_dir="$1"
  local expected_current_sha="$2"
  local old_sha="$3"

  log "rolling back code from $expected_current_sha to $old_sha"
  stop_runtime || true
  git_service reset --hard "$old_sha"
  restore_dist "$backup_dir"
  restore_untracked_documents "$backup_dir"
  start_runtime
  verify_local_health || die "rollback completed but local health failed"
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
  fetch_and_verify_commit "$expected_sha"

  local old_sha stamp backup_dir work_dir artifact_tree backup_started next_dist backup_nonce
  old_sha="$(git_service rev-parse HEAD)"
  [[ "$old_sha" != "$expected_sha" ]] || die "requested SHA is already deployed"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_nonce="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
  backup_dir="$BACKUP_ROOT/${stamp}-${old_sha:0:12}-to-${expected_sha:0:12}-${backup_nonce}"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN

  local documents_preserved=0
  local runtime_touched=0
  local rollback_needed=0
  local approval_claimed=0
  on_deploy_error() {
    local rc=$?
    trap - ERR
    if [[ "$rollback_needed" == "1" ]]; then
      log "deployment failed after switch; starting automatic rollback"
      if ! (rollback_from_backup "$backup_dir" "$expected_sha" "$old_sha"); then
        log "ERROR: automatic rollback did not restore healthy runtime" >&2
      fi
    else
      if [[ "$documents_preserved" == "1" ]]; then
        restore_untracked_documents "$backup_dir" || true
      fi
      if [[ "$runtime_touched" == "1" ]]; then
        start_runtime || true
      fi
    fi
    if [[ "$approval_claimed" == "1" && -n "$APPROVAL_CLAIM" ]]; then
      finalize_approval failed "$backup_dir" || true
    fi
    exit "$rc"
  }
  trap on_deploy_error ERR

  claim_approval "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  approval_claimed=1
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
  ensure_backup_root
  mkdir -p "$backup_dir"
  chmod 0700 "$backup_dir"
  git_service archive --format=tar.gz "$old_sha" >"$backup_dir/source-${old_sha}.tar.gz"
  sha256sum "$backup_dir/source-${old_sha}.tar.gz" >"$backup_dir/source.sha256"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "preparing"
  write_approval_link "$backup_dir" "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
  preserve_untracked_documents "$backup_dir"
  documents_preserved=1
  backup_started="$(date +%s)"
  run_verified_backup "$backup_started"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "backed_up"
  next_dist="$(prepare_tested_dist "$artifact_tree")"
  backup_current_dist "$backup_dir"
  rollback_needed=1

  runtime_touched=1
  stop_runtime
  switch_dist "$next_dist" "$backup_dir"
  git_service merge --ff-only "$expected_sha"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "switched"
  run_migrations
  start_runtime
  verify_local_health
  [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]] || die "deployed Git SHA mismatch"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "deployed"
  finalize_approval consumed "$backup_dir"
  trap - ERR
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
  rollback_from_backup "$backup_dir" "$new_sha" "$old_sha"
}

validate_release() {
  local source_archive="$1"
  local expected_sha="$2"
  validate_sha "$expected_sha"
  assert_live_checkout
  assert_worktree_safe
  fetch_and_verify_commit "$expected_sha"
  local work_dir artifact_tree artifact_sha256
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-validate.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN
  artifact_sha256="$(sha256sum "$source_archive" | awk '{print $1}')"
  validate_sha256 "$artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$artifact_sha256" "$work_dir")"
  [[ -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
  log "artifact matches approved source and contains a tested frontend: $expected_sha"
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
