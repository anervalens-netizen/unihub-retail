#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-retail-artifact.sh"
[[ -x "$DEPLOY_SCRIPT" ]] || DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-retail-artifact.sh.candidate"
APPROVE_SCRIPT="$SCRIPT_DIR/approve-retail-release.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-test.XXXXXX")"
trap 'rm -rf -- "$ROOT"' EXIT

REMOTE="$ROOT/remote.git"
BUILDER="$ROOT/builder"
LIVE="$ROOT/live"
OPS="$ROOT/ops"
ARTIFACT="$ROOT/release.tar.gz"
CI_RUN_ID=29445177873

git init --bare --quiet "$REMOTE"
git init --quiet --initial-branch=main "$BUILDER"
git -C "$BUILDER" config user.name "Deploy Test"
git -C "$BUILDER" config user.email "deploy-test@example.invalid"
git -C "$BUILDER" remote add origin "$REMOTE"

mkdir -p "$BUILDER/backend"
printf '{"name":"retail-deploy-test"}\n' >"$BUILDER/package.json"
printf 'print("old")\n' >"$BUILDER/backend/main.py"
printf 'dist/\n' >"$BUILDER/.gitignore"
git -C "$BUILDER" add .
git -C "$BUILDER" commit --quiet -m old
OLD_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet -u origin main
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main

git clone --quiet "$REMOTE" "$LIVE"
mkdir -p "$LIVE/dist" "$LIVE/docs"
printf 'old frontend\n' >"$LIVE/dist/index.html"
printf 'original audit\n' >"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md"
printf 'original plan\n' >"$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md"
ORIGINAL_AUDIT_SHA="$(sha256sum "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" | awk '{print $1}')"
ORIGINAL_PLAN_SHA="$(sha256sum "$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md" | awk '{print $1}')"

mkdir -p "$BUILDER/docs"
printf 'print("new")\n' >"$BUILDER/backend/main.py"
printf 'published audit\n' >"$BUILDER/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md"
printf 'published plan\n' >"$BUILDER/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md"
git -C "$BUILDER" add .
git -C "$BUILDER" commit --quiet -m new
NEW_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet origin main

mkdir -p "$BUILDER/dist/assets"
printf 'new frontend\n' >"$BUILDER/dist/index.html"
printf 'asset\n' >"$BUILDER/dist/assets/app.js"
git -C "$BUILDER" archive --format=tar "$NEW_SHA" >"$ROOT/release.tar"
tar -rf "$ROOT/release.tar" -C "$BUILDER" dist
gzip -n "$ROOT/release.tar"
ARTIFACT_SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"

run_deploy() {
  RETAIL_DEPLOY_TEST_MODE=1 \
  RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
    bash "$DEPLOY_SCRIPT" "$@"
}

approve_release() {
  local run_id="$1"
  local source_sha="$2"
  local artifact_sha256="$3"
  local now="${4:-$(date +%s)}"
  RETAIL_APPROVAL_TEST_MODE=1 \
  RETAIL_APPROVAL_TEST_ROOT="$ROOT/approval-store" \
  RETAIL_APPROVAL_TEST_APPROVER=test-approver \
  RETAIL_APPROVAL_TEST_NOW="$now" \
  RETAIL_APPROVAL_TEST_CONFIRM=APPROVE_RETAIL_PRODUCTION \
    bash "$APPROVE_SCRIPT" "$run_id" "$source_sha" "$artifact_sha256"
}

set +e
RETAIL_APPROVAL_TEST_MODE=1 \
RETAIL_APPROVAL_TEST_ROOT="$ROOT/approval-store" \
RETAIL_APPROVAL_TEST_APPROVER=unihub-deploy \
RETAIL_APPROVAL_TEST_CONFIRM=APPROVE_RETAIL_PRODUCTION \
  bash "$APPROVE_SCRIPT" "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
RUNNER_APPROVAL_RC=$?
set -e
[[ "$RUNNER_APPROVAL_RC" -ne 0 ]]

set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
NO_APPROVAL_RC=$?
set -e
[[ "$NO_APPROVAL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ ! -d "$OPS/backups/retail-deploy" ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
set +e
approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
DUPLICATE_APPROVAL_RC=$?
set -e
[[ "$DUPLICATE_APPROVAL_RC" -ne 0 ]]

run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "new frontend" ]]
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit" ]]
HANDLE="$(rg -l '^STATE=deployed$' "$OPS/backups/retail-deploy"/*/release.env | xargs -r -n1 dirname | tail -1)"
[[ -n "$HANDLE" ]]
grep -q "^$ORIGINAL_AUDIT_SHA  docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md$" "$HANDLE/untracked.sha256"
grep -q "^$ORIGINAL_PLAN_SHA  docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md$" "$HANDLE/untracked.sha256"
grep -q '^STATE=deployed$' "$HANDLE/release.env"
grep -q "^ci_run_id=$CI_RUN_ID$" "$HANDLE/approval.env"
grep -q "^source_sha=$NEW_SHA$" "$HANDLE/approval.env"
grep -q "^artifact_sha256=$ARTIFACT_SHA256$" "$HANDLE/approval.env"
grep -q '^approved_by_os=test-approver$' "$HANDLE/approval.env"
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' | wc -l)" -eq 0 ]]

run_deploy rollback "$HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ "$(sha256sum "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" | awk '{print $1}')" == "$ORIGINAL_AUDIT_SHA" ]]
[[ "$(sha256sum "$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md" | awk '{print $1}')" == "$ORIGINAL_PLAN_SHA" ]]
grep -q '^STATE=rolled_back$' "$HANDLE/release.env"

set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
REUSE_RC=$?
set -e
[[ "$REUSE_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=health \
  bash "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
FAIL_RC=$?
set -e
[[ "$FAIL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ "$(sha256sum "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" | awk '{print $1}')" == "$ORIGINAL_AUDIT_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq 1 ]]

mkdir -p "$ROOT/tampered"
tar -xzf "$ARTIFACT" -C "$ROOT/tampered"
printf 'tampered\n' >"$ROOT/tampered/backend/main.py"
tar -czf "$ROOT/tampered.tar.gz" -C "$ROOT/tampered" .
TAMPER_SHA256="$(sha256sum "$ROOT/tampered.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$TAMPER_SHA256" >/dev/null
set +e
run_deploy "$ROOT/tampered.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$TAMPER_SHA256" >/dev/null 2>&1
TAMPER_RC=$?
set -e
[[ "$TAMPER_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]

python3 - "$ROOT/unsafe.tar.gz" <<'PY'
import io
import sys
import tarfile

with tarfile.open(sys.argv[1], "w:gz") as bundle:
    payload = b"escape"
    member = tarfile.TarInfo("../escape")
    member.size = len(payload)
    bundle.addfile(member, io.BytesIO(payload))
PY
UNSAFE_SHA256="$(sha256sum "$ROOT/unsafe.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$UNSAFE_SHA256" >/dev/null
set +e
run_deploy "$ROOT/unsafe.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$UNSAFE_SHA256" >/dev/null 2>&1
UNSAFE_RC=$?
set -e
[[ "$UNSAFE_RC" -ne 0 ]]
[[ ! -e "$ROOT/escape" ]]

python3 - "$ROOT/symlink.tar.gz" <<'PY'
import sys
import tarfile

with tarfile.open(sys.argv[1], "w:gz") as bundle:
    member = tarfile.TarInfo("dist/index.html")
    member.type = tarfile.SYMTYPE
    member.linkname = "/etc/passwd"
    bundle.addfile(member)
PY
SYMLINK_SHA256="$(sha256sum "$ROOT/symlink.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$SYMLINK_SHA256" >/dev/null
set +e
run_deploy "$ROOT/symlink.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$SYMLINK_SHA256" >/dev/null 2>&1
SYMLINK_RC=$?
set -e
[[ "$SYMLINK_RC" -ne 0 ]]

truncate -s 268435457 "$ROOT/oversize.tar.gz"
OVERSIZE_APPROVED_SHA256="$(printf 'f%.0s' {1..64})"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$OVERSIZE_APPROVED_SHA256" >/dev/null
set +e
run_deploy "$ROOT/oversize.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$OVERSIZE_APPROVED_SHA256" >/dev/null 2>&1
OVERSIZE_RC=$?
set -e
[[ "$OVERSIZE_RC" -ne 0 ]]

printf 'unexpected\n' >"$LIVE/unexpected.txt"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
DIRTY_RC=$?
set -e
[[ "$DIRTY_RC" -ne 0 ]]
rm "$LIVE/unexpected.txt"

WRONG_SHA256="$(printf '0%.0s' {1..64})"
approve_release "$((CI_RUN_ID + 1))" "$NEW_SHA" "$WRONG_SHA256" >/dev/null
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$((CI_RUN_ID + 1))" "$ARTIFACT_SHA256" >/dev/null 2>&1
WRONG_DIGEST_APPROVAL_RC=$?
set -e
[[ "$WRONG_DIGEST_APPROVAL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]

approve_release "$((CI_RUN_ID + 2))" "$NEW_SHA" "$ARTIFACT_SHA256" 1000 >/dev/null
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_NOW=4000 \
  bash "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$((CI_RUN_ID + 2))" "$ARTIFACT_SHA256" >/dev/null 2>&1
EXPIRED_APPROVAL_RC=$?
set -e
[[ "$EXPIRED_APPROVAL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.rejected' | wc -l)" -eq 1 ]]

printf 'deploy and rollback sandbox tests: PASS\n'
