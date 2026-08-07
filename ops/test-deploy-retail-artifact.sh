#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-retail-artifact.sh"
[[ -x "$DEPLOY_SCRIPT" ]] || DEPLOY_SCRIPT="$SCRIPT_DIR/deploy-retail-artifact.sh.candidate"
APPROVE_SCRIPT="$SCRIPT_DIR/approve-retail-release.sh"
BUILD_SCRIPT="$SCRIPT_DIR/build-retail-release-artifact.sh"
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/retail-deploy-test.XXXXXX")"
trap 'rm -rf -- "$ROOT"' EXIT

REMOTE="$ROOT/remote.git"
BUILDER="$ROOT/builder"
LIVE="$ROOT/live"
OPS="$ROOT/ops"
CI_RUN_ID=29445177873

git init --bare --quiet "$REMOTE"
git init --quiet --initial-branch=main "$BUILDER"
git -C "$BUILDER" config user.name "Deploy Test"
git -C "$BUILDER" config user.email "deploy-test@example.invalid"
git -C "$BUILDER" remote add origin "$REMOTE"

mkdir -p "$BUILDER/backend" "$BUILDER/ops/systemd" "$BUILDER/ops/observability"
printf '{"name":"retail-deploy-test"}\n' >"$BUILDER/package.json"
printf 'print("old")\n' >"$BUILDER/backend/main.py"
printf 'dist/\n' >"$BUILDER/.gitignore"
cp "$SCRIPT_DIR/systemd/unihub-backend.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/../unihub-worker.service" "$BUILDER/"
cp "$SCRIPT_DIR/systemd/unihub-import-worker.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/systemd/unihub-retail-migrate.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/observability/retail-process-scrape.yml" "$BUILDER/ops/observability/"
git -C "$BUILDER" add .
git -C "$BUILDER" commit --quiet -m old
OLD_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet -u origin main
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main

git clone --quiet "$REMOTE" "$LIVE"
mkdir -p "$LIVE/dist"
printf 'old frontend\n' >"$LIVE/dist/index.html"

mkdir -p \
  "$ROOT/etc/systemd/system" \
  "$ROOT/prometheus" \
  "$OPS/prometheus/scrape.d"
printf '%s\n' \
  'global:' \
  '  scrape_interval: 15s' \
  'scrape_config_files:' \
  '  - /etc/prometheus/scrape.d/*.yml' \
  >"$ROOT/prometheus/prometheus.yml"
touch "$ROOT/prometheus/scrape-mount-ready"
for unit in \
  unihub-backend.service \
  unihub-worker.service \
  unihub-import-worker.service \
  unihub-retail-migrate.service; do
  printf 'legacy unit %s\n' "$unit" >"$ROOT/etc/systemd/system/$unit"
done

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
build_release() {
  local source_sha="$1"
  local output_dir="$2"
  (
    cd "$BUILDER"
    "$BUILD_SCRIPT" "$source_sha" "$output_dir"
  ) >/dev/null
}

RELEASE_DIR="$ROOT/release"
build_release "$NEW_SHA" "$RELEASE_DIR"
ARTIFACT="$RELEASE_DIR/retail-release-${NEW_SHA}.tar.gz"
[[ "$(<"$RELEASE_DIR/SOURCE_SHA")" == "$NEW_SHA" ]]
(cd "$RELEASE_DIR" && sha256sum --check SHA256SUMS >/dev/null)
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

runtime_state_hash() {
  (
    find "$ROOT/etc/systemd/system" "$OPS/prometheus" \
      -type f -exec sha256sum {} +
    find "$ROOT/etc/systemd/system" "$OPS/prometheus" \
      -type l -printf '%p -> %l\n'
  ) | sort | sha256sum | awk '{print $1}'
}

RUNTIME_BEFORE_VALIDATE="$(runtime_state_hash)"
run_deploy validate "$ARTIFACT" "$NEW_SHA" >/dev/null
[[ "$(runtime_state_hash)" == "$RUNTIME_BEFORE_VALIDATE" ]]

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

EXPIRED_RUN_ID="$((CI_RUN_ID + 100))"
approve_release "$EXPIRED_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" 100 >/dev/null
approve_release "$EXPIRED_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" 2000 >/dev/null
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name "${EXPIRED_RUN_ID}-*.rejected" | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name "${EXPIRED_RUN_ID}-*.approved" | wc -l)" -eq 1 ]]
find "$ROOT/approval-store" -maxdepth 1 -type f -name "${EXPIRED_RUN_ID}-*" -delete

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
set +e
approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
DUPLICATE_APPROVAL_RC=$?
set -e
[[ "$DUPLICATE_APPROVAL_RC" -ne 0 ]]

ACTIVE_APPROVAL="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' -print -quit)"
CLAIMED_APPROVAL="${ACTIVE_APPROVAL%.approved}.claimed.99999"
mv -- "$ACTIVE_APPROVAL" "$CLAIMED_APPROVAL"
set +e
approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
CLAIMED_DUPLICATE_RC=$?
set -e
[[ "$CLAIMED_DUPLICATE_RC" -ne 0 ]]
mv -- "$CLAIMED_APPROVAL" "$ACTIVE_APPROVAL"

run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "new frontend" ]]
for unit in \
  unihub-backend.service \
  unihub-worker.service \
  unihub-import-worker.service \
  unihub-retail-migrate.service; do
  [[ -L "$ROOT/etc/systemd/system/$unit" ]]
  [[ "$(readlink -f "$ROOT/etc/systemd/system/$unit")" == "$ROOT/runtime-releases/$NEW_SHA/systemd/$unit" ]]
done
grep -Fxq 'PROMETHEUS_DOCKER_GATEWAY=172.23.0.1' "$OPS/prometheus/unihub-retail-network.env"
grep -Fxq 'PROMETHEUS_DOCKER_SUBNET=172.23.0.0/16' "$OPS/prometheus/unihub-retail-network.env"
grep -Fxq 'WORKER_METRICS_HOST=172.23.0.1' "$OPS/prometheus/unihub-retail-network.env"
[[ "$(grep -Fc '172.23.0.1:' "$OPS/prometheus/scrape.d/unihub-retail.yml")" -eq 3 ]]
! grep -Eq '__PROMETHEUS_DOCKER_GATEWAY__|0\.0\.0\.0|127\.0\.0\.1' \
  "$OPS/prometheus/scrape.d/unihub-retail.yml"
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit" ]]
HANDLE="$(rg -l '^STATE=deployed$' "$OPS/backups/retail-deploy"/*/release.env | xargs -r -n1 dirname | tail -1)"
[[ -n "$HANDLE" ]]
grep -q '^STATE=deployed$' "$HANDLE/release.env"
grep -q "^ci_run_id=$CI_RUN_ID$" "$HANDLE/approval.env"
grep -q "^source_sha=$NEW_SHA$" "$HANDLE/approval.env"
grep -q "^artifact_sha256=$ARTIFACT_SHA256$" "$HANDLE/approval.env"
grep -q '^approved_by_os=test-approver$' "$HANDLE/approval.env"
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' | wc -l)" -eq 0 ]]
BACKUP_COUNT="$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d | wc -l)"
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" -eq 1 ]]
[[ "$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d | wc -l)" -eq "$BACKUP_COUNT" ]]

printf 'corrupted frontend\n' >"$LIVE/dist/index.html"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
REVERIFY_CORRUPT_DIST_RC=$?
set -e
[[ "$REVERIFY_CORRUPT_DIST_RC" -ne 0 ]]
printf 'new frontend\n' >"$LIVE/dist/index.html"

set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$(printf '0%.0s' {1..64})" >/dev/null 2>&1
REVERIFY_WRONG_DIGEST_RC=$?
set -e
[[ "$REVERIFY_WRONG_DIGEST_RC" -ne 0 ]]

printf 'print("newer")\n' >"$BUILDER/backend/main.py"
printf 'published audit v2\n' >"$BUILDER/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md"
printf 'published plan v2\n' >"$BUILDER/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md"
git -C "$BUILDER" add .
git -C "$BUILDER" commit --quiet -m newer
NEWER_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet origin main
NEWER_RELEASE_DIR="$ROOT/release-newer"
build_release "$NEWER_SHA" "$NEWER_RELEASE_DIR"
NEWER_ARTIFACT="$NEWER_RELEASE_DIR/retail-release-${NEWER_SHA}.tar.gz"
[[ "$(<"$NEWER_RELEASE_DIR/SOURCE_SHA")" == "$NEWER_SHA" ]]
(cd "$NEWER_RELEASE_DIR" && sha256sum --check SHA256SUMS >/dev/null)
NEWER_ARTIFACT_SHA256="$(sha256sum "$NEWER_ARTIFACT" | awk '{print $1}')"

set +e
build_release "$NEW_SHA" "$ROOT/stale-release" >/dev/null 2>&1
STALE_BUILD_RC=$?
set -e
[[ "$STALE_BUILD_RC" -ne 0 ]]
[[ ! -e "$ROOT/stale-release" ]]

approve_release "$((CI_RUN_ID + 10))" "$NEWER_SHA" "$NEWER_ARTIFACT_SHA256" >/dev/null
run_deploy "$NEWER_ARTIFACT" "$NEWER_SHA" "$((CI_RUN_ID + 10))" "$NEWER_ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEWER_SHA" ]]
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit v2" ]]
[[ "$(<"$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md")" == "published plan v2" ]]
SECOND_HANDLE="$(
  for manifest in "$OPS/backups/retail-deploy"/*/release.env; do
    if grep -q "^NEW_SHA=$NEWER_SHA$" "$manifest" && grep -q '^STATE=deployed$' "$manifest"; then
      dirname "$manifest"
    fi
  done
)"
[[ -n "$SECOND_HANDLE" && "$SECOND_HANDLE" != "$HANDLE" ]]

run_deploy rollback "$SECOND_HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(readlink -f "$ROOT/etc/systemd/system/unihub-backend.service")" == "$ROOT/runtime-releases/$NEW_SHA/systemd/unihub-backend.service" ]]
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit" ]]
[[ "$(<"$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md")" == "published plan" ]]

run_deploy rollback "$HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ ! -L "$ROOT/etc/systemd/system/unihub-backend.service" ]]
grep -Fxq 'legacy unit unihub-backend.service' "$ROOT/etc/systemd/system/unihub-backend.service"
[[ ! -e "$OPS/prometheus/unihub-retail-network.env" ]]
[[ ! -e "$OPS/prometheus/scrape.d/unihub-retail.yml" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ ! -e "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" ]]
[[ ! -e "$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md" ]]
grep -q '^STATE=rolled_back$' "$HANDLE/release.env"
git --git-dir="$REMOTE" update-ref refs/heads/main "$NEW_SHA"

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
[[ ! -e "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq 1 ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
FAILED_BEFORE_PROMETHEUS="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=prometheus \
  bash "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
PROMETHEUS_RC=$?
set -e
[[ "$PROMETHEUS_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ ! -L "$ROOT/etc/systemd/system/unihub-backend.service" ]]
grep -Fxq 'legacy unit unihub-backend.service' "$ROOT/etc/systemd/system/unihub-backend.service"
[[ ! -e "$OPS/prometheus/unihub-retail-network.env" ]]
[[ ! -e "$OPS/prometheus/scrape.d/unihub-retail.yml" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$((FAILED_BEFORE_PROMETHEUS + 1))" ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
FAILED_BEFORE_PUBLIC_HEALTH="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=public_health \
  bash "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
PUBLIC_HEALTH_RC=$?
set -e
[[ "$PUBLIC_HEALTH_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$((FAILED_BEFORE_PUBLIC_HEALTH + 1))" ]]

mkdir -p "$ROOT/tampered"
tar -xzf "$ARTIFACT" -C "$ROOT/tampered"
printf 'tampered\n' >"$ROOT/tampered/backend/main.py"
tar -czf "$ROOT/tampered.tar.gz" -C "$ROOT/tampered" .
TAMPER_SHA256="$(sha256sum "$ROOT/tampered.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$TAMPER_SHA256" >/dev/null
FAILED_BEFORE_TAMPER="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
run_deploy "$ROOT/tampered.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$TAMPER_SHA256" >/dev/null 2>&1
TAMPER_RC=$?
set -e
[[ "$TAMPER_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$((FAILED_BEFORE_TAMPER + 1))" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.claimed.*' | wc -l)" -eq 0 ]]

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

mkdir -p "$ROOT/directory-index"
tar -xzf "$ARTIFACT" -C "$ROOT/directory-index"
rm "$ROOT/directory-index/dist/index.html"
mkdir "$ROOT/directory-index/dist/index.html"
tar -czf "$ROOT/directory-index.tar.gz" -C "$ROOT/directory-index" .
DIRECTORY_INDEX_SHA256="$(sha256sum "$ROOT/directory-index.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$DIRECTORY_INDEX_SHA256" >/dev/null
set +e
run_deploy "$ROOT/directory-index.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$DIRECTORY_INDEX_SHA256" >/dev/null 2>&1
DIRECTORY_INDEX_RC=$?
set -e
[[ "$DIRECTORY_INDEX_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]

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
REJECTED_APPROVAL="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.rejected' -print -quit)"
grep -q '^state=rejected$' "$REJECTED_APPROVAL"
grep -q '^rejected_at_epoch=4000$' "$REJECTED_APPROVAL"
grep -q '^rejection_reason=not_currently_valid_at_claim$' "$REJECTED_APPROVAL"

mkdir -p "$BUILDER/backend/db/migrations"
printf '%s\n' \
  '{' \
  '  "version": 1,' \
  '  "baseline": {' \
  '    "file": "schema_v2.sql",' \
  '    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",' \
  '    "incorporated_through": "001_test.sql"' \
  '  },' \
  '  "migrations": {' \
  '    "001_test.sql": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' \
  '  }' \
  '}' >"$BUILDER/backend/db/migrations/manifest.json"
git -C "$BUILDER" add backend/db/migrations/manifest.json
git -C "$BUILDER" commit --quiet -m migrated
MIGRATED_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet origin main
MIGRATED_RELEASE_DIR="$ROOT/release-migrated"
build_release "$MIGRATED_SHA" "$MIGRATED_RELEASE_DIR"
MIGRATED_ARTIFACT="$MIGRATED_RELEASE_DIR/retail-release-${MIGRATED_SHA}.tar.gz"
[[ "$(<"$MIGRATED_RELEASE_DIR/SOURCE_SHA")" == "$MIGRATED_SHA" ]]
(cd "$MIGRATED_RELEASE_DIR" && sha256sum --check SHA256SUMS >/dev/null)
MIGRATED_ARTIFACT_SHA256="$(sha256sum "$MIGRATED_ARTIFACT" | awk '{print $1}')"
MIGRATED_RUN_ID="$((CI_RUN_ID + 20))"
approve_release "$MIGRATED_RUN_ID" "$MIGRATED_SHA" "$MIGRATED_ARTIFACT_SHA256" >/dev/null
rm -f "$ROOT/.health-failure-consumed"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=health \
  bash "$DEPLOY_SCRIPT" "$MIGRATED_ARTIFACT" "$MIGRATED_SHA" "$MIGRATED_RUN_ID" "$MIGRATED_ARTIFACT_SHA256" \
  >"$ROOT/migrated-initial-failure.log" 2>&1
MIGRATED_INITIAL_RC=$?
set -e
[[ "$MIGRATED_INITIAL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$MIGRATED_SHA" ]]
MIGRATED_HANDLE="$(
  for manifest in "$OPS/backups/retail-deploy"/*/release.env; do
    if grep -q "^NEW_SHA=$MIGRATED_SHA$" "$manifest" && grep -q '^STATE=recovery_required$' "$manifest"; then
      dirname "$manifest"
    fi
  done
)"
[[ -n "$MIGRATED_HANDLE" ]]
grep -q 'requires a fresh one-time approval for forward recovery' "$ROOT/migrated-initial-failure.log"

printf 'main advanced after failed deploy\n' >"$BUILDER/docs/after-failed-deploy.txt"
git -C "$BUILDER" add docs/after-failed-deploy.txt
git -C "$BUILDER" commit --quiet -m advanced-after-failure
ADVANCED_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet origin main
[[ "$ADVANCED_SHA" != "$MIGRATED_SHA" ]]

approve_release "$MIGRATED_RUN_ID" "$MIGRATED_SHA" "$MIGRATED_ARTIFACT_SHA256" >/dev/null
rm -f "$ROOT/.health-failure-consumed"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=health \
  bash "$DEPLOY_SCRIPT" "$MIGRATED_ARTIFACT" "$MIGRATED_SHA" "$MIGRATED_RUN_ID" "$MIGRATED_ARTIFACT_SHA256" \
  >"$ROOT/migrated-recovery-failure.log" 2>&1
MIGRATED_RECOVERY_RC=$?
set -e
[[ "$MIGRATED_RECOVERY_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$MIGRATED_SHA" ]]
grep -q '^STATE=recovery_required$' "$MIGRATED_HANDLE/release.env"
[[ "$(find "$MIGRATED_HANDLE" -maxdepth 1 -type f -name 'approval.failed.*.env' | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name "${MIGRATED_RUN_ID}-${MIGRATED_SHA}-${MIGRATED_ARTIFACT_SHA256}-*.failed" | wc -l)" -eq 2 ]]
grep -q 'release remains recovery_required and requires a fresh one-time approval' "$ROOT/migrated-recovery-failure.log"

approve_release "$MIGRATED_RUN_ID" "$MIGRATED_SHA" "$MIGRATED_ARTIFACT_SHA256" >/dev/null
run_deploy "$MIGRATED_ARTIFACT" "$MIGRATED_SHA" "$MIGRATED_RUN_ID" "$MIGRATED_ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$MIGRATED_SHA" ]]
grep -q '^STATE=deployed$' "$MIGRATED_HANDLE/release.env"
[[ "$(find "$MIGRATED_HANDLE" -maxdepth 1 -type f -name 'approval.failed.*.env' | wc -l)" -eq 2 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name "${MIGRATED_RUN_ID}-${MIGRATED_SHA}-${MIGRATED_ARTIFACT_SHA256}-*.consumed" | wc -l)" -eq 1 ]]

set +e
run_deploy rollback "$MIGRATED_HANDLE" >"$ROOT/incompatible-rollback.log" 2>&1
INCOMPATIBLE_ROLLBACK_RC=$?
set -e
[[ "$INCOMPATIBLE_ROLLBACK_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$MIGRATED_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "new frontend" ]]
grep -q '^STATE=deployed$' "$MIGRATED_HANDLE/release.env"
grep -q 'rollback target has a different migration manifest' "$ROOT/incompatible-rollback.log"

printf 'deploy and rollback sandbox tests: PASS\n'
