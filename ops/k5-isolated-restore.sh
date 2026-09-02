#!/usr/bin/env bash
# Canonical isolated-only DR restore exercise entrypoint for UniHub Retail.
#
# This script is NOT a production restore command. It requires an explicit
# immutable backup generation and source release, restores only into disposable
# local targets, never runs migrations, emits sanitized evidence, and cleans up.
#
# RPO timestamp authority contract (future-safe):
#   Backup start/completion are derived EXCLUSIVELY from the per-generation
#   metadata artifact <backup-root>/manifests/generation_<stamp>.result.
#   The required metadata keys are: stamp, status (exactly "verified"),
#   started_at, completed_at, file_count. Timestamps must carry an explicit
#   UTC offset and are canonicalized to YYYY-MM-DDTHH:MM:SSZ before any
#   downstream use. Rolling last-run metadata, filesystem mtimes, log lines
#   and filename inference are never used as RPO authority. Persisting
#   per-generation timing into the external backup contract is tracked
#   separately (GitHub issue #251); until that ships, historical generations
#   without per-generation timing metadata simply cannot be exercised.
#
# Provenance: the weekly restore-mechanics helper recovered during K5 has
# SHA-256 a5de3ed7803253abcbde0aa66885de5380279f133ee01bd20fd4db5bf19599af.
# This entrypoint extends that proven foundation with the full K5 acceptance
# sequence exercised on 2026-08-31.

set -Eeuo pipefail

readonly REFERENCE_WEEKLY_DRILL_SHA256="a5de3ed7803253abcbde0aa66885de5380279f133ee01bd20fd4db5bf19599af"
readonly DEFAULT_POSTGRES_IMAGE="postgres:18-alpine"
readonly DEFAULT_WORK_ROOT="/tmp"
readonly DEFAULT_PG_PORT="55433"
readonly DEFAULT_APP_PORT="9899"

BACKUP_ROOT=""
STAMP=""
SOURCE_REPO=""
SOURCE_SHA=""
GITHUB_MAIN_SHA=""
EVIDENCE_OUT=""
WORK_ROOT="$DEFAULT_WORK_ROOT"
POSTGRES_IMAGE="$DEFAULT_POSTGRES_IMAGE"
PG_PORT="$DEFAULT_PG_PORT"
APP_PORT="$DEFAULT_APP_PORT"
APP_PYTHON=""
EXECUTE=0

WORK=""
SOURCE_DIR=""
CONTAINER=""
VOLUME=""
PASSWORD=""
APP_PID=""
APP_PROCESS_STATUS="not-started"
CURRENT_PHASE="preflight"
RESULT="fail"
FAILURE_REASON=""
CLEANUP_STATUS="pending"
SOURCE_BACKUP_MUTATION="false"
EVIDENCE_CREATED=0
EVIDENCE_DEVICE=""
EVIDENCE_INODE=""
CONTAINER_CREATED=0
VOLUME_CREATED=0
DOCKER_RM_STATUS="not-created"
DOCKER_VOLUME_RM_STATUS="not-created"
DOCKER_PS_STATUS="not-run"
DOCKER_VOLUME_LS_STATUS="not-run"
REFERENCE_FAILURE_AT=""
RESTORE_STARTED_MONOTONIC_NS=""
READY_MONOTONIC_NS=""
BACKUP_STARTED_AT=""
BACKUP_COMPLETED_AT=""
GENERATION_RESULT_SHA256=""
GENERATION_METADATA_STATUS=""
REQUIREMENTS_LOCK_SHA256=""
RUNTIME_DEPENDENCY_VALIDATION=""
RUNTIME_DEPENDENCY_FINGERPRINT=""
APP_PYTHON_SOURCE=""

usage() {
  cat <<'EOF'
Usage:
  bash ops/k5-isolated-restore.sh \
    --backup-root <checksum-backed generation root> \
    --stamp YYYYMMDD_HHMMSS \
    --source-repo <local git repo containing source commit> \
    --source-sha <40-char source release sha> \
    --github-main-sha <40-char main sha observed immediately before exercise> \
    --evidence-out <sanitized JSON output path> \
    [--work-root /tmp] \
    [--postgres-image postgres:18-alpine] \
    [--pg-port 55433] \
    [--app-port 9899] \
    [--app-python /path/to/isolated/python] \
    --execute-isolated-restore

Backup timing authority:
  Backup start/completion are derived exclusively from the per-generation
  metadata artifact <backup-root>/manifests/generation_<stamp>.result.
  Required metadata keys: stamp, status (exactly "verified"), started_at,
  completed_at, file_count. Timestamps must carry an explicit UTC offset and
  are canonicalized to YYYY-MM-DDTHH:MM:SSZ before any evidence/RPO use.
  Rolling last-run metadata, filesystem mtimes, log lines and filename
  inference are never accepted as RPO authority, and arbitrary CLI
  timestamps no longer exist on this interface.

Safety:
  - This command is isolated-only. It does not implement production cutover.
  - It never runs migrations.
  - It never writes to the source backup root.
  - It creates/removes only exercise-named disposable Docker resources.
  - The PostgreSQL and application ports bind to 127.0.0.1 only.
  - Evidence is written through exclusive no-follow temporary files inside a
    current-user-owned, non-group/world-writable evidence parent.
EOF
}

die() {
  FAILURE_REASON="$*"
  RESULT="fail"
  printf 'K5 isolated restore: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

app_process_alive() {
  [ -n "$APP_PID" ] || return 1
  [ -d "/proc/$APP_PID" ] || return 1
  local stat_line rest state
  stat_line="$(cat "/proc/$APP_PID/stat" 2>/dev/null)" || return 1
  rest="${stat_line##*) }"
  state="${rest%% *}"
  [ "$state" != "Z" ]
}

terminate_application() {
  if [ -z "$APP_PID" ] || [ "$APP_PROCESS_STATUS" = "not-started" ]; then
    APP_PROCESS_STATUS="not-started"
    return 0
  fi
  local grace_iterations="${K5_APP_TERM_GRACE_ITERATIONS:-10}"
  local grace_sleep="${K5_APP_TERM_SLEEP_SECONDS:-0.3}"
  local used_kill=0

  if app_process_alive; then
    kill -TERM "$APP_PID" >/dev/null 2>&1 || true
    for _ in $(seq 1 "$grace_iterations"); do
      app_process_alive || break
      sleep "$grace_sleep"
    done
    if app_process_alive; then
      kill -KILL "$APP_PID" >/dev/null 2>&1 || true
      used_kill=1
      for _ in $(seq 1 "$grace_iterations"); do
        app_process_alive || break
        sleep "$grace_sleep"
      done
    fi
  fi

  # Reap the terminated child without indefinite blocking: after a delivered
  # TERM/KILL the child is gone or a zombie, so wait returns immediately.
  wait "$APP_PID" >/dev/null 2>&1 || true

  if app_process_alive; then
    APP_PROCESS_STATUS="fail"
    return 1
  fi
  if [ "$used_kill" -eq 1 ]; then
    APP_PROCESS_STATUS="kill-terminated"
  else
    APP_PROCESS_STATUS="terminated"
  fi
  return 0
}

write_initial_evidence() {
  local parent
  parent="$(dirname -- "$EVIDENCE_OUT")"
  if [ ! -d "$parent" ]; then
    mkdir -p -- "$parent" || die "cannot create evidence parent: $parent"
    chmod 0700 -- "$parent" || die "cannot secure newly created evidence parent: $parent"
  fi
  [ "$(realpath -e -- "$parent")" = "$parent" ] ||
    die "evidence parent must not be a symlink: $parent"
  python3 - "$EVIDENCE_OUT" "$EXERCISE_ID" "$GITHUB_MAIN_SHA" "$SOURCE_SHA" \
    "$STAMP" "$REFERENCE_FAILURE_AT" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path
path, exercise_id, github_main, source_sha, stamp, reference_failure = sys.argv[1:]
target = Path(path)

def fail(message):
    raise SystemExit(message)

def verify_parent():
    parent = target.parent
    current = os.lstat(parent)
    if stat.S_ISLNK(current.st_mode):
        fail("evidence parent is a symlink")
    if os.path.realpath(parent) != str(parent):
        fail("evidence parent is not canonical")
    if current.st_uid != os.geteuid():
        fail("evidence parent is not owned by the current user")
    if current.st_mode & 0o022:
        fail("evidence parent is group or world writable")

verify_parent()
payload = {
    "schemaVersion": "k5/1",
    "kind": "restore-exercise-evidence",
    "exerciseId": exercise_id,
    "githubMainAtStart": github_main,
    "sourceReleaseSha": source_sha,
    "sourceBackupId": stamp,
    "backupStartedAt": None,
    "backupCompletedAt": None,
    "referenceFailureAt": reference_failure,
    "generationMetadataSha256": None,
    "generationMetadataStatus": None,
    "sourceIntegrityStatus": "not-verified",
    "productionMutation": False,
    "sourceBackupMutation": False,
    "migrationExecution": False,
    "cleanupStatus": "pending",
    "result": "fail",
    "failurePhase": "preflight",
    "failureReason": "exercise did not complete",
}
data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
fd = os.open(path, flags, 0o600)
try:
    with os.fdopen(fd, "wb") as output:
        output.write(data)
    fd = -1
finally:
    if fd != -1:
        os.close(fd)
PY
  EVIDENCE_CREATED=1
  read -r EVIDENCE_DEVICE EVIDENCE_INODE < <(stat -c '%d %i' -- "$EVIDENCE_OUT")
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backup-root) BACKUP_ROOT="${2:-}"; shift 2 ;;
    --stamp) STAMP="${2:-}"; shift 2 ;;
    --source-repo) SOURCE_REPO="${2:-}"; shift 2 ;;
    --source-sha) SOURCE_SHA="${2:-}"; shift 2 ;;
    --github-main-sha) GITHUB_MAIN_SHA="${2:-}"; shift 2 ;;
    --evidence-out) EVIDENCE_OUT="${2:-}"; shift 2 ;;
    --work-root) WORK_ROOT="${2:-}"; shift 2 ;;
    --postgres-image) POSTGRES_IMAGE="${2:-}"; shift 2 ;;
    --pg-port) PG_PORT="${2:-}"; shift 2 ;;
    --app-port) APP_PORT="${2:-}"; shift 2 ;;
    --app-python) APP_PYTHON="${2:-}"; shift 2 ;;
    --execute-isolated-restore) EXECUTE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[ "$EXECUTE" -eq 1 ] || die "--execute-isolated-restore is required"
[ -n "$BACKUP_ROOT" ] || die "--backup-root is required"
[ -n "$STAMP" ] || die "--stamp is required"
[ -n "$SOURCE_REPO" ] || die "--source-repo is required"
[ -n "$SOURCE_SHA" ] || die "--source-sha is required"
[ -n "$GITHUB_MAIN_SHA" ] || die "--github-main-sha is required"
[ -n "$EVIDENCE_OUT" ] || die "--evidence-out is required"
if [ -e "$EVIDENCE_OUT" ] || [ -L "$EVIDENCE_OUT" ]; then
  die "--evidence-out must not already exist or be a symlink"
fi

[[ "$STAMP" =~ ^[0-9]{8}_[0-9]{6}$ ]] || die "--stamp must be YYYYMMDD_HHMMSS"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || die "--source-sha must be a lowercase 40-char SHA"
[[ "$GITHUB_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]] || die "--github-main-sha must be a lowercase 40-char SHA"
[[ "$PG_PORT" =~ ^[0-9]+$ ]] || die "--pg-port must be numeric"
[[ "$APP_PORT" =~ ^[0-9]+$ ]] || die "--app-port must be numeric"
if [ "$PG_PORT" -lt 1024 ] || [ "$PG_PORT" -gt 65535 ]; then
  die "--pg-port out of range"
fi
if [ "$APP_PORT" -lt 1024 ] || [ "$APP_PORT" -gt 65535 ]; then
  die "--app-port out of range"
fi
[ "$PG_PORT" -ne "$APP_PORT" ] || die "PostgreSQL and application ports must differ"

for command_name in bash python3 git sha256sum realpath stat cp docker openssl curl \
  tar awk grep cmp sqlite3; do
  require_cmd "$command_name"
done

EVIDENCE_OUT_INPUT="$EVIDENCE_OUT"
EVIDENCE_PARENT_INPUT="$(dirname -- "$EVIDENCE_OUT_INPUT")"
if [ -e "$EVIDENCE_PARENT_INPUT" ] &&
  [ "$(realpath -e -- "$EVIDENCE_PARENT_INPUT")" != "$(realpath -m -- "$EVIDENCE_PARENT_INPUT")" ]; then
  die "evidence parent must not traverse a symlink"
fi
BACKUP_ROOT="$(realpath -e -- "$BACKUP_ROOT")"
SOURCE_REPO="$(realpath -e -- "$SOURCE_REPO")"
WORK_ROOT="$(realpath -e -- "$WORK_ROOT")"
EVIDENCE_OUT="$(realpath -m -- "$EVIDENCE_OUT")"
if [ -e "$EVIDENCE_OUT" ] || [ -L "$EVIDENCE_OUT" ]; then
  die "--evidence-out must not already exist or be a symlink"
fi
readonly BACKUP_ROOT SOURCE_REPO WORK_ROOT EVIDENCE_OUT

case "$WORK_ROOT/" in
  "$BACKUP_ROOT/"*) die "--work-root must not be inside the source backup root" ;;
esac
case "$EVIDENCE_OUT" in
  "$BACKUP_ROOT"|"$BACKUP_ROOT"/*)
    die "--evidence-out must not be inside the source backup root"
    ;;
esac

EXERCISE_ID="k5-${STAMP}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
CONTAINER="${EXERCISE_ID}-pg"
VOLUME="${EXERCISE_ID}-pgdata"
REFERENCE_FAILURE_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
readonly EXERCISE_ID CONTAINER VOLUME REFERENCE_FAILURE_AT
write_initial_evidence

update_early_failure_evidence() {
  [ "$EVIDENCE_CREATED" -eq 1 ] || return 0
  python3 - "$EVIDENCE_OUT" "$EVIDENCE_DEVICE" "$EVIDENCE_INODE" \
    "$CURRENT_PHASE" "$FAILURE_REASON" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path
path = Path(sys.argv[1])
expected = (int(sys.argv[2]), int(sys.argv[3]))

def fail(message):
    raise SystemExit(message)

def verify_parent():
    parent = path.parent
    current = os.lstat(parent)
    if stat.S_ISLNK(current.st_mode):
        fail("evidence parent is a symlink")
    if os.path.realpath(parent) != str(parent):
        fail("evidence parent is not canonical")
    if current.st_uid != os.geteuid():
        fail("evidence parent is not owned by the current user")
    if current.st_mode & 0o022:
        fail("evidence parent is group or world writable")

def verify_destination():
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        fail("evidence output is missing during early failure")
    if stat.S_ISLNK(current.st_mode):
        fail("evidence output is a symlink during early failure")
    if (current.st_dev, current.st_ino) != expected:
        fail("evidence output was replaced during early failure")

def secure_replace(payload_bytes):
    verify_parent()
    verify_destination()
    temporary = None
    fd = -1
    for _attempt in range(8):
        candidate = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            # Fail closed on any creation race (existing leaf, symlinked
            # candidate, or permission anomaly): try another random leaf.
            continue
        temporary = candidate
        break
    if temporary is None:
        fail("unable to allocate a secure temporary evidence file")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(payload_bytes)
            output.flush()
            os.fsync(output.fileno())
        fd = -1
        verify_destination()
        os.replace(temporary, path)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except (FileNotFoundError, TypeError):
            pass

verify_destination()
with path.open("r", encoding="utf-8") as source:
    payload = json.load(source)
payload["result"] = "fail"
payload["failurePhase"] = sys.argv[4] or "preflight"
payload["failureReason"] = sys.argv[5] or f"phase {payload['failurePhase']} failed"
secure_replace((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
PY
}

early_failure_cleanup() {
  local exit_rc=$?
  set +e
  if [ "$exit_rc" -ne 0 ]; then
    update_early_failure_evidence || true
  fi
  exit "$exit_rc"
}
trap early_failure_cleanup EXIT

[ -d "$BACKUP_ROOT" ] || die "backup root is not a directory"
[ -d "$SOURCE_REPO/.git" ] || die "source repo is not a git checkout"
[ -d "$WORK_ROOT" ] || die "work root is not a directory"

git -C "$SOURCE_REPO" cat-file -e "${SOURCE_SHA}^{commit}" 2>/dev/null ||
  die "source release commit is not available locally: $SOURCE_SHA"

CURRENT_PHASE="port-validation"
python3 - "$PG_PORT" "$APP_PORT" <<'PY'
import socket
import sys
for raw in sys.argv[1:]:
    port = int(raw)
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            raise SystemExit(f"loopback port {port} is not free: {exc}")
PY

WORK="$(mktemp -d -p "$WORK_ROOT" k5-isolated-restore-XXXXXXXX)"
SOURCE_DIR="$WORK/source"
mkdir -p "$WORK/in/postgres" "$WORK/in/visits" "$WORK/out" "$WORK/home" "$SOURCE_DIR"
readonly WORK SOURCE_DIR

PASSWORD="$(openssl rand -hex 24)"
readonly PASSWORD

trap - EXIT

record_failure() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ -z "$FAILURE_REASON" ]; then
    FAILURE_REASON="phase ${CURRENT_PHASE} failed"
  fi
  return "$rc"
}
trap record_failure ERR

capture_evidence_identity() {
  [ -e "$EVIDENCE_OUT" ] && [ ! -L "$EVIDENCE_OUT" ] || return 1
  read -r EVIDENCE_DEVICE EVIDENCE_INODE < <(stat -c '%d %i' -- "$EVIDENCE_OUT")
}

validate_runtime_dependencies() {
  local interpreter="$1"
  local lock_file="$SOURCE_DIR/backend/requirements.lock"
  [ -f "$lock_file" ] || die "backend/requirements.lock is missing from the source release"
  REQUIREMENTS_LOCK_SHA256="$(sha256sum "$lock_file" | awk '{print $1}')"
  local validation_output
  validation_output="$(env -i \
    HOME="$WORK/home" \
    PATH="${PATH:-/usr/bin:/bin}" \
    PYTHONNOUSERSITE=1 \
    "$interpreter" - "$lock_file" 2>&1 <<'PY'
import hashlib
import importlib.metadata as metadata
import re
import sys
from pathlib import Path

lock_path = Path(sys.argv[1])
EXEMPT_TOOLING = {"pip", "setuptools", "wheel"}

def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()

pins = {}
for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or line.startswith("--"):
        continue
    token = line.split()[0]
    if "==" not in token:
        raise SystemExit(f"unparseable requirements.lock line: {raw_line!r}")
    name, version = token.split("==", 1)
    name = name.split("[", 1)[0]
    normalized = normalize(name)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", normalized):
        raise SystemExit(f"unsafe distribution name in requirements.lock: {name!r}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]*", version):
        raise SystemExit(f"unsafe version in requirements.lock: {version!r}")
    if normalized in pins:
        raise SystemExit(f"duplicate locked distribution: {normalized}")
    pins[normalized] = version
if not pins:
    raise SystemExit("requirements.lock contains no pinned distributions")

installed = {}
for distribution in metadata.distributions():
    raw_name = (distribution.metadata.get("Name") if distribution.metadata else "") or ""
    installed.setdefault(normalize(raw_name), set()).add(distribution.version)

missing = sorted(
    name for name in pins if name not in EXEMPT_TOOLING and name not in installed
)
mismatched = sorted(
    f"{name} locked={pins[name]} installed={'|'.join(sorted(installed[name]))}"
    for name in pins
    if name not in EXEMPT_TOOLING and name in installed and pins[name] not in installed[name]
)
if missing or mismatched:
    raise SystemExit(
        f"runtime dependency validation failed missing={missing} mismatched={mismatched}"
    )
fingerprint_source = "\n".join(f"{name}=={pins[name]}" for name in sorted(pins))
fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
print(f"pass\t{fingerprint}")
PY
  )" || die "runtime dependency validation failed: $validation_output"
  RUNTIME_DEPENDENCY_VALIDATION="${validation_output%%$'\t'*}"
  RUNTIME_DEPENDENCY_FINGERPRINT="${validation_output#*$'\t'}"
  [ "$RUNTIME_DEPENDENCY_VALIDATION" = "pass" ] ||
    die "runtime dependency validation did not pass: $validation_output"
}

update_final_evidence() {
  [ "$EVIDENCE_CREATED" -eq 1 ] || return 0
  python3 - "$EVIDENCE_OUT" "$EVIDENCE_DEVICE" "$EVIDENCE_INODE" \
    "$CLEANUP_STATUS" "$SOURCE_BACKUP_MUTATION" "$RESULT" \
    "$CURRENT_PHASE" "$FAILURE_REASON" "$DOCKER_RM_STATUS" "$DOCKER_VOLUME_RM_STATUS" \
    "$DOCKER_PS_STATUS" "$DOCKER_VOLUME_LS_STATUS" "$APP_PROCESS_STATUS" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path
path = Path(sys.argv[1])
expected = (int(sys.argv[2]), int(sys.argv[3]))

def fail(message):
    raise SystemExit(message)

def verify_parent():
    parent = path.parent
    current = os.lstat(parent)
    if stat.S_ISLNK(current.st_mode):
        fail("evidence parent is a symlink")
    if os.path.realpath(parent) != str(parent):
        fail("evidence parent is not canonical")
    if current.st_uid != os.geteuid():
        fail("evidence parent is not owned by the current user")
    if current.st_mode & 0o022:
        fail("evidence parent is group or world writable")

def verify_destination():
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        fail("evidence output is missing during cleanup")
    if stat.S_ISLNK(current.st_mode):
        fail("evidence output is a symlink during cleanup")
    if (current.st_dev, current.st_ino) != expected:
        fail("evidence output was replaced during cleanup")

def secure_replace(payload_bytes):
    verify_parent()
    verify_destination()
    temporary = None
    fd = -1
    for _attempt in range(8):
        candidate = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            # Fail closed on any creation race (existing leaf, symlinked
            # candidate, or permission anomaly): try another random leaf.
            continue
        temporary = candidate
        break
    if temporary is None:
        fail("unable to allocate a secure temporary evidence file")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(payload_bytes)
            output.flush()
            os.fsync(output.fileno())
        fd = -1
        verify_destination()
        os.replace(temporary, path)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except (FileNotFoundError, TypeError):
            pass

verify_destination()
with path.open("r", encoding="utf-8") as source:
    payload = json.load(source)
payload["cleanupStatus"] = sys.argv[4]
payload["sourceBackupMutation"] = sys.argv[5] == "true"
payload["result"] = sys.argv[6]
payload["appTerminationStatus"] = sys.argv[13]
payload["dockerCleanup"] = {
    "containerRemoval": sys.argv[9],
    "volumeRemoval": sys.argv[10],
    "containerListing": sys.argv[11],
    "volumeListing": sys.argv[12],
}
if payload["result"] != "pass":
    payload["failurePhase"] = sys.argv[7] or payload.get("failurePhase") or "unknown"
    payload["failureReason"] = sys.argv[8] or "exercise failed"
else:
    payload["failurePhase"] = None
    payload["failureReason"] = None
secure_replace((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
PY
  capture_evidence_identity
}

cleanup() {
  local exit_rc=$?
  set +e

  terminate_application || true
  if [ "$APP_PROCESS_STATUS" = "fail" ]; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="application process termination could not be proven"
  fi

  if [ "$CONTAINER_CREATED" -eq 1 ]; then
    if docker rm -f "$CONTAINER" >/dev/null 2>&1; then
      DOCKER_RM_STATUS="pass"
    else
      DOCKER_RM_STATUS="fail"
    fi
  else
    DOCKER_RM_STATUS="not-created"
  fi
  if [ "$VOLUME_CREATED" -eq 1 ]; then
    if docker volume rm "$VOLUME" >/dev/null 2>&1; then
      DOCKER_VOLUME_RM_STATUS="pass"
    else
      DOCKER_VOLUME_RM_STATUS="fail"
    fi
  else
    DOCKER_VOLUME_RM_STATUS="not-created"
  fi
  if [ "$DOCKER_RM_STATUS" = "fail" ] || [ "$DOCKER_VOLUME_RM_STATUS" = "fail" ]; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="disposable Docker resource removal failed"
  fi

  local source_after=""
  if [ -n "$WORK" ] && [ -d "$WORK" ]; then
    source_after="$WORK/source-after.tsv"
    : >"$source_after"
    if [ -f "$WORK/source-paths.txt" ]; then
      while IFS= read -r source_path; do
        [ -n "$source_path" ] || continue
        if [ -e "$source_path" ]; then
          stat -c '%n\t%s\t%Y' -- "$source_path" >>"$source_after" || true
        else
          printf '%s\tMISSING\tMISSING\n' "$source_path" >>"$source_after"
        fi
      done <"$WORK/source-paths.txt"
    fi
  fi

  if [ -z "$source_after" ] || [ ! -f "$WORK/source-before.tsv" ] ||
    cmp -s "$WORK/source-before.tsv" "$source_after"; then
    SOURCE_BACKUP_MUTATION="false"
  else
    SOURCE_BACKUP_MUTATION="true"
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="source backup metadata changed"
  fi

  local docker_ps_output=""
  local docker_volume_output=""
  if [ -n "$WORK" ] && [ -d "$WORK" ]; then
    docker_ps_output="$WORK/docker-ps-cleanup.txt"
    docker_volume_output="$WORK/docker-volume-cleanup.txt"
  else
    docker_ps_output="$(mktemp)"
    docker_volume_output="$(mktemp)"
  fi
  if docker ps -a --format '{{.Names}}' >"$docker_ps_output" 2>/dev/null; then
    DOCKER_PS_STATUS="pass"
  else
    DOCKER_PS_STATUS="fail"
  fi
  if docker volume ls --format '{{.Name}}' >"$docker_volume_output" 2>/dev/null; then
    DOCKER_VOLUME_LS_STATUS="pass"
  else
    DOCKER_VOLUME_LS_STATUS="fail"
  fi
  if ! { [[ "$DOCKER_RM_STATUS" = "pass" || "$DOCKER_RM_STATUS" = "not-created" ]] &&
    [[ "$DOCKER_VOLUME_RM_STATUS" = "pass" || "$DOCKER_VOLUME_RM_STATUS" = "not-created" ]] &&
    [ "$DOCKER_PS_STATUS" = "pass" ] &&
    [ "$DOCKER_VOLUME_LS_STATUS" = "pass" ] &&
    ! grep -Fxq "$CONTAINER" "$docker_ps_output" &&
    ! grep -Fxq "$VOLUME" "$docker_volume_output"; }; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="disposable Docker cleanup failed"
  fi
  if [ -z "$WORK" ] || [ ! -d "$WORK" ]; then
    rm -f -- "$docker_ps_output" "$docker_volume_output"
  fi

  # Intermediate durable state: records cleanup progress but never a PASS.
  if ! update_final_evidence; then
    CLEANUP_STATUS="fail"
    RESULT="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="evidence output identity changed during cleanup"
  fi

  if [ -n "$WORK" ] && [ -d "$WORK" ] &&
    [ "$(dirname "$WORK")" = "$WORK_ROOT" ] &&
    [[ "$(basename "$WORK")" == k5-isolated-restore-* ]]; then
    rm -rf -- "$WORK"
  else
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="unsafe workdir cleanup boundary"
  fi

  if [ -d "$WORK" ]; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
    [ -n "$FAILURE_REASON" ] || FAILURE_REASON="workdir cleanup failed"
  fi

  if [ "$exit_rc" -ne 0 ] || [ -n "$FAILURE_REASON" ]; then
    update_final_evidence || true
    [ "$exit_rc" -ne 0 ] && exit "$exit_rc"
    exit 1
  fi

  # Every cleanup verification succeeded: publish the FIRST durable full PASS.
  CLEANUP_STATUS="pass"
  RESULT="pass"
  if ! update_final_evidence; then
    RESULT="fail"
    CLEANUP_STATUS="fail"
    FAILURE_REASON="final evidence publication failed; durable evidence remains non-pass"
    [ "$exit_rc" -ne 0 ] && exit "$exit_rc"
    exit 1
  fi
  exit 0
}
trap cleanup EXIT

MANIFEST="$BACKUP_ROOT/manifests/generation_${STAMP}.sha256"
GENERATION_RESULT="$BACKUP_ROOT/manifests/generation_${STAMP}.result"
readonly MANIFEST GENERATION_RESULT
CURRENT_PHASE="docker-preflight"
if docker ps -a --format '{{.Names}}' >"$WORK/docker-ps-preflight.txt" 2>"$WORK/docker-ps-preflight.err"; then
  if grep -Fxq "$CONTAINER" "$WORK/docker-ps-preflight.txt"; then
    die "refusing to reuse existing container: $CONTAINER"
  fi
else
  die "Docker container query failed during preflight"
fi
if docker volume ls --format '{{.Name}}' >"$WORK/docker-volume-preflight.txt" 2>"$WORK/docker-volume-preflight.err"; then
  if grep -Fxq "$VOLUME" "$WORK/docker-volume-preflight.txt"; then
    die "refusing to reuse existing volume: $VOLUME"
  fi
else
  die "Docker volume query failed during preflight"
fi

CURRENT_PHASE="generation-manifest"
[ -f "$MANIFEST" ] || die "generation manifest not found for stamp $STAMP"
python3 - "$MANIFEST" "$STAMP" "$WORK/expected.tsv" <<'PY'
import re
import sys
from pathlib import Path

manifest = Path(sys.argv[1])
stamp = sys.argv[2]
output = Path(sys.argv[3])
databases = (
    "unihub", "mobiup_dwh", "unihub_identity", "unihub_retail",
    "unihub_learning", "authentik", "glitchtip",
)
expected = {
    *(f"postgres/{name}_{stamp}.dump" for name in databases),
    f"visits/visits_{stamp}.db",
}
parsed = {}
for raw in manifest.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line:
        continue
    match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(.+)", line)
    if not match:
        raise SystemExit(f"invalid generation manifest line: {raw!r}")
    digest, raw_name = match.groups()
    name = raw_name.lstrip("./")
    path = Path(name)
    if name.startswith("/") or ".." in path.parts or name in parsed:
        raise SystemExit(f"unsafe/duplicate manifest path: {raw_name!r}")
    parsed[name] = digest
if set(parsed) != expected:
    raise SystemExit(
        f"manifest component mismatch missing={sorted(expected-set(parsed))} "
        f"extra={sorted(set(parsed)-expected)}"
    )
output.write_text(
    "".join(f"{name}\t{parsed[name]}\n" for name in sorted(parsed)),
    encoding="utf-8",
)
PY

GENERATION_MANIFEST_SHA256="$(sha256sum "$MANIFEST" | awk '{print $1}')"
readonly GENERATION_MANIFEST_SHA256

: >"$WORK/source-paths.txt"
printf '%s\n' "$MANIFEST" >>"$WORK/source-paths.txt"
while IFS=$'\t' read -r relative expected_sha; do
  source_path="$BACKUP_ROOT/$relative"
  [ -f "$source_path" ] || die "backup component missing: $relative"
  actual_sha="$(sha256sum "$source_path" | awk '{print $1}')"
  [ "$actual_sha" = "$expected_sha" ] || die "source checksum mismatch: $relative"
  printf '%s\n' "$source_path" >>"$WORK/source-paths.txt"
done <"$WORK/expected.tsv"

: >"$WORK/source-before.tsv"
while IFS= read -r source_path; do
  stat -c '%n\t%s\t%Y' -- "$source_path" >>"$WORK/source-before.tsv"
done <"$WORK/source-paths.txt"

CURRENT_PHASE="generation-metadata"
[ -f "$GENERATION_RESULT" ] ||
  die "per-generation result metadata not found for stamp $STAMP (rolling last-run metadata is never used as RPO authority)"
GENERATION_METADATA_OUTPUT="$(python3 - "$GENERATION_RESULT" "$STAMP" \
  "$REFERENCE_FAILURE_AT" "$WORK/expected.tsv" 2>&1 <<'PY'
import datetime as dt
import re
import sys
from pathlib import Path

metadata_path = Path(sys.argv[1])
expected_stamp = sys.argv[2]
reference_raw = sys.argv[3]
expected_tsv = Path(sys.argv[4])

REQUIRED_KEYS = ("stamp", "status", "started_at", "completed_at", "file_count")
KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

values = {}
for raw_line in metadata_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"malformed generation metadata line: {raw_line!r}")
    key, value = line.split("=", 1)
    if not KEY_PATTERN.fullmatch(key):
        raise SystemExit(f"malformed generation metadata key: {key!r}")
    if key in values:
        raise SystemExit(f"duplicate generation metadata key: {key}")
    values[key] = value

missing = [key for key in REQUIRED_KEYS if key not in values]
if missing:
    raise SystemExit(f"missing required generation metadata keys: {missing}")

if values["stamp"] != expected_stamp:
    raise SystemExit(
        f"generation metadata stamp {values['stamp']!r} does not match "
        f"selected generation {expected_stamp!r}"
    )
if values["status"] != "verified":
    raise SystemExit(
        f"generation metadata status must be exactly 'verified', got {values['status']!r}"
    )
if not values["file_count"].isdigit():
    raise SystemExit(f"generation metadata file_count is not numeric: {values['file_count']!r}")

manifest_entries = [
    line for line in expected_tsv.read_text(encoding="utf-8").splitlines() if line
]
if int(values["file_count"]) != len(manifest_entries):
    raise SystemExit(
        f"generation metadata file_count {values['file_count']} does not match "
        f"manifest entry count {len(manifest_entries)}"
    )

def canonicalize(raw, label):
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"{label} is not a valid ISO-8601 timestamp: {raw!r}")
    if parsed.tzinfo is None:
        raise SystemExit(f"{label} must include an explicit UTC offset: {raw!r}")
    utc = parsed.astimezone(dt.timezone.utc)
    if utc.microsecond != 0:
        raise SystemExit(f"{label} must have whole-second precision: {raw!r}")
    return utc

def format_utc(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")

started = canonicalize(values["started_at"], "started_at")
completed = canonicalize(values["completed_at"], "completed_at")
reference = canonicalize(reference_raw, "referenceFailureAt")
if started > completed:
    raise SystemExit("backup completion precedes backup start")
if completed > reference:
    raise SystemExit("backup completion follows reference failure")
print(f"{format_utc(started)}\t{format_utc(completed)}")
PY
)" || die "generation metadata validation failed for $STAMP: $GENERATION_METADATA_OUTPUT"
BACKUP_STARTED_AT="${GENERATION_METADATA_OUTPUT%%$'\t'*}"
BACKUP_COMPLETED_AT="${GENERATION_METADATA_OUTPUT#*$'\t'}"
GENERATION_RESULT_SHA256="$(sha256sum "$GENERATION_RESULT" | awk '{print $1}')"
GENERATION_METADATA_STATUS="verified"
readonly BACKUP_STARTED_AT BACKUP_COMPLETED_AT GENERATION_RESULT_SHA256 \
  GENERATION_METADATA_STATUS

CURRENT_PHASE="source-release-export"
git -C "$SOURCE_REPO" archive --format=tar "$SOURCE_SHA" >"$WORK/source.tar"
tar -xf "$WORK/source.tar" -C "$SOURCE_DIR"
rm -f "$WORK/source.tar"
[ ! -e "$SOURCE_DIR/.git" ] || die "source archive unexpectedly contains .git"

CURRENT_PHASE="source-migration-authority"
python3 - "$SOURCE_DIR" "$WORK/migration-meta.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
migration_dir = root / "backend/db/migrations"
manifest_path = migration_dir / "manifest.json"
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
if payload.get("version") != 2:
    raise SystemExit("migration manifest version is not 2")
migrations = payload.get("migrations")
classes = payload.get("execution_classes")
if not isinstance(migrations, dict) or not migrations:
    raise SystemExit("migration manifest migrations invalid")
if set(classes or {}) != set(migrations):
    raise SystemExit("execution_classes do not cover every migration")
if any(value not in {"transactional", "online", "maintenance-window"} for value in classes.values()):
    raise SystemExit("invalid migration execution class")
actual = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in migration_dir.glob("*.sql")
}
if actual != migrations:
    raise SystemExit("migration files do not match immutable manifest")
baseline = payload["baseline"]
baseline_path = migration_dir / baseline["file"]
if baseline_path.name != "schema_v2.sql":
    raise SystemExit("unexpected baseline file")
if hashlib.sha256(baseline_path.read_bytes()).hexdigest() != baseline["sha256"]:
    raise SystemExit("baseline checksum mismatch")
out.write_text(json.dumps({
    "version": 2,
    "count": len(migrations),
    "head": sorted(migrations)[-1],
    "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    "migrations": migrations,
}, sort_keys=True), encoding="utf-8")
PY

CURRENT_PHASE="postgres-image"
IMAGE_META="$(docker image inspect "$POSTGRES_IMAGE" \
  --format '{{.Id}}|{{json .RepoDigests}}' 2>/dev/null)" ||
  die "PostgreSQL image not available locally: $POSTGRES_IMAGE"
[ -n "$IMAGE_META" ] || die "PostgreSQL image metadata is empty"
POSTGRES_IMAGE_ID="${IMAGE_META%%|*}"
POSTGRES_DIGEST="$(python3 - "${IMAGE_META#*|}" "$POSTGRES_IMAGE_ID" <<'PY'
import json
import sys
raw, fallback = sys.argv[1:]
try:
    values = json.loads(raw)
except Exception:
    values = []
print(values[0].split("@", 1)[-1] if values else fallback)
PY
)"
readonly POSTGRES_IMAGE_ID POSTGRES_DIGEST

CURRENT_PHASE="payload-stage"
RESTORE_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RESTORE_STARTED_MONOTONIC_NS="$(python3 -c 'import time; print(time.monotonic_ns())')"
read -r RPO_UPPER_SECONDS COMPLETED_GENERATION_AGE_SECONDS < <(
  python3 - "$REFERENCE_FAILURE_AT" "$BACKUP_STARTED_AT" "$BACKUP_COMPLETED_AT" <<'PY'
import datetime as dt
import sys
def parse(raw):
    return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
reference, started, completed = map(parse, sys.argv[1:])
if completed > reference or started > completed:
    raise SystemExit("invalid backup timestamp ordering")
print(int((reference-started).total_seconds()),
      int((reference-completed).total_seconds()))
PY
)
readonly REFERENCE_FAILURE_AT RESTORE_STARTED_AT RPO_UPPER_SECONDS COMPLETED_GENERATION_AGE_SECONDS

while IFS=$'\t' read -r relative expected_sha; do
  case "$relative" in
    postgres/*) destination="$WORK/in/postgres/$(basename "$relative")" ;;
    visits/*) destination="$WORK/in/visits/$(basename "$relative")" ;;
    *) die "unexpected component namespace: $relative" ;;
  esac
  cp --preserve=mode,timestamps -- "$BACKUP_ROOT/$relative" "$destination"
  copied_sha="$(sha256sum "$destination" | awk '{print $1}')"
  [ "$copied_sha" = "$expected_sha" ] || die "staged checksum mismatch: $relative"
done <"$WORK/expected.tsv"

CURRENT_PHASE="postgres-target"
if docker volume create "$VOLUME" >/dev/null; then
  VOLUME_CREATED=1
else
  die "failed to create disposable PostgreSQL volume"
fi
printf 'POSTGRES_PASSWORD=%s\n' "$PASSWORD" >"$WORK/postgres.env"
chmod 0600 "$WORK/postgres.env"
if docker run -d \
  --name "$CONTAINER" \
  -p "127.0.0.1:${PG_PORT}:5432" \
  --env-file "$WORK/postgres.env" \
  -v "$VOLUME:/var/lib/postgresql/data" \
  -v "$WORK/in/postgres:/backups:ro" \
  "$POSTGRES_IMAGE" >/dev/null; then
  CONTAINER_CREATED=1
else
  die "failed to create disposable PostgreSQL container"
fi

for _ in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -U postgres -q >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U postgres -q >/dev/null 2>&1 ||
  die "disposable PostgreSQL did not become ready"
POSTGRES_VERSION="$(docker exec "$CONTAINER" postgres --version)"
[[ "$POSTGRES_VERSION" =~ PostgreSQL\)\ 18\. ]] ||
  die "disposable PostgreSQL is not major 18: $POSTGRES_VERSION"

CURRENT_PHASE="role-precreation"
docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
  pg_restore --schema-only --no-owner --no-acl -f - \
  "/backups/unihub_${STAMP}.dump" 2>/dev/null |
  grep -oE 'TO +unihub_[a-zA-Z0-9_]+' |
  awk '{print $2}' | sort -u >"$WORK/roles.txt" || true

while IFS= read -r role; do
  [ -n "$role" ] || continue
  [[ "$role" =~ ^unihub_[a-zA-Z0-9_]+$ ]] || die "unsafe restore role: $role"
  docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
    psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE \"$role\";" \
    >/dev/null
done <"$WORK/roles.txt"

CURRENT_PHASE="postgres-restore"
: >"$WORK/postgres-restores.tsv"
for label in unihub mobiup_dwh unihub_identity unihub_retail unihub_learning authentik glitchtip; do
  database="dr_${label}"
  started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  restore_started_monotonic_ns="$(python3 -c 'import time; print(time.monotonic_ns())')"
  docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
    createdb -U postgres --template=template0 "$database" >/dev/null
  docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
    pg_restore -U postgres --no-owner --no-acl --exit-on-error \
    -d "$database" "/backups/${label}_${STAMP}.dump" >/dev/null
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  duration="$(python3 - "$restore_started_monotonic_ns" <<'PY'
import sys
import time
started_ns = int(sys.argv[1])
elapsed_ns = time.monotonic_ns() - started_ns
if elapsed_ns < 0:
    raise SystemExit("monotonic restore duration was negative")
# Round up to a whole second so an observed sub-second tail is not hidden.
print((elapsed_ns + 999_999_999) // 1_000_000_000)
PY
)"
  relations="$(
    docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
      psql -U postgres -d "$database" -Atc \
      "SELECT count(*) FROM pg_class WHERE relkind IN ('r','p','v','m');" |
      tr -d '[:space:]'
  )"
  [[ "$relations" =~ ^[0-9]+$ ]] || die "invalid relation count for $label"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$label" "$database" "$started_at" "$completed_at" "$duration" "$relations" \
    >>"$WORK/postgres-restores.tsv"
done

CURRENT_PHASE="visits-restore"
VISITS_SOURCE="$WORK/in/visits/visits_${STAMP}.db"
VISITS_COPY="$WORK/out/visits.db"
cp --preserve=mode,timestamps -- "$VISITS_SOURCE" "$VISITS_COPY"
VISITS_EXPECTED_SHA="$(awk -F'\t' -v p="visits/visits_${STAMP}.db" '$1==p {print $2}' "$WORK/expected.tsv")"
[ "$(sha256sum "$VISITS_COPY" | awk '{print $1}')" = "$VISITS_EXPECTED_SHA" ] ||
  die "visits staged-copy checksum mismatch"
require_cmd sqlite3
VISITS_INTEGRITY="$(sqlite3 "$VISITS_COPY" 'PRAGMA integrity_check;')"
[ "$VISITS_INTEGRITY" = "ok" ] || die "visits integrity_check failed: $VISITS_INTEGRITY"
VISITS_TABLE_COUNT="$(sqlite3 "$VISITS_COPY" "SELECT count(*) FROM sqlite_master WHERE type='table';")"
[[ "$VISITS_TABLE_COUNT" =~ ^[0-9]+$ ]] || die "invalid visits table count"

CURRENT_PHASE="migration-verification"
docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
  psql -U postgres -d dr_unihub -At -F $'\t' \
  -c 'SELECT filename, checksum FROM schema_migrations ORDER BY filename;' \
  >"$WORK/restored-migrations.tsv"

python3 - "$WORK/migration-meta.json" "$WORK/restored-migrations.tsv" <<'PY'
import json
import sys
from pathlib import Path
meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
applied = {}
for raw in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines():
    if not raw:
        continue
    filename, checksum = raw.split("\t", 1)
    applied[filename] = checksum
expected = meta["migrations"]
if applied != expected:
    missing = sorted(set(expected) - set(applied))
    extra = sorted(set(applied) - set(expected))
    changed = sorted(k for k in set(applied) & set(expected) if applied[k] != expected[k])
    raise SystemExit(
        f"schema_migrations mismatch missing={missing} extra={extra} checksum={changed}"
    )
PY

CURRENT_PHASE="business-integrity"
: >"$WORK/business-1.tsv"
: >"$WORK/business-2.tsv"
for pass_file in "$WORK/business-1.tsv" "$WORK/business-2.tsv"; do
  selected=0
  for table in stores agent_targets historical_monthly_sales grile_runs incentive_campaigns; do
    [[ "$table" =~ (salary|identity|user|auth|session|token|secret|credential|customer|person) ]] &&
      die "sensitive business-table selection: $table"
    exists="$(
      docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
        psql -U postgres -d dr_unihub -Atc \
        "SELECT to_regclass('public.${table}') IS NOT NULL;"
    )"
    [ "$exists" = "t" ] || continue
    count="$(
      docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
        psql -U postgres -d dr_unihub -Atc \
        "SELECT count(*) FROM public.\"${table}\";"
    )"
    [[ "$count" =~ ^[0-9]+$ ]] || die "invalid count for $table"
    printf '%s\t%s\n' "$table" "$count" >>"$pass_file"
    selected=$(( selected + 1 ))
  done
  [ "$selected" -ge 3 ] || die "fewer than three approved business tables are available"
done
cmp -s "$WORK/business-1.tsv" "$WORK/business-2.tsv" ||
  die "business-integrity counts are not reproducible"
BUSINESS_FINGERPRINT="$(
  python3 - "$WORK/business-1.tsv" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
counts = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    name, count = raw.split("\t", 1)
    counts[name] = int(count)
canonical = json.dumps(counts, sort_keys=True, separators=(",", ":")).encode()
print(hashlib.sha256(canonical).hexdigest())
PY
)"
readonly BUSINESS_FINGERPRINT

CURRENT_PHASE="application-runtime"
if [ -n "$APP_PYTHON" ]; then
  # Explicit interpreter path: validate against the source release lock via
  # importlib.metadata only. This branch performs no package installation and
  # no network mutation.
  APP_PYTHON="$(realpath -e -- "$APP_PYTHON")"
  APP_PYTHON_SOURCE="explicit"
else
  APP_PYTHON="$WORK/venv/bin/python"
  APP_PYTHON_SOURCE="default-venv"
  env -i \
    HOME="$WORK/home" \
    PATH="${PATH:-/usr/bin:/bin}" \
    PIP_CONFIG_FILE=/dev/null \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    PYTHONNOUSERSITE=1 \
    python3 -m venv "$WORK/venv"
  env -i \
    HOME="$WORK/home" \
    PATH="${PATH:-/usr/bin:/bin}" \
    PIP_CONFIG_FILE=/dev/null \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    PYTHONNOUSERSITE=1 \
    "$APP_PYTHON" -m pip install --disable-pip-version-check \
      --require-hashes -r "$SOURCE_DIR/backend/requirements.lock" >"$WORK/pip.log" 2>&1
fi
validate_runtime_dependencies "$APP_PYTHON"
env -i \
  HOME="$WORK/home" \
  PATH="${PATH:-/usr/bin:/bin}" \
  PYTHONNOUSERSITE=1 \
  "$APP_PYTHON" -c 'import uvicorn, asyncpg' >/dev/null

CURRENT_PHASE="application-start"
(
  cd "$SOURCE_DIR/backend"
  exec env -i \
    HOME="$WORK/home" \
    PATH="${PATH:-/usr/bin:/bin}" \
    PYTHONNOUSERSITE=1 \
    PYTHONPATH="$SOURCE_DIR/backend" \
    UNIHUB_ENV=development \
    DATABASE_URL="postgresql://postgres:${PASSWORD}@127.0.0.1:${PG_PORT}/dr_unihub" \
    DB_POOL_MIN_SIZE=1 \
    DB_POOL_MAX_SIZE=3 \
    DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY=1 \
    RETAIL_VISITS_READ_SOURCE=postgres \
    RETAIL_VISITS_SHADOW_COMPARE_ENABLED=false \
    HOST=127.0.0.1 \
    PORT="$APP_PORT" \
    "$APP_PYTHON" -m uvicorn main:app \
      --host 127.0.0.1 --port "$APP_PORT"
) >"$WORK/app.log" 2>&1 &
APP_PID=$!
APP_PROCESS_STATUS="running"

CURRENT_PHASE="application-readiness"
probe_json() {
  local endpoint="$1"
  local expected_status="$2"
  local output="$3"
  local http_code
  http_code="$(curl -sS --max-time 5 -o "$output" -w '%{http_code}' \
    "http://127.0.0.1:${APP_PORT}${endpoint}" || true)"
  [ "$http_code" = "200" ] || return 1
  python3 - "$output" "$expected_status" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if payload == {"status": sys.argv[2]} else 1)
PY
}

ready=0
for _ in $(seq 1 60); do
  if ! kill -0 "$APP_PID" >/dev/null 2>&1; then
    die "application exited before readiness"
  fi
  if probe_json /livez alive "$WORK/livez.json" &&
    probe_json /health ok "$WORK/health.json" &&
    probe_json /readyz ok "$WORK/readyz.json"; then
    ready=1
    break
  fi
  sleep 1
done
[ "$ready" -eq 1 ] || die "application readiness timeout"
READY_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
READY_MONOTONIC_NS="$(python3 -c 'import time; print(time.monotonic_ns())')"
RTO_SECONDS="$(python3 - "$RESTORE_STARTED_MONOTONIC_NS" "$READY_MONOTONIC_NS" <<'PY'
import sys
started_ns, ready_ns = map(int, sys.argv[1:])
elapsed_ns = ready_ns - started_ns
if elapsed_ns < 0:
    raise SystemExit("monotonic RTO elapsed time was negative")
# Round up to a whole second so an observed sub-second tail is not hidden.
print((elapsed_ns + 999_999_999) // 1_000_000_000)
PY
)"
APP_PYTHON_VERSION="$("$APP_PYTHON" --version 2>&1 | head -1)"
readonly READY_AT RTO_SECONDS APP_PYTHON_VERSION

CURRENT_PHASE="service-acceptance"
python3 - \
  "$EVIDENCE_OUT" "$EVIDENCE_DEVICE" "$EVIDENCE_INODE" \
  "$EXERCISE_ID" "$GITHUB_MAIN_SHA" "$SOURCE_SHA" "$STAMP" \
  "$BACKUP_STARTED_AT" "$BACKUP_COMPLETED_AT" "$GENERATION_MANIFEST_SHA256" \
  "$GENERATION_RESULT_SHA256" "$GENERATION_METADATA_STATUS" \
  "$REFERENCE_WEEKLY_DRILL_SHA256" "$REFERENCE_FAILURE_AT" "$RPO_UPPER_SECONDS" \
  "$COMPLETED_GENERATION_AGE_SECONDS" "$RESTORE_STARTED_AT" "$READY_AT" "$RTO_SECONDS" \
  "$POSTGRES_IMAGE" "$POSTGRES_DIGEST" "$CONTAINER" "$PG_PORT" \
  "$WORK/expected.tsv" "$WORK/migration-meta.json" "$WORK/roles.txt" \
  "$WORK/postgres-restores.tsv" "$VISITS_TABLE_COUNT" "$WORK/business-1.tsv" \
  "$BUSINESS_FINGERPRINT" "$APP_PYTHON_VERSION" "$APP_PORT" \
  "$REQUIREMENTS_LOCK_SHA256" "$RUNTIME_DEPENDENCY_VALIDATION" \
  "$RUNTIME_DEPENDENCY_FINGERPRINT" "$APP_PYTHON_SOURCE" <<'PY'
import json
import os
import stat
import sys
from pathlib import Path

(
    evidence_path, expected_device, expected_inode, exercise_id, github_main,
    source_sha, stamp, backup_started, backup_completed, generation_manifest_sha,
    generation_metadata_sha, generation_metadata_status, reference_drill_sha,
    reference_failure, rpo_upper, completed_age, restore_started, ready_at, rto,
    postgres_image, postgres_digest, container, pg_port, expected_path,
    migration_meta_path, roles_path, restores_path, visits_table_count,
    business_path, business_fingerprint, python_version, app_port,
    requirements_lock_sha, runtime_dependency_validation,
    runtime_dependency_fingerprint, app_python_source,
) = sys.argv[1:]

path = Path(evidence_path)
expected = (int(expected_device), int(expected_inode))

def fail(message):
    raise SystemExit(message)

def verify_parent():
    parent = path.parent
    current = os.lstat(parent)
    if stat.S_ISLNK(current.st_mode):
        fail("evidence parent is a symlink")
    if os.path.realpath(parent) != str(parent):
        fail("evidence parent is not canonical")
    if current.st_uid != os.geteuid():
        fail("evidence parent is not owned by the current user")
    if current.st_mode & 0o022:
        fail("evidence parent is group or world writable")

def verify_destination():
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        fail("evidence output is missing before successful replacement")
    if stat.S_ISLNK(current.st_mode):
        fail("evidence output is a symlink before successful replacement")
    if (current.st_dev, current.st_ino) != expected:
        fail("evidence output was replaced before successful replacement")

def secure_replace(payload_bytes):
    verify_parent()
    verify_destination()
    temporary = None
    fd = -1
    for _attempt in range(8):
        candidate = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
        try:
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError:
            # Fail closed on any creation race (existing leaf, symlinked
            # candidate, or permission anomaly): try another random leaf.
            continue
        temporary = candidate
        break
    if temporary is None:
        fail("unable to allocate a secure temporary evidence file")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(payload_bytes)
            output.flush()
            os.fsync(output.fileno())
        fd = -1
        verify_destination()
        os.replace(temporary, path)
    finally:
        if fd != -1:
            os.close(fd)
        try:
            os.unlink(temporary)
        except (FileNotFoundError, TypeError):
            pass

checksums = {}
for raw in Path(expected_path).read_text(encoding="utf-8").splitlines():
    relative, digest = raw.split("\t", 1)
    filename = Path(relative).stem
    component = filename.rsplit("_", 2)[0]
    checksums[component] = digest

migration_meta = json.loads(Path(migration_meta_path).read_text(encoding="utf-8"))
roles = [
    line for line in Path(roles_path).read_text(encoding="utf-8").splitlines() if line
]
restores = []
for raw in Path(restores_path).read_text(encoding="utf-8").splitlines():
    label, database, started, completed, duration, relations = raw.split("\t")
    restores.append({
        "label": label,
        "database": database,
        "exitCode": 0,
        "startedAt": started,
        "completedAt": completed,
        "durationSeconds": int(duration),
        "durationAuthority": "monotonic-ns",
        "relationCount": int(relations),
        "status": "pass",
    })
counts = {}
for raw in Path(business_path).read_text(encoding="utf-8").splitlines():
    table, count = raw.split("\t")
    counts[table] = int(count)

payload = {
    "schemaVersion": "k5/1",
    "kind": "restore-exercise-evidence",
    "exerciseId": exercise_id,
    "githubMainAtStart": github_main,
    "sourceReleaseSha": source_sha,
    "sourceMigrationHead": migration_meta["head"],
    "sourceBackupId": stamp,
    "backupStartedAt": backup_started,
    "backupCompletedAt": backup_completed,
    "backupTimestampAuthority": "per-generation-metadata-artifact",
    "generationMetadataSha256": generation_metadata_sha,
    "generationMetadataStatus": generation_metadata_status,
    "sourceIntegrityStatus": "verified",
    "sourceComponentCount": len(checksums),
    "sourceChecksums": checksums,
    "generationManifestSha256": generation_manifest_sha,
    "sourceMigrationManifestSha256": migration_meta["manifestSha256"],
    "referenceDrillSha256": reference_drill_sha,
    "crossDatabaseSnapshotAtomic": False,
    "referenceFailureAt": reference_failure,
    "rpoDefinition": "conservative-generation-age-upper-bound",
    "rpoUpperBoundSeconds": int(rpo_upper),
    "completedGenerationAgeSeconds": int(completed_age),
    "restoreStartedAt": restore_started,
    "readyAt": ready_at,
    "rtoDefinition": "monotonic-from-payload-transfer-start-to-restored-service-acceptance",
    "rtoSeconds": int(rto),
    "restoreTargetType": "disposable-docker-local",
    "restoreTargetHost": os.uname().nodename,
    "postgresImage": postgres_image,
    "postgresImageDigest": postgres_digest,
    "postgresMajorVersion": 18,
    "postgresContainerName": container,
    "postgresPort": int(pg_port),
    "rolePrecreationApproach": "extract TO unihub_* from schema-only pg_restore; CREATE ROLE without privileges",
    "precreatedRoles": roles,
    "postgresRestoreStatus": {"overall": "pass", "databases": restores},
    "visitsRestoreStatus": {
        "checksumMatch": True,
        "integrityCheck": "ok",
        "tableCount": int(visits_table_count),
    },
    "migrationVerificationStatus": {
        "manifestVersion": 2,
        "migrationHead": migration_meta["head"],
        "migrationCount": int(migration_meta["count"]),
        "allChecksumsMatch": True,
        "noMigrationExecuted": True,
    },
    "businessIntegritySampleStatus": {
        "tableCounts": counts,
        "fingerprintSha256": business_fingerprint,
        "repeatFingerprintMatch": True,
    },
    "applicationStartStatus": {
        "status": "pass",
        "sourceSha": source_sha,
        "environmentMode": "development",
        "databaseAuthorityScope": "development/no-process-authority",
        "externalIdentityDependenciesEnabled": False,
        "pythonRuntime": python_version,
        "appPythonSource": app_python_source,
        "requirementsLockSha256": requirements_lock_sha,
        "runtimeDependencyValidation": runtime_dependency_validation,
        "runtimeDependencyFingerprint": runtime_dependency_fingerprint,
        "environmentCategoriesUsed": [
            "UNIHUB_ENV=development",
            f"DATABASE_URL=postgresql://postgres:[REDACTED]@127.0.0.1:{pg_port}/dr_unihub",
            "DB_POOL_MIN_SIZE=1",
            "DB_POOL_MAX_SIZE=3",
            "DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY=1",
            "RETAIL_VISITS_READ_SOURCE=postgres",
            "RETAIL_VISITS_SHADOW_COMPARE_ENABLED=false",
            "HOST=127.0.0.1",
            f"PORT={app_port}",
        ],
        "excludedEnvironmentVariables": [
            "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE", "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET", "SESSION_ENCRYPTION_KEY", "SESSION_VALKEY_URL",
            "RATE_LIMIT_VALKEY_URL", "RATE_LIMIT_KEY_HMAC_SECRET",
            "BACKEND_SENTRY_DSN", "SENTRY_DSN", "UNIHUB_DB_PROCESS_AUTHORITY",
        ],
    },
    "livezStatus": {"httpCode": 200, "body": {"status": "alive"}},
    "healthStatus": {"httpCode": 200, "body": {"status": "ok"}},
    "readinessStatus": {
        "httpCode": 200,
        "body": {"status": "ok"},
        "dependencyScope": {
            "postgresqlRestoredDbExercised": True,
            "sessionBackendDisabled": True,
            "oidcJwksDisabled": True,
            "productionValkeySessionSemanticsNotExercised": True,
            "productionDbProcessAuthoritySemanticsNotExercised": True,
        },
    },
    "serviceAcceptanceRecorded": True,
    "appTerminationStatus": "pending",
    "productionMutation": False,
    "sourceBackupMutation": False,
    "migrationExecution": False,
    "cleanupStatus": "pending",
    "result": "fail",
    "failurePhase": None,
    "failureReason": "cleanup verification pending",
}
secure_replace((json.dumps(payload, indent=2) + "\n").encode("utf-8"))
PY
capture_evidence_identity

CURRENT_PHASE=""
printf '%s\n' \
  "K5 isolated restore service acceptance recorded; overall pass is published only after complete verified cleanup; evidence=$EVIDENCE_OUT"
