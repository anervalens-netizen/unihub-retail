#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
TEST_MODE="${RETAIL_APPROVAL_TEST_MODE:-0}"

log() {
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

[[ "$#" -eq 3 ]] \
  || die "usage: $PROGRAM <ci-run-id> <source-sha> <artifact-sha256>"

CI_RUN_ID="$1"
SOURCE_SHA="$2"
ARTIFACT_SHA256="$3"

[[ "$CI_RUN_ID" =~ ^[1-9][0-9]{0,19}$ ]] || die "CI run ID must be a positive integer"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] || die "source SHA must be 40 lowercase hex characters"
[[ "$ARTIFACT_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "artifact SHA-256 must be 64 lowercase hex characters"

if [[ "$TEST_MODE" == "1" ]]; then
  [[ "$EUID" -ne 0 ]] || die "test mode must never run as root"
  APPROVAL_ROOT="${RETAIL_APPROVAL_TEST_ROOT:?RETAIL_APPROVAL_TEST_ROOT is required in test mode}"
  APPROVER="${RETAIL_APPROVAL_TEST_APPROVER:-test-approver}"
  NOW="${RETAIL_APPROVAL_TEST_NOW:-$(date +%s)}"
  TTL_SECONDS="${RETAIL_APPROVAL_TEST_TTL_SECONDS:-1800}"
  CONFIRMATION="${RETAIL_APPROVAL_TEST_CONFIRM:-}"
else
  [[ "$EUID" -eq 0 ]] || die "production approval requires root through sudo"
  [[ -z "${RETAIL_APPROVAL_TEST_ROOT:-}" ]] || die "test root is forbidden in production mode"
  [[ -z "${RETAIL_APPROVAL_TEST_APPROVER:-}" ]] || die "test approver is forbidden in production mode"
  [[ -z "${RETAIL_APPROVAL_TEST_NOW:-}" ]] || die "test time is forbidden in production mode"
  [[ -z "${RETAIL_APPROVAL_TEST_TTL_SECONDS:-}" ]] || die "test TTL is forbidden in production mode"
  [[ -z "${RETAIL_APPROVAL_TEST_CONFIRM:-}" ]] || die "non-interactive confirmation is forbidden in production mode"
  APPROVAL_ROOT="/var/lib/unihub-retail-deploy/approvals"
  APPROVER="${SUDO_USER:-}"
  NOW="$(date +%s)"
  TTL_SECONDS=1800
  [[ -t 0 && -t 1 ]] || die "production approval requires an interactive terminal"
fi

[[ "$APPROVER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "approver OS identity is invalid"
[[ "$APPROVER" != "root" && "$APPROVER" != "unihub-deploy" ]] \
  || die "root and the deploy runner cannot act as the human approver"
[[ "$NOW" =~ ^[0-9]{1,12}$ ]] || die "approval timestamp is invalid"
[[ "$TTL_SECONDS" =~ ^[1-9][0-9]{0,3}$ && "$TTL_SECONDS" -le 3600 ]] \
  || die "approval TTL must be between 1 and 3600 seconds"

if [[ "$TEST_MODE" != "1" ]]; then
  printf 'Retail production approval\n'
  printf '  CI run:       %s\n' "$CI_RUN_ID"
  printf '  source SHA:   %s\n' "$SOURCE_SHA"
  printf '  artifact SHA: %s\n' "$ARTIFACT_SHA256"
  printf '  expires in:   %s minutes\n' "$((TTL_SECONDS / 60))"
  printf 'Type APPROVE_RETAIL_PRODUCTION to continue: '
  read -r CONFIRMATION
fi

[[ "$CONFIRMATION" == "APPROVE_RETAIL_PRODUCTION" ]] || die "approval confirmation did not match"

if [[ "$TEST_MODE" == "1" ]]; then
  mkdir -p "$APPROVAL_ROOT"
  chmod 0700 "$APPROVAL_ROOT"
else
  install -d -m 0700 -o root -g root /var/lib/unihub-retail-deploy
  install -d -m 0700 -o root -g root "$APPROVAL_ROOT"
  [[ "$(stat -c '%u:%g:%a' "$APPROVAL_ROOT")" == "0:0:700" ]] \
    || die "approval directory must be root:root mode 0700"
fi

exec 9>"$APPROVAL_ROOT/.approval.lock"
flock -n 9 || die "another approval operation is active"

PREFIX="${CI_RUN_ID}-${SOURCE_SHA}-${ARTIFACT_SHA256}"
shopt -s nullglob
ACTIVE=(
  "$APPROVAL_ROOT/${PREFIX}-"*.approved
  "$APPROVAL_ROOT/${PREFIX}-"*.claimed.*
)
shopt -u nullglob
[[ "${#ACTIVE[@]}" -eq 0 ]] || die "an unconsumed approval already exists for this release"

EXPIRES_AT="$((NOW + TTL_SECONDS))"
RANDOM_SUFFIX="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
APPROVAL_ID="${PREFIX}-${NOW}-${RANDOM_SUFFIX}"
TMP_FILE="$(mktemp "$APPROVAL_ROOT/.approval.XXXXXX")"
FINAL_FILE="$APPROVAL_ROOT/${APPROVAL_ID}.approved"
trap 'rm -f -- "$TMP_FILE"' EXIT

{
  printf 'version=1\n'
  printf 'approval_id=%s\n' "$APPROVAL_ID"
  printf 'ci_run_id=%s\n' "$CI_RUN_ID"
  printf 'source_sha=%s\n' "$SOURCE_SHA"
  printf 'artifact_sha256=%s\n' "$ARTIFACT_SHA256"
  printf 'approved_by_os=%s\n' "$APPROVER"
  printf 'approved_at_epoch=%s\n' "$NOW"
  printf 'expires_at_epoch=%s\n' "$EXPIRES_AT"
  printf 'state=approved\n'
} >"$TMP_FILE"
chmod 0600 "$TMP_FILE"
mv -- "$TMP_FILE" "$FINAL_FILE"
trap - EXIT

log "one-time approval created by $APPROVER for CI run $CI_RUN_ID and source $SOURCE_SHA"
log "approval expires at epoch $EXPIRES_AT"
