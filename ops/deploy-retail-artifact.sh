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
  local old_sha state work_dir artifact_tree next_dist failed_dist prior_link prior_approval_id

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

  stop_runtime
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
  verify_public_release
  [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]] || die "recovered Git SHA mismatch"

  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "deployed"
  finalize_approval consumed "$backup_dir"
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
    [[ -f "$LIVE_ROOT/dist/index.html" && ! -L "$LIVE_ROOT/dist/index.html" \
      && -s "$LIVE_ROOT/dist/index.html" ]]
    return
  fi

  local attempt
  for attempt in {1..30}; do
    if systemctl is-active --quiet "$BACKEND_SERVICE" \
      && systemctl is-active --quiet "$WORKER_SERVICE" \
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
  if [[ "$old_sha" == "$expected_sha" ]]; then
    local recovery_handle=""
    if recovery_handle="$(find_retryable_forward_handle "$ci_run_id" "$expected_sha" "$expected_artifact_sha256")"; then
      recover_forward_release \
        "$source_archive" "$expected_sha" "$ci_run_id" \
        "$expected_artifact_sha256" "$recovery_handle"
      return 0
    fi
    verify_completed_deploy_record "$ci_run_id" "$expected_sha" "$expected_artifact_sha256"
    work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-reverify.XXXXXX")"
    trap 'rm -rf -- "$work_dir"' RETURN
    artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$expected_artifact_sha256" "$work_dir")"
    [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
      && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
    diff -qr -- "$LIVE_ROOT/dist" "$artifact_tree/dist" >/dev/null \
      || die "live frontend differs from the tested release artifact"
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
  rollback_needed=1

  runtime_touched=1
  stop_runtime
  switch_dist "$next_dist" "$backup_dir"
  git_service merge --ff-only "$expected_sha"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "switched"
  migrations_may_have_applied=1
  run_migrations
  start_runtime
  verify_local_health
  verify_public_release
  [[ "$(git_service rev-parse HEAD)" == "$expected_sha" ]] || die "deployed Git SHA mismatch"
  write_release_manifest "$backup_dir" "$old_sha" "$expected_sha" "deployed"
  finalize_approval consumed "$backup_dir"
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
  local work_dir artifact_tree artifact_sha256
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-validate.XXXXXX")"
  trap 'rm -rf -- "$work_dir"' RETURN
  artifact_sha256="$(sha256sum "$source_archive" | awk '{print $1}')"
  validate_sha256 "$artifact_sha256"
  artifact_tree="$(copy_and_verify_artifact "$source_archive" "$expected_sha" "$artifact_sha256" "$work_dir")"
  [[ -f "$artifact_tree/dist/index.html" && ! -L "$artifact_tree/dist/index.html" \
    && -s "$artifact_tree/dist/index.html" ]] || die "tested frontend artifact is missing"
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
