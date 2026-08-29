#!/usr/bin/bash -p

set -Eeuo pipefail
umask 077
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONSTARTUP PYTHONINSPECT || true
unset PYTHONHOME PYTHONPATH MYPYPATH MYPY_CONFIG_FILE

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
cp "$SCRIPT_DIR/../package.json" "$BUILDER/package.json"
cp "$SCRIPT_DIR/../package-lock.json" "$BUILDER/package-lock.json"
WHEELHOUSE="$ROOT/wheelhouse"
mkdir -p "$WHEELHOUSE"
/usr/bin/python3.12 -I -S - "$WHEELHOUSE/demo_runtime-1.0-py3-none-any.whl" <<'PY'
import base64
import csv
import hashlib
import io
from pathlib import Path
import sys
import zipfile

target = Path(sys.argv[1])
files = {
    "demo_runtime.py": b"def main():\n    return 0\n",
    "demo_runtime-1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: demo-runtime\nVersion: 1.0\n",
    "demo_runtime-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: unihub-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    "demo_runtime-1.0.dist-info/entry_points.txt": b"[console_scripts]\ndemo-runtime=demo_runtime:main\n",
}
rows = []
for name, payload in files.items():
    digest = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
    rows.append([name, f"sha256={digest}", str(len(payload))])
rows.append(["demo_runtime-1.0.dist-info/RECORD", "", ""])
buffer = io.StringIO(newline="")
csv.writer(buffer, lineterminator="\n").writerows(rows)
files["demo_runtime-1.0.dist-info/RECORD"] = buffer.getvalue().encode()
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
    for name, payload in files.items():
        wheel.writestr(name, payload)
PY
WHEEL_SHA256="$(sha256sum "$WHEELHOUSE/demo_runtime-1.0-py3-none-any.whl" | awk '{print $1}')"
printf 'demo-runtime==1.0 --hash=sha256:%s\n' "$WHEEL_SHA256" \
  >"$BUILDER/backend/requirements.lock"
printf 'print("old")\n' >"$BUILDER/backend/main.py"
printf 'dist/\ndata/\nbackend/outputs/\nbackend/venv/\n' >"$BUILDER/.gitignore"
cp "$SCRIPT_DIR/systemd/unihub-backend.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/../unihub-worker.service" "$BUILDER/"
cp "$DEPLOY_SCRIPT" "$BUILDER/ops/deploy-retail-artifact.sh"
cp "$SCRIPT_DIR/systemd/unihub-import-worker.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/systemd/unihub-retail-migrate.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/provision-retail-service-identities.sh" "$BUILDER/ops/"
cp "$SCRIPT_DIR/provision-retail-salary-export-database.sh" "$BUILDER/ops/"
cp "$SCRIPT_DIR/observability/retail-process-scrape.yml" "$BUILDER/ops/observability/"
cp "$SCRIPT_DIR/observability/retail-slo-rules.yml" "$BUILDER/ops/observability/"
mkdir -p "$BUILDER/scripts"
cp "$SCRIPT_DIR/../scripts/release_identity.py" "$BUILDER/scripts/release_identity.py"
mkdir -p "$BUILDER/backend/db/migrations"
printf '%s\n' \
  '{' \
  '  "version": 1,' \
  '  "baseline": {' \
  '    "file": "schema_v2.sql",' \
  '    "sha256": "0000000000000000000000000000000000000000000000000000000000000000",' \
  '    "incorporated_through": "001_first.sql"' \
  '  },' \
  '  "migrations": {' \
  '    "001_first.sql": "1111111111111111111111111111111111111111111111111111111111111111"' \
  '  }' \
  '}' >"$BUILDER/backend/db/migrations/manifest.json"
git -C "$BUILDER" add .
git -C "$BUILDER" commit --quiet -m old
OLD_SHA="$(git -C "$BUILDER" rev-parse HEAD)"
git -C "$BUILDER" push --quiet -u origin main
git --git-dir="$REMOTE" symbolic-ref HEAD refs/heads/main

# The candidate has isolated Grile/export/salary-export workers plus a disabled legacy
# tombstone; the old release intentionally has none of them.
cp "$SCRIPT_DIR/systemd/unihub-grile-worker.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/systemd/unihub-export-worker.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/systemd/unihub-salary-export-worker.service" "$BUILDER/ops/systemd/"
cp "$SCRIPT_DIR/systemd/unihub-legacy-worker.service" "$BUILDER/ops/systemd/"

git clone --quiet "$REMOTE" "$LIVE"
mkdir -p "$LIVE/dist"
/usr/bin/python3.12 -I -m venv "$LIVE/backend/venv"
printf 'old frontend\n' >"$LIVE/dist/index.html"
chmod 0700 "$LIVE" "$LIVE/backend" "$LIVE/dist"
chmod 0600 "$LIVE/backend/main.py" "$LIVE/dist/index.html"
[[ "$(stat -c '%a' "$LIVE/backend/main.py")" == "600" ]]

venv_identity_hash() {
  /usr/bin/python3.12 -I -S - "$LIVE/backend/venv" <<'PY'
import hashlib
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
entries = []
for path in sorted(root.rglob("*")):
    relative = str(path.relative_to(root))
    if path.is_symlink():
        entries.append([relative, "symlink", path.readlink().as_posix()])
    elif path.is_file():
        entries.append([relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()])
print(hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest())
PY
}

OLD_VENV_HASH="$(venv_identity_hash)"

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
mkdir -p "$ROOT/enabled"
for unit in unihub-backend.service unihub-worker.service unihub-import-worker.service; do
  : >"$ROOT/enabled/$unit"
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
chmod 0700 "$BUILDER/dist" "$BUILDER/dist/assets"
chmod 0600 "$BUILDER/dist/index.html" "$BUILDER/dist/assets/app.js"
build_release() {
  local source_sha="$1"
  local output_dir="$2"
  local evidence_dir="${3:-}"
  local -a release_env=(PYTHON_RUNTIME_WHEELHOUSE_PATH="$WHEELHOUSE")
  if [[ -n "$evidence_dir" ]]; then
    release_env+=(
      RELEASE_A_EVIDENCE_DIR="$evidence_dir"
      RELEASE_A_EVIDENCE_RUN_ID="$CI_RUN_ID"
    )
  fi
  (
    cd "$BUILDER"
    env "${release_env[@]}" "$BUILD_SCRIPT" "$source_sha" "$output_dir"
  ) >/dev/null
}

make_release_a_evidence() {
  local source_sha="$1"
  local output_dir="$2"
  mkdir -p "$output_dir"
  /usr/bin/python3.12 -I -S - "$source_sha" "$output_dir" <<'PY'
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

source_sha, output = sys.argv[1:]
root = pathlib.Path(output)
names = (
    "test_069_is_additive_empty_and_old_ai_insert_remains_compatible",
    "test_069_seals_cohort_and_requires_exact_completed_run_lineage",
    "test_069_outbox_is_canonical_private_ordered_and_replayable",
    "test_069_runtime_roles_have_exact_producer_privileges",
    "test_release_a_runtime_starts_and_is_ready_on_069",
    "test_pre_069_manifest_is_refused_after_schema_upgrade",
)
digests = {}
for filename in ("release-a-schema-empty.xml", "release-a-schema-restored.xml"):
    suite = ET.Element(
        "testsuite", tests="6", failures="0", errors="0", skipped="0"
    )
    for name in names:
        ET.SubElement(
            suite,
            "testcase",
            classname="backend.tests.test_release_a_schema_069",
            name=name,
        )
    path = root / filename
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    digests[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
(root / "schema-gate.json").write_text(
    json.dumps(
        {
            "result": "PASS",
            "release_a_sha": source_sha,
            "junit_empty_sha256": digests["release-a-schema-empty.xml"],
            "junit_restored_sha256": digests["release-a-schema-restored.xml"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n",
    encoding="utf-8",
)
PY
}

RELEASE_DIR="$ROOT/release"
RELEASE_A_EVIDENCE="$ROOT/release-a-evidence"
make_release_a_evidence "$NEW_SHA" "$RELEASE_A_EVIDENCE"
build_release "$NEW_SHA" "$RELEASE_DIR" "$RELEASE_A_EVIDENCE"
ARTIFACT="$RELEASE_DIR/retail-release-${NEW_SHA}.tar.gz"
[[ "$(<"$RELEASE_DIR/SOURCE_SHA")" == "$NEW_SHA" ]]
(cd "$RELEASE_DIR" && sha256sum --check SHA256SUMS >/dev/null)
for release_a_evidence in \
  schema-gate.json \
  release-a-schema-empty.xml \
  release-a-schema-restored.xml; do
  [[ -s "$RELEASE_DIR/$release_a_evidence" && ! -L "$RELEASE_DIR/$release_a_evidence" ]]
done
for runtime_supply in \
  PYTHON_RUNTIME_SUPPLY.json \
  PYTHON_RUNTIME_REQUIREMENTS.lock \
  PYTHON_RUNTIME_WHEELS.tar.gz; do
  [[ -s "$RELEASE_DIR/$runtime_supply" && ! -L "$RELEASE_DIR/$runtime_supply" ]]
done
ARTIFACT_SHA256="$(sha256sum "$ARTIFACT" | awk '{print $1}')"
/usr/bin/python3.12 -I -S - \
  "$RELEASE_DIR" "$NEW_SHA" "$ARTIFACT_SHA256" \
  "$BUILDER/backend/db/migrations/manifest.json" <<'PY'
import json
import pathlib
import sys

release_dir, source_sha, artifact_sha256, builder_migrations = sys.argv[1:]
manifest_path = pathlib.Path(release_dir) / "RELEASE_MANIFEST.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
errors = []

expected_release_id = f"retail-release-{source_sha}"
if manifest.get("releaseId") != expected_release_id:
    errors.append(
        f"releaseId mismatch: {manifest.get('releaseId')!r} vs {expected_release_id!r}"
    )

migrations_payload = json.loads(pathlib.Path(builder_migrations).read_text(encoding="utf-8"))
migrations = migrations_payload.get("migrations")
if not isinstance(migrations, dict) or not migrations:
    raise SystemExit("test fixture migrations manifest is invalid")
expected_head = max(migrations.keys(), key=lambda n: int(n.split("_", 1)[0]))
if manifest.get("migrationHead") != expected_head:
    errors.append(
        f"migrationHead mismatch: {manifest.get('migrationHead')!r} vs {expected_head!r}"
    )

inventory = manifest.get("sha256")
archive = manifest.get("archive")
if not isinstance(inventory, dict) or not isinstance(archive, str):
    raise SystemExit("release manifest sha256 inventory or archive is invalid")
if inventory.get(archive) != artifact_sha256:
    errors.append("sha256 inventory archive digest mismatch")
sbom_digest = inventory.get("SBOM.cdx.json")
if not isinstance(sbom_digest, str) or len(sbom_digest) != 64:
    errors.append("sha256 inventory SBOM digest missing")
if manifest.get("artifactSha256") != artifact_sha256:
    errors.append(
        f"explicit artifactSha256 mismatch: {manifest.get('artifactSha256')!r}"
    )
if manifest.get("sbomSha256") != sbom_digest:
    errors.append(
        f"explicit sbomSha256 mismatch: {manifest.get('sbomSha256')!r}"
    )

if errors:
    raise SystemExit("D2 manifest identity mismatch: " + "; ".join(errors))
PY

run_deploy() {
  RETAIL_DEPLOY_TEST_MODE=1 \
  RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
    /usr/bin/bash -p "$DEPLOY_SCRIPT" "$@"
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
    /usr/bin/bash -p "$APPROVE_SCRIPT" "$run_id" "$source_sha" "$artifact_sha256"
}

# The one-time privileged bootstrap is independently recoverable and cannot be
# invoked by the deploy runner identity itself.
mkdir -p "$OPS/scripts"
printf '#!/usr/bin/bash -p\nexit 7\n' >"$OPS/scripts/deploy-retail-artifact.sh"
chmod 0755 "$OPS/scripts/deploy-retail-artifact.sh"
BOOTSTRAP_OLD_SHA="$(sha256sum "$OPS/scripts/deploy-retail-artifact.sh" | awk '{print $1}')"
run_deploy bootstrap-entrypoint "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
cmp -- "$DEPLOY_SCRIPT" "$OPS/scripts/deploy-retail-artifact.sh"
BOOTSTRAP_NEW_SHA="$(sha256sum "$DEPLOY_SCRIPT" | awk '{print $1}')"
[[ "$(find "$OPS/backups/retail-deploy-entrypoints" -maxdepth 1 -type f \
  -name "*-${BOOTSTRAP_OLD_SHA}.sh" | wc -l)" -eq 1 ]]
/usr/bin/python3.12 -I -S - \
  "$OPS/release-evidence/deploy-entrypoint-bootstrap/${BOOTSTRAP_NEW_SHA}.json" \
  "$BOOTSTRAP_NEW_SHA" "$BOOTSTRAP_OLD_SHA" "$NEW_SHA" "$ARTIFACT_SHA256" <<'PY'
import json
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
if (
    payload.get("result") != "PASS"
    or payload.get("new_sha256") != sys.argv[2]
    or payload.get("old_sha256") != sys.argv[3]
    or payload.get("mode") != "0755"
    or payload.get("source_release_sha") != sys.argv[4]
    or payload.get("source_artifact_sha256") != sys.argv[5]
):
    raise SystemExit("deploy entrypoint bootstrap evidence mismatch")
PY
BOOTSTRAP_EVIDENCE_SHA="$(sha256sum \
  "$OPS/release-evidence/deploy-entrypoint-bootstrap/${BOOTSTRAP_NEW_SHA}.json" \
  | awk '{print $1}')"
run_deploy bootstrap-entrypoint "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
[[ "$(find "$OPS/backups/retail-deploy-entrypoints" -maxdepth 1 -type f | wc -l)" -eq 1 ]]
[[ "$(sha256sum \
  "$OPS/release-evidence/deploy-entrypoint-bootstrap/${BOOTSTRAP_NEW_SHA}.json" \
  | awk '{print $1}')" == "$BOOTSTRAP_EVIDENCE_SHA" ]]
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
SUDO_USER=unihub-deploy \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" \
    bootstrap-entrypoint "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
RUNNER_BOOTSTRAP_RC=$?
set -e
[[ "$RUNNER_BOOTSTRAP_RC" -ne 0 ]]

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
  /usr/bin/bash -p "$APPROVE_SCRIPT" "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null 2>&1
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

# Phase I regression: missing required runtime user must fail closed
# BEFORE consuming the one-time approval, mutating the deployment
# backup store, or advancing the live Git HEAD. The SAME unconsumed
# ACTIVE_APPROVAL proves both paths: injected missing identity -> fail
# closed with operator-visible remediation; no injection -> existing
# success path consumes the approval normally.
PHASE_I_MISSING_USER="unihub-grile"
PHASE_I_PROVISION_APPLY="/opt/Mobiup/ops/scripts/provision-retail-service-identities.sh apply"
PHASE_I_PROVISION_VERIFY="/opt/Mobiup/ops/scripts/provision-retail-service-identities.sh verify"
PHASE_I_LIVE_HEAD_BEFORE="$(git -C "$LIVE" rev-parse HEAD)"
PHASE_I_BACKUP_COUNT_BEFORE="$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"
PHASE_I_APPROVED_COUNT_BEFORE="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' | wc -l)"
PHASE_I_CLAIMED_COUNT_BEFORE="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.claimed.*' | wc -l)"
PHASE_I_CONSUMED_COUNT_BEFORE="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)"
PHASE_I_FAILED_COUNT_BEFORE="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_MISSING_RUNTIME_IDENTITY="$PHASE_I_MISSING_USER" \
  /usr/bin/bash -p "$OPS/scripts/deploy-retail-artifact.sh" \
    "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
    >"$ROOT/phase-i-missing-identity.log" 2>&1
PHASE_I_MISSING_RC=$?
set -e
[[ "$PHASE_I_MISSING_RC" -ne 0 ]] \
  || { echo "missing-identity deploy unexpectedly succeeded" >&2; exit 1; }
grep -Fq "required runtime service user is absent: $PHASE_I_MISSING_USER" \
  "$ROOT/phase-i-missing-identity.log" \
  || { echo "missing-identity deploy did not report the exact missing account" >&2; exit 1; }
grep -Fq "$PHASE_I_PROVISION_APPLY" "$ROOT/phase-i-missing-identity.log" \
  || { echo "missing-identity deploy did not direct operator to the apply remediation" >&2; exit 1; }
grep -Fq "$PHASE_I_PROVISION_VERIFY" "$ROOT/phase-i-missing-identity.log" \
  || { echo "missing-identity deploy did not direct operator to the verify remediation" >&2; exit 1; }
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$PHASE_I_LIVE_HEAD_BEFORE" ]] \
  || { echo "missing-identity deploy mutated the live Git HEAD" >&2; exit 1; }
[[ "$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)" \
  == "$PHASE_I_BACKUP_COUNT_BEFORE" ]] \
  || { echo "missing-identity deploy mutated the deployment backup store" >&2; exit 1; }
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' | wc -l)" \
  == "$PHASE_I_APPROVED_COUNT_BEFORE" ]] \
  || { echo "missing-identity deploy consumed or replaced the active approval" >&2; exit 1; }
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.claimed.*' | wc -l)" \
  == "$PHASE_I_CLAIMED_COUNT_BEFORE" ]] \
  || { echo "missing-identity deploy moved the approval to claimed state" >&2; exit 1; }
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" \
  == "$PHASE_I_CONSUMED_COUNT_BEFORE" ]] \
  || { echo "missing-identity deploy finalized the approval as consumed" >&2; exit 1; }
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" \
  == "$PHASE_I_FAILED_COUNT_BEFORE" ]] \
  || { echo "missing-identity deploy finalized the approval as failed" >&2; exit 1; }

# Out-of-list test-only injection must be rejected deterministically, not
# silently coerced to a missing-user error. The same approval must remain
# untouched and the deployment backup store must stay clean.
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_MISSING_RUNTIME_IDENTITY=not-a-real-user \
  /usr/bin/bash -p "$OPS/scripts/deploy-retail-artifact.sh" \
    "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
    >"$ROOT/phase-i-bogus-injection.log" 2>&1
PHASE_I_BOGUS_RC=$?
set -e
[[ "$PHASE_I_BOGUS_RC" -ne 0 ]] \
  || { echo "out-of-list injection unexpectedly succeeded" >&2; exit 1; }
grep -Fq "RETAIL_DEPLOY_TEST_MISSING_RUNTIME_IDENTITY must match a required runtime user" \
  "$ROOT/phase-i-bogus-injection.log" \
  || { echo "out-of-list injection did not fail with the deterministic guard" >&2; exit 1; }
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$PHASE_I_LIVE_HEAD_BEFORE" ]] \
  || { echo "out-of-list injection mutated the live Git HEAD" >&2; exit 1; }
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.claimed.*' | wc -l)" \
  == "$PHASE_I_CLAIMED_COUNT_BEFORE" ]] \
  || { echo "out-of-list injection moved the approval to claimed state" >&2; exit 1; }

# Regression test for P1: the production-style privileged entrypoint at
# $OPS/scripts/deploy-retail-artifact.sh is provisioned without a sibling
# scripts/release_identity.py. The OLD lookup would resolve to
# $OPS/scripts/release_identity.py (or its parent) and fail before any
# claim_approval; the NEW lookup uses the verified artifact tree at
# $artifact_tree/scripts/release_identity.py. The first deploy must go
# through the bootstrap entrypoint to demonstrate that.
[[ ! -e "$OPS/scripts/release_identity.py" ]] \
  || { echo "regression fixture contamination: bootstrap sibling helper must not exist" >&2; exit 1; }
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
  /usr/bin/bash -p "$OPS/scripts/deploy-retail-artifact.sh" \
    "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ -L "$LIVE/backend/venv/bin/python" \
  && "$(readlink -- "$LIVE/backend/venv/bin/python")" == "python3.12" ]]
[[ -L "$LIVE/backend/venv/bin/python3" \
  && "$(readlink -- "$LIVE/backend/venv/bin/python3")" == "python3.12" ]]
[[ -L "$LIVE/backend/venv/bin/python3.12" \
  && "$(readlink -- "$LIVE/backend/venv/bin/python3.12")" == "/usr/bin/python3.12" ]]
[[ "$(readlink -f "$LIVE/backend/venv/bin/python")" == "/usr/bin/python3.12" ]]
[[ ! -e "$LIVE/backend/venv/bin/demo-runtime" \
  && ! -L "$LIVE/backend/venv/bin/demo-runtime" ]]
/usr/bin/python3.12 -I -S - "$LIVE/backend/venv" <<'PY'
import csv
import pathlib
import sys

venv = pathlib.Path(sys.argv[1])
record = venv / "lib/python3.12/site-packages/demo_runtime-1.0.dist-info/RECORD"
rows = {row[0]: row[1:] for row in csv.reader(record.read_text(encoding="utf-8").splitlines())}
if "../../../bin/demo-runtime" in rows:
    raise SystemExit("removed console script remains in installed RECORD")
PY
NEW_VENV_HASH="$(venv_identity_hash)"
[[ "$(<"$LIVE/dist/index.html")" == "new frontend" ]]
[[ "$(stat -c '%a' "$LIVE")" == "755" ]]
[[ "$(stat -c '%a' "$LIVE/backend")" == "755" ]]
[[ "$(stat -c '%a' "$LIVE/backend/main.py")" == "644" ]]
[[ "$(stat -c '%U:%G:%a' "$LIVE/dist")" == "$(id -un):$(id -gn):750" ]]
[[ "$(stat -c '%U:%G:%a' "$LIVE/dist/assets")" == "$(id -un):$(id -gn):750" ]]
[[ "$(stat -c '%U:%G:%a' "$LIVE/dist/index.html")" == "$(id -un):$(id -gn):640" ]]
[[ "$(stat -c '%U:%G:%a' "$LIVE/dist/assets/app.js")" == "$(id -un):$(id -gn):640" ]]
[[ -d "$LIVE/data/export_artifacts/salary" ]]
[[ "$(stat -c '%a' "$LIVE/data/export_artifacts/salary")" == "770" ]]
for shared_root in \
  "$LIVE/data/import_spool" \
  "$LIVE/data/promo_generations" \
  "$LIVE/backend/outputs/grile" \
  "$LIVE/data/export_artifacts" \
  "$LIVE/data/export_artifacts/salary"; do
  [[ "$(stat -c '%U:%G:%a' "$shared_root")" == "$(id -un):$(id -gn):770" ]]
done
for unit in \
  unihub-backend.service \
  unihub-worker.service \
  unihub-import-worker.service \
  unihub-grile-worker.service \
  unihub-export-worker.service \
  unihub-salary-export-worker.service \
  unihub-legacy-worker.service \
  unihub-retail-migrate.service; do
  [[ -L "$ROOT/etc/systemd/system/$unit" ]]
  [[ "$(readlink -f "$ROOT/etc/systemd/system/$unit")" == "$ROOT/runtime-releases/$NEW_SHA/systemd/$unit" ]]
done
for unit in unihub-backend.service unihub-worker.service unihub-import-worker.service \
  unihub-grile-worker.service unihub-export-worker.service \
  unihub-salary-export-worker.service; do
  [[ -e "$ROOT/enabled/$unit" ]]
done
[[ ! -e "$ROOT/enabled/unihub-legacy-worker.service" ]]
[[ ! -e "$ROOT/node-exporter/textfile/unihub_retail_deploy.prom" ]]
grep -Fxq 'PROMETHEUS_DOCKER_GATEWAY=172.23.0.1' "$OPS/prometheus/unihub-retail-network.env"
grep -Fxq 'PROMETHEUS_DOCKER_SUBNET=172.23.0.0/16' "$OPS/prometheus/unihub-retail-network.env"
grep -Fxq 'WORKER_METRICS_HOST=172.23.0.1' "$OPS/prometheus/unihub-retail-network.env"
[[ "$(grep -Fc '172.23.0.1:' "$OPS/prometheus/scrape.d/unihub-retail.yml")" -eq 6 ]]
if grep -Eq '__PROMETHEUS_DOCKER_GATEWAY__|0\.0\.0\.0|127\.0\.0\.1' \
  "$OPS/prometheus/scrape.d/unihub-retail.yml"; then
  exit 1
fi
cmp "$SCRIPT_DIR/observability/retail-slo-rules.yml" \
  "$OPS/prometheus/rules/retail-slo-rules.yml"
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit" ]]
HANDLE="$(rg -l '^STATE=deployed$' "$OPS/backups/retail-deploy"/*/release.env | xargs -r -n1 dirname | tail -1)"
[[ -n "$HANDLE" ]]
grep -q '^STATE=deployed$' "$HANDLE/release.env"
grep -q "^ci_run_id=$CI_RUN_ID$" "$HANDLE/approval.env"
grep -q "^source_sha=$NEW_SHA$" "$HANDLE/approval.env"
grep -q "^artifact_sha256=$ARTIFACT_SHA256$" "$HANDLE/approval.env"
grep -q '^approved_by_os=test-approver$' "$HANDLE/approval.env"
DEPLOYED_AT_UTC_AFTER_FIRST="$(sed -n 's/^DEPLOYED_AT_UTC=//p' "$HANDLE/release.env" | head -n1)"
[[ "$DEPLOYED_AT_UTC_AFTER_FIRST" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] \
  || { echo "DEPLOYED_AT_UTC is not a UTC ISO timestamp: '$DEPLOYED_AT_UTC_AFTER_FIRST'" >&2; exit 1; }
/usr/bin/python3.12 -I -S - \
  "$HANDLE/release.env" "$NEW_SHA" "$OLD_SHA" "$ARTIFACT_SHA256" "$DEPLOYED_AT_UTC_AFTER_FIRST" <<'PY'
import pathlib
import re
import sys

release_env, new_sha, old_sha, artifact_sha256, expected_deployed_at = sys.argv[1:]
text = pathlib.Path(release_env).read_text(encoding="utf-8")
fields = {}
for line in text.splitlines():
    if not line or "=" not in line:
        continue
    key, _, value = line.partition("=")
    fields.setdefault(key, []).append(value)
errors = []
required = [
    "PROMOTION_SCHEMA_VERSION",
    "RELEASE_ID",
    "SOURCE_SHA",
    "MIGRATION_HEAD",
    "ARTIFACT_SHA256",
    "SBOM_SHA256",
    "DEPLOYED_AT_UTC",
    "PREDECESSOR_RELEASE_ID",
    "PREDECESSOR_SHA",
    "ROLLBACK_RELEASE_ID",
    "ROLLBACK_SHA",
    "OLD_SHA",
    "NEW_SHA",
    "STATE",
    "UPDATED_AT",
]
for key in required:
    values = fields.get(key)
    if not values or len(values) != 1:
        errors.append(f"{key} missing or duplicated: {values!r}")
if fields.get("PROMOTION_SCHEMA_VERSION") != ["1"]:
    errors.append("PROMOTION_SCHEMA_VERSION must be exactly 1")
if fields.get("RELEASE_ID") != [f"retail-release-{new_sha}"]:
    errors.append(f"RELEASE_ID must equal retail-release-{new_sha}")
if fields.get("SOURCE_SHA") != [new_sha]:
    errors.append("SOURCE_SHA mismatch")
if fields.get("ARTIFACT_SHA256") != [artifact_sha256]:
    errors.append("ARTIFACT_SHA256 mismatch")
if fields.get("OLD_SHA") != [old_sha]:
    errors.append("OLD_SHA mismatch")
if fields.get("NEW_SHA") != [new_sha]:
    errors.append("NEW_SHA mismatch")
if fields.get("STATE") != ["deployed"]:
    errors.append("STATE must be deployed")
if fields.get("PREDECESSOR_SHA") != [old_sha]:
    errors.append("PREDECESSOR_SHA must equal old_sha")
if fields.get("PREDECESSOR_RELEASE_ID") != [f"retail-release-{old_sha}"]:
    errors.append("PREDECESSOR_RELEASE_ID must equal retail-release-old_sha")
if fields.get("ROLLBACK_SHA") != [old_sha]:
    errors.append("ROLLBACK_SHA must equal old_sha")
if fields.get("ROLLBACK_RELEASE_ID") != [f"retail-release-{old_sha}"]:
    errors.append("ROLLBACK_RELEASE_ID must equal retail-release-old_sha")
migration_head_values = fields.get("MIGRATION_HEAD", [])
if not migration_head_values or not re.fullmatch(
    r"[0-9]{3}_[A-Za-z0-9_]+\.sql", migration_head_values[0]
):
    errors.append(f"MIGRATION_HEAD invalid: {migration_head_values!r}")
sbom_sha_values = fields.get("SBOM_SHA256", [])
if not sbom_sha_values or not re.fullmatch(r"[0-9a-f]{64}", sbom_sha_values[0]):
    errors.append(f"SBOM_SHA256 invalid: {sbom_sha_values!r}")
deployed_values = fields.get("DEPLOYED_AT_UTC", [])
if not deployed_values or not re.fullmatch(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
    deployed_values[0],
):
    errors.append(f"DEPLOYED_AT_UTC invalid: {deployed_values!r}")
elif deployed_values[0] != expected_deployed_at:
    errors.append(
        f"DEPLOYED_AT_UTC {deployed_values[0]!r} != parsed {expected_deployed_at!r}"
    )
if errors:
    raise SystemExit("D2 release.env identity mismatch: " + "; ".join(errors))
PY
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.approved' | wc -l)" -eq 0 ]]
BACKUP_COUNT="$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d | wc -l)"
printf 'web upload\n' >"$LIVE/data/import_spool/web-owned.upload"
chmod 0660 "$LIVE/data/import_spool/web-owned.upload"
set +e
RETAIL_DEPLOY_TEST_IMPORT_FILE_USER=not-the-file-owner \
RETAIL_DEPLOY_TEST_WEB_FILE_USER=also-not-the-file-owner \
  run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
  >/dev/null 2>&1
UNTRUSTED_SPOOL_OWNER_RC=$?
set -e
[[ "$UNTRUSTED_SPOOL_OWNER_RC" -ne 0 ]]
RETAIL_DEPLOY_TEST_IMPORT_FILE_USER=not-the-file-owner \
RETAIL_DEPLOY_TEST_WEB_FILE_USER="$(id -un)" \
  run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.consumed' | wc -l)" -eq 1 ]]
[[ "$(find "$OPS/backups/retail-deploy" -mindepth 1 -maxdepth 1 -type d | wc -l)" -eq "$BACKUP_COUNT" ]]

ln -sfn -- /usr/bin/false "$LIVE/backend/venv/bin/python3.12"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
REVERIFY_TAMPERED_INTERPRETER_RC=$?
set -e
[[ "$REVERIFY_TAMPERED_INTERPRETER_RC" -ne 0 ]]
ln -sfn -- /usr/bin/python3.12 "$LIVE/backend/venv/bin/python3.12"
[[ "$(venv_identity_hash)" == "$NEW_VENV_HASH" ]]

printf '#!/bin/sh\nexit 0\n' >"$LIVE/backend/venv/bin/unsigned-runtime-tool"
chmod 0755 "$LIVE/backend/venv/bin/unsigned-runtime-tool"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
REVERIFY_UNSIGNED_BIN_RC=$?
set -e
[[ "$REVERIFY_UNSIGNED_BIN_RC" -ne 0 ]]
rm -- "$LIVE/backend/venv/bin/unsigned-runtime-tool"
[[ "$(venv_identity_hash)" == "$NEW_VENV_HASH" ]]

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
NEWER_VENV_HASH="$(venv_identity_hash)"
DEPLOYED_AT_UTC_BEFORE_SECOND_ROLLBACK="$(sed -n 's/^DEPLOYED_AT_UTC=//p' "$SECOND_HANDLE/release.env" | head -n1)"
[[ "$DEPLOYED_AT_UTC_BEFORE_SECOND_ROLLBACK" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] \
  || { echo "second deploy DEPLOYED_AT_UTC is not a UTC ISO timestamp: '$DEPLOYED_AT_UTC_BEFORE_SECOND_ROLLBACK'" >&2; exit 1; }

mv -- "$SECOND_HANDLE/venv-before.json" "$SECOND_HANDLE/venv-before.json.missing-test"
set +e
run_deploy rollback "$SECOND_HANDLE" >"$ROOT/rollback-missing-venv-evidence.log" 2>&1
ROLLBACK_MISSING_VENV_EVIDENCE_RC=$?
set -e
[[ "$ROLLBACK_MISSING_VENV_EVIDENCE_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEWER_SHA" ]]
[[ "$(venv_identity_hash)" == "$NEWER_VENV_HASH" ]]
if grep -q 'TEST systemctl stop ' "$ROOT/rollback-missing-venv-evidence.log"; then
  exit 1
fi
mv -- "$SECOND_HANDLE/venv-before.json.missing-test" "$SECOND_HANDLE/venv-before.json"

mv -- "$SECOND_HANDLE/python-runtime-supply.old/PYTHON_RUNTIME_SUPPLY.json" \
  "$SECOND_HANDLE/python-runtime-supply.old/PYTHON_RUNTIME_SUPPLY.json.missing-test"
set +e
run_deploy rollback "$SECOND_HANDLE" >"$ROOT/rollback-missing-managed-supply.log" 2>&1
ROLLBACK_MISSING_MANAGED_SUPPLY_RC=$?
set -e
[[ "$ROLLBACK_MISSING_MANAGED_SUPPLY_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEWER_SHA" ]]
[[ "$(venv_identity_hash)" == "$NEWER_VENV_HASH" ]]
if grep -q 'TEST systemctl stop ' "$ROOT/rollback-missing-managed-supply.log"; then
  exit 1
fi
mv -- "$SECOND_HANDLE/python-runtime-supply.old/PYTHON_RUNTIME_SUPPLY.json.missing-test" \
  "$SECOND_HANDLE/python-runtime-supply.old/PYTHON_RUNTIME_SUPPLY.json"

run_deploy rollback "$SECOND_HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(venv_identity_hash)" == "$NEW_VENV_HASH" ]]
[[ "$(stat -c '%a' "$LIVE/backend/main.py")" == "644" ]]
[[ "$(stat -c '%a' "$LIVE/dist/index.html")" == "640" ]]
[[ "$(readlink -f "$ROOT/etc/systemd/system/unihub-backend.service")" == "$ROOT/runtime-releases/$NEW_SHA/systemd/unihub-backend.service" ]]
[[ "$(<"$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md")" == "published audit" ]]
[[ "$(<"$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md")" == "published plan" ]]
DEPLOYED_AT_UTC_AFTER_ROLLBACK="$(sed -n 's/^DEPLOYED_AT_UTC=//p' "$SECOND_HANDLE/release.env" | head -n1)"
[[ "$DEPLOYED_AT_UTC_AFTER_ROLLBACK" == "$DEPLOYED_AT_UTC_BEFORE_SECOND_ROLLBACK" ]] \
  || { echo "DEPLOYED_AT_UTC was not preserved after manual rollback: $DEPLOYED_AT_UTC_BEFORE_SECOND_ROLLBACK vs $DEPLOYED_AT_UTC_AFTER_ROLLBACK" >&2; exit 1; }
grep -q '^STATE=rolled_back$' "$SECOND_HANDLE/release.env"
/usr/bin/python3.12 -I -S - "$SECOND_HANDLE/release.env" "$NEWER_SHA" "$NEW_SHA" <<'PY'
import pathlib
import sys

release_env, newer_sha, new_sha = sys.argv[1:]
text = pathlib.Path(release_env).read_text(encoding="utf-8")
fields = {}
for line in text.splitlines():
    if not line or "=" not in line:
        continue
    key, _, value = line.partition("=")
    fields.setdefault(key, []).append(value)
errors = []
if fields.get("RELEASE_ID") != [f"retail-release-{newer_sha}"]:
    errors.append(f"RELEASE_ID must equal retail-release-{newer_sha}")
if fields.get("SOURCE_SHA") != [newer_sha]:
    errors.append("SOURCE_SHA must remain newer_sha")
if fields.get("NEW_SHA") != [newer_sha]:
    errors.append("NEW_SHA must remain newer_sha")
if fields.get("OLD_SHA") != [new_sha]:
    errors.append("OLD_SHA must remain new_sha")
if fields.get("PREDECESSOR_SHA") != [new_sha]:
    errors.append("PREDECESSOR_SHA must remain new_sha")
if fields.get("ROLLBACK_SHA") != [new_sha]:
    errors.append("ROLLBACK_SHA must remain new_sha")
if fields.get("PREDECESSOR_RELEASE_ID") != [f"retail-release-{new_sha}"]:
    errors.append("PREDECESSOR_RELEASE_ID must remain retail-release-new_sha")
if fields.get("ROLLBACK_RELEASE_ID") != [f"retail-release-{new_sha}"]:
    errors.append("ROLLBACK_RELEASE_ID must remain retail-release-new_sha")
if fields.get("STATE") != ["rolled_back"]:
    errors.append("STATE must be rolled_back")
if errors:
    raise SystemExit("D2 release.env post-rollback mismatch: " + "; ".join(errors))
PY

# Once a release is contract-managed, removing its signed runtime supply must
# fail before any service stop or runtime switch; it may never degrade to the
# one-time legacy-opaque baseline compatibility path.
MISSING_SUPPLY_RUN_ID="$((CI_RUN_ID + 11))"
approve_release "$MISSING_SUPPLY_RUN_ID" "$NEWER_SHA" "$NEWER_ARTIFACT_SHA256" >/dev/null
mv -- "$ROOT/runtime-releases/$NEW_SHA/python-runtime-supply" \
  "$ROOT/runtime-releases/$NEW_SHA/python-runtime-supply.missing-test"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" \
    "$NEWER_ARTIFACT" "$NEWER_SHA" "$MISSING_SUPPLY_RUN_ID" "$NEWER_ARTIFACT_SHA256" \
    >"$ROOT/missing-runtime-supply.log" 2>&1
MISSING_RUNTIME_SUPPLY_RC=$?
set -e
[[ "$MISSING_RUNTIME_SUPPLY_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$NEW_SHA" ]]
[[ "$(venv_identity_hash)" == "$NEW_VENV_HASH" ]]
if grep -q 'TEST systemctl stop ' "$ROOT/missing-runtime-supply.log"; then
  exit 1
fi
mv -- "$ROOT/runtime-releases/$NEW_SHA/python-runtime-supply.missing-test" \
  "$ROOT/runtime-releases/$NEW_SHA/python-runtime-supply"

# P2.1 regression: corrupting a D2 identity field on the active deployed
# release.env must reject same-SHA reverification BEFORE any runtime,
# frontend or health mutation. The reverify path runs
# copy_and_verify_artifact + verify_candidate_identity first, then it
# MUST fail at the D2 identity comparison step.
git --git-dir="$REMOTE" update-ref refs/heads/main "$NEW_SHA"
LIVE_HEAD_BEFORE_REVERIFY="$(git -C "$LIVE" rev-parse HEAD)"
DIST_BEFORE_REVERIFY="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
ORIGINAL_RELEASE_ID="$(sed -n 's/^RELEASE_ID=//p' "$HANDLE/release.env" | head -n1)"
sed -i 's|^RELEASE_ID=.*|RELEASE_ID=retail-release-tampered00000000000000000000000000000000000000|' "$HANDLE/release.env"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
  >"$ROOT/reverify-tampered-release-id.log" 2>&1
REVERIFY_TAMPERED_RC=$?
set -e
[[ "$REVERIFY_TAMPERED_RC" -ne 0 ]]
grep -Eq 'RELEASE_ID (must equal retail-release-SOURCE_SHA|does not match verified candidate)' \
  "$ROOT/reverify-tampered-release-id.log" \
  || { echo "reverify did not fail at D2 RELEASE_ID mismatch" >&2; exit 1; }
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$LIVE_HEAD_BEFORE_REVERIFY" ]] \
  || { echo "tampered reverify mutated live HEAD" >&2; exit 1; }
DIST_AFTER_REVERIFY="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
[[ "$DIST_BEFORE_REVERIFY" == "$DIST_AFTER_REVERIFY" ]] \
  || { echo "tampered reverify mutated live dist" >&2; exit 1; }
# Restore the handle so the manual rollback test below still works.
sed -i "s|^RELEASE_ID=.*|RELEASE_ID=$ORIGINAL_RELEASE_ID|" "$HANDLE/release.env"

# P2.2 regression: corrupting a D2 identity field on a deployed release.env
# must reject manual rollback BEFORE any mutation (stop_runtime, git reset,
# restore_runtime_venv, restore_dist, restore_runtime_assets). The validator
# runs at the start of rollback_from_backup and captures D2 values used by
# the final write_release_manifest (no TOCTOU re-read).
LIVE_HEAD_BEFORE_ROLLBACK="$(git -C "$LIVE" rev-parse HEAD)"
DIST_BEFORE_ROLLBACK="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
BACKEND_MAIN_BEFORE_ROLLBACK="$(sha256sum "$LIVE/backend/main.py" | awk '{print $1}')"
SYSTEMD_BEFORE_ROLLBACK="$(sha256sum "$ROOT/etc/systemd/system/unihub-backend.service" 2>/dev/null | awk '{print $1}')"
ORIGINAL_ROLLBACK_SHA="$(sed -n 's/^ROLLBACK_SHA=//p' "$HANDLE/release.env" | head -n1)"
sed -i 's|^ROLLBACK_SHA=.*|ROLLBACK_SHA=tampered00000000000000000000000000000000000000|' "$HANDLE/release.env"
set +e
run_deploy rollback "$HANDLE" >"$ROOT/rollback-tampered-d2.log" 2>&1
ROLLBACK_TAMPERED_RC=$?
set -e
[[ "$ROLLBACK_TAMPERED_RC" -ne 0 ]]
grep -Eq '(ROLLBACK_(RELEASE_ID must equal retail-release-ROLLBACK_SHA|SHA must equal OLD_SHA)|source SHA must be exactly 40 lowercase hex characters)' \
  "$ROOT/rollback-tampered-d2.log" \
  || { echo "tampered rollback did not fail at D2 ROLLBACK_SHA invariant" >&2; exit 1; }
if grep -q 'TEST systemctl stop ' "$ROOT/rollback-tampered-d2.log"; then
  echo "tampered rollback mutated runtime before D2 preflight validation" >&2
  exit 1
fi
if grep -q 'HEAD is now at' "$ROOT/rollback-tampered-d2.log"; then
  echo "tampered rollback advanced git before D2 preflight validation" >&2
  exit 1
fi
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$LIVE_HEAD_BEFORE_ROLLBACK" ]] \
  || { echo "tampered rollback mutated live HEAD" >&2; exit 1; }
DIST_AFTER_ROLLBACK="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
[[ "$DIST_BEFORE_ROLLBACK" == "$DIST_AFTER_ROLLBACK" ]] \
  || { echo "tampered rollback mutated live dist" >&2; exit 1; }
BACKEND_MAIN_AFTER_ROLLBACK="$(sha256sum "$LIVE/backend/main.py" | awk '{print $1}')"
[[ "$BACKEND_MAIN_BEFORE_ROLLBACK" == "$BACKEND_MAIN_AFTER_ROLLBACK" ]] \
  || { echo "tampered rollback mutated backend main.py" >&2; exit 1; }
SYSTEMD_AFTER_ROLLBACK="$(sha256sum "$ROOT/etc/systemd/system/unihub-backend.service" 2>/dev/null | awk '{print $1}')"
[[ "$SYSTEMD_BEFORE_ROLLBACK" == "$SYSTEMD_AFTER_ROLLBACK" ]] \
  || { echo "tampered rollback mutated systemd unit" >&2; exit 1; }
grep -q '^STATE=deployed$' "$HANDLE/release.env" \
  || { echo "tampered rollback flipped STATE away from deployed" >&2; exit 1; }
# Restore so the existing legitimate HANDLE rollback below still works.
sed -i "s|^ROLLBACK_SHA=.*|ROLLBACK_SHA=$ORIGINAL_ROLLBACK_SHA|" "$HANDLE/release.env"

# Test A: deleting PROMOTION_SCHEMA_VERSION from an otherwise-D2 handle
# MUST NOT silently downgrade the validator to legacy mode. The
# remaining D2-only fields (RELEASE_ID, SOURCE_SHA, MIGRATION_HEAD,
# ARTIFACT_SHA256, SBOM_SHA256, DEPLOYED_AT_UTC, PREDECESSOR_*,
# ROLLBACK_*) trip the schema-deletion guard.
ORIGINAL_SCHEMA_LINE="$(grep '^PROMOTION_SCHEMA_VERSION=' "$HANDLE/release.env" | head -n1)"
[[ -n "$ORIGINAL_SCHEMA_LINE" ]] \
  || { echo "PROMOTION_SCHEMA_VERSION missing from deployed D2 handle" >&2; exit 1; }
sed -i '/^PROMOTION_SCHEMA_VERSION=/d' "$HANDLE/release.env"
DIST_BEFORE_SCHEMA_REVERIFY="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
LIVE_HEAD_BEFORE_SCHEMA_REVERIFY="$(git -C "$LIVE" rev-parse HEAD)"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
  >"$ROOT/schema-delete-reverify.log" 2>&1
SCHEMA_DELETE_REVERIFY_RC=$?
set -e
[[ "$SCHEMA_DELETE_REVERIFY_RC" -ne 0 ]]
grep -Eq 'D2 fields present without PROMOTION_SCHEMA_VERSION' \
  "$ROOT/schema-delete-reverify.log" \
  || { echo "schema deletion reverify did not fail with D2-only field guard" >&2; exit 1; }
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$LIVE_HEAD_BEFORE_SCHEMA_REVERIFY" ]] \
  || { echo "schema deletion reverify mutated live HEAD" >&2; exit 1; }
DIST_AFTER_SCHEMA_REVERIFY="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
[[ "$DIST_BEFORE_SCHEMA_REVERIFY" == "$DIST_AFTER_SCHEMA_REVERIFY" ]] \
  || { echo "schema deletion reverify mutated live dist" >&2; exit 1; }
# Restore PROMOTION_SCHEMA_VERSION so subsequent tests still operate on
# a complete D2 handle.
printf '%s\n' "$ORIGINAL_SCHEMA_LINE" >>"$HANDLE/release.env"

# Test B: same schema-deletion corruption on manual rollback must fail
# at the rollback preflight, BEFORE stop_runtime / git reset / restore.
sed -i '/^PROMOTION_SCHEMA_VERSION=/d' "$HANDLE/release.env"
LIVE_HEAD_BEFORE_SCHEMA_ROLLBACK="$(git -C "$LIVE" rev-parse HEAD)"
DIST_BEFORE_SCHEMA_ROLLBACK="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
BACKEND_MAIN_BEFORE_SCHEMA_ROLLBACK="$(sha256sum "$LIVE/backend/main.py" | awk '{print $1}')"
set +e
run_deploy rollback "$HANDLE" >"$ROOT/schema-delete-rollback.log" 2>&1
SCHEMA_DELETE_ROLLBACK_RC=$?
set -e
[[ "$SCHEMA_DELETE_ROLLBACK_RC" -ne 0 ]]
grep -Eq 'D2 fields present without PROMOTION_SCHEMA_VERSION' \
  "$ROOT/schema-delete-rollback.log" \
  || { echo "schema deletion rollback did not fail with D2-only field guard" >&2; exit 1; }
if grep -q 'TEST systemctl stop ' "$ROOT/schema-delete-rollback.log"; then
  echo "schema deletion rollback mutated runtime before D2 preflight validation" >&2
  exit 1
fi
if grep -q 'HEAD is now at' "$ROOT/schema-delete-rollback.log"; then
  echo "schema deletion rollback advanced git before D2 preflight validation" >&2
  exit 1
fi
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$LIVE_HEAD_BEFORE_SCHEMA_ROLLBACK" ]] \
  || { echo "schema deletion rollback mutated live HEAD" >&2; exit 1; }
DIST_AFTER_SCHEMA_ROLLBACK="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
[[ "$DIST_BEFORE_SCHEMA_ROLLBACK" == "$DIST_AFTER_SCHEMA_ROLLBACK" ]] \
  || { echo "schema deletion rollback mutated live dist" >&2; exit 1; }
BACKEND_MAIN_AFTER_SCHEMA_ROLLBACK="$(sha256sum "$LIVE/backend/main.py" | awk '{print $1}')"
[[ "$BACKEND_MAIN_BEFORE_SCHEMA_ROLLBACK" == "$BACKEND_MAIN_AFTER_SCHEMA_ROLLBACK" ]] \
  || { echo "schema deletion rollback mutated backend main.py" >&2; exit 1; }
grep -q '^STATE=deployed$' "$HANDLE/release.env" \
  || { echo "schema deletion rollback flipped STATE away from deployed" >&2; exit 1; }
printf '%s\n' "$ORIGINAL_SCHEMA_LINE" >>"$HANDLE/release.env"

# Test C: a D2 STATE=deployed handle MUST have a canonical DEPLOYED_AT_UTC.
# Deleting it must fail same-SHA reverify AND manual rollback.
ORIGINAL_DEPLOYED_AT="$(grep '^DEPLOYED_AT_UTC=' "$HANDLE/release.env" | head -n1)"
[[ -n "$ORIGINAL_DEPLOYED_AT" ]] \
  || { echo "DEPLOYED_AT_UTC missing from deployed D2 handle" >&2; exit 1; }
sed -i '/^DEPLOYED_AT_UTC=/d' "$HANDLE/release.env"
set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" \
  >"$ROOT/missing-timestamp-reverify.log" 2>&1
MISSING_TIMESTAMP_REVERIFY_RC=$?
set -e
[[ "$MISSING_TIMESTAMP_REVERIFY_RC" -ne 0 ]]
grep -Eq 'DEPLOYED_AT_UTC is required when STATE=deployed' \
  "$ROOT/missing-timestamp-reverify.log" \
  || { echo "missing timestamp reverify did not fail with D2 timestamp invariant" >&2; exit 1; }
set +e
run_deploy rollback "$HANDLE" >"$ROOT/missing-timestamp-rollback.log" 2>&1
MISSING_TIMESTAMP_ROLLBACK_RC=$?
set -e
[[ "$MISSING_TIMESTAMP_ROLLBACK_RC" -ne 0 ]]
grep -Eq 'DEPLOYED_AT_UTC is required when STATE=deployed' \
  "$ROOT/missing-timestamp-rollback.log" \
  || { echo "missing timestamp rollback did not fail with D2 timestamp invariant" >&2; exit 1; }
if grep -q 'TEST systemctl stop ' "$ROOT/missing-timestamp-rollback.log"; then
  echo "missing timestamp rollback mutated runtime before D2 preflight validation" >&2
  exit 1
fi
grep -q '^STATE=deployed$' "$HANDLE/release.env" \
  || { echo "missing timestamp rollback flipped STATE away from deployed" >&2; exit 1; }
printf '%s\n' "$ORIGINAL_DEPLOYED_AT" >>"$HANDLE/release.env"

# Test D: SHA format must be enforced even when the internal identity
# relations are internally consistent. OLD_SHA / PREDECESSOR_SHA /
# ROLLBACK_SHA / PREDECESSOR_RELEASE_ID / ROLLBACK_RELEASE_ID are
# rewritten to a 40-character non-hex token and a matching
# retail-release-* ID. The relation checks would pass but the SHA
# format check must still reject.
INVALID_TOKEN="tampered0000000000000000000000000000000000"
INVALID_PREDECESSOR_ID="retail-release-${INVALID_TOKEN}"
ORIGINAL_OLD_SHA="$(sed -n 's/^OLD_SHA=//p' "$HANDLE/release.env" | head -n1)"
ORIGINAL_PREDECESSOR_SHA="$(sed -n 's/^PREDECESSOR_SHA=//p' "$HANDLE/release.env" | head -n1)"
ORIGINAL_ROLLBACK_SHA="$(sed -n 's/^ROLLBACK_SHA=//p' "$HANDLE/release.env" | head -n1)"
ORIGINAL_PREDECESSOR_RELEASE_ID="$(sed -n 's/^PREDECESSOR_RELEASE_ID=//p' "$HANDLE/release.env" | head -n1)"
ORIGINAL_ROLLBACK_RELEASE_ID="$(sed -n 's/^ROLLBACK_RELEASE_ID=//p' "$HANDLE/release.env" | head -n1)"
sed -i "s|^OLD_SHA=.*|OLD_SHA=$INVALID_TOKEN|" "$HANDLE/release.env"
sed -i "s|^PREDECESSOR_SHA=.*|PREDECESSOR_SHA=$INVALID_TOKEN|" "$HANDLE/release.env"
sed -i "s|^ROLLBACK_SHA=.*|ROLLBACK_SHA=$INVALID_TOKEN|" "$HANDLE/release.env"
sed -i "s|^PREDECESSOR_RELEASE_ID=.*|PREDECESSOR_RELEASE_ID=$INVALID_PREDECESSOR_ID|" "$HANDLE/release.env"
sed -i "s|^ROLLBACK_RELEASE_ID=.*|ROLLBACK_RELEASE_ID=$INVALID_PREDECESSOR_ID|" "$HANDLE/release.env"
LIVE_HEAD_BEFORE_INVALID_SHA="$(git -C "$LIVE" rev-parse HEAD)"
DIST_BEFORE_INVALID_SHA="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
set +e
run_deploy rollback "$HANDLE" >"$ROOT/invalid-sha-rollback.log" 2>&1
INVALID_SHA_ROLLBACK_RC=$?
set -e
[[ "$INVALID_SHA_ROLLBACK_RC" -ne 0 ]]
grep -Eq 'source SHA must be exactly 40 lowercase hex characters' \
  "$ROOT/invalid-sha-rollback.log" \
  || { echo "invalid SHA format rollback did not fail with SHA format check" >&2; exit 1; }
if grep -q 'TEST systemctl stop ' "$ROOT/invalid-sha-rollback.log"; then
  echo "invalid SHA format rollback mutated runtime before SHA format check" >&2
  exit 1
fi
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$LIVE_HEAD_BEFORE_INVALID_SHA" ]] \
  || { echo "invalid SHA format rollback mutated live HEAD" >&2; exit 1; }
DIST_AFTER_INVALID_SHA="$(find "$LIVE/dist" -type f -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}')"
[[ "$DIST_BEFORE_INVALID_SHA" == "$DIST_AFTER_INVALID_SHA" ]] \
  || { echo "invalid SHA format rollback mutated live dist" >&2; exit 1; }
grep -q '^STATE=deployed$' "$HANDLE/release.env" \
  || { echo "invalid SHA format rollback flipped STATE away from deployed" >&2; exit 1; }
sed -i "s|^OLD_SHA=.*|OLD_SHA=$ORIGINAL_OLD_SHA|" "$HANDLE/release.env"
sed -i "s|^PREDECESSOR_SHA=.*|PREDECESSOR_SHA=$ORIGINAL_PREDECESSOR_SHA|" "$HANDLE/release.env"
sed -i "s|^ROLLBACK_SHA=.*|ROLLBACK_SHA=$ORIGINAL_ROLLBACK_SHA|" "$HANDLE/release.env"
sed -i "s|^PREDECESSOR_RELEASE_ID=.*|PREDECESSOR_RELEASE_ID=$ORIGINAL_PREDECESSOR_RELEASE_ID|" "$HANDLE/release.env"
sed -i "s|^ROLLBACK_RELEASE_ID=.*|ROLLBACK_RELEASE_ID=$ORIGINAL_ROLLBACK_RELEASE_ID|" "$HANDLE/release.env"

run_deploy rollback "$HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(venv_identity_hash)" == "$OLD_VENV_HASH" ]]
[[ "$(stat -c '%a' "$LIVE/backend/main.py")" == "644" ]]
[[ "$(stat -c '%a' "$LIVE/dist/index.html")" == "640" ]]
[[ ! -L "$ROOT/etc/systemd/system/unihub-backend.service" ]]
grep -Fxq 'legacy unit unihub-backend.service' "$ROOT/etc/systemd/system/unihub-backend.service"
for unit in unihub-grile-worker.service unihub-export-worker.service \
  unihub-salary-export-worker.service unihub-legacy-worker.service; do
  [[ ! -e "$ROOT/etc/systemd/system/$unit" ]]
  [[ ! -e "$ROOT/enabled/$unit" ]]
done
[[ ! -e "$OPS/prometheus/unihub-retail-network.env" ]]
[[ ! -e "$OPS/prometheus/scrape.d/unihub-retail.yml" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ ! -e "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" ]]
[[ ! -e "$LIVE/docs/PLAN_DEZVOLTARE_RETAIL_UNIHUB_URMATOAREA_VERSIUNE_2026-07-15.md" ]]
grep -q '^STATE=rolled_back$' "$HANDLE/release.env"

# Pre-D2 manual rollback compatibility: a handle that lacks PROMOTION_SCHEMA_VERSION
# must still roll back successfully and must NOT have D2 fields retroactively added.
PRE_D2_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PRE_D2_NONCE="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
PRE_D2_HANDLE="$OPS/backups/retail-deploy/${PRE_D2_STAMP}-${OLD_SHA:0:12}-to-${OLD_SHA:0:12}-${PRE_D2_NONCE}"
mkdir -p "$PRE_D2_HANDLE"
git -C "$LIVE" archive --format=tar.gz "$OLD_SHA" >"$PRE_D2_HANDLE/source-${OLD_SHA}.tar.gz"
sha256sum "$PRE_D2_HANDLE/source-${OLD_SHA}.tar.gz" >"$PRE_D2_HANDLE/source.sha256"
cat >"$PRE_D2_HANDLE/release.env" <<EOF
OLD_SHA=$OLD_SHA
NEW_SHA=$OLD_SHA
STATE=deployed
UPDATED_AT=${PRE_D2_STAMP%?}Z
EOF
chmod 0600 "$PRE_D2_HANDLE/release.env"
cp -a "$LIVE/dist" "$PRE_D2_HANDLE/dist"
/usr/bin/python3.12 -I -S - "$LIVE/backend/venv" "$PRE_D2_HANDLE/venv-before.json" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
entries = []
for path in sorted(root.rglob("*")):
    relative = str(path.relative_to(root))
    if path.is_symlink():
        entries.append([relative, "symlink", path.readlink().as_posix()])
    elif path.is_file():
        entries.append([relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()])
digest = hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()
pathlib.Path(sys.argv[2]).write_text(
    json.dumps({"schemaVersion": 1, "legacyOpaque": True, "treeSha256": digest}, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
chmod 0600 "$PRE_D2_HANDLE/venv-before.json"
mkdir -p "$PRE_D2_HANDLE/runtime-assets/files"
{
  printf 'unihub-backend.service=1\n'
  printf 'unihub-worker.service=1\n'
  printf 'unihub-import-worker.service=1\n'
  printf 'unihub-grile-worker.service=0\n'
  printf 'unihub-export-worker.service=0\n'
  printf 'unihub-salary-export-worker.service=0\n'
  printf 'unihub-legacy-worker.service=0\n'
  printf 'unihub-retail-migrate.service=1\n'
  printf 'unihub-retail-network.env=0\n'
  printf 'unihub-retail.yml=0\n'
  printf 'retail-slo-rules.yml=0\n'
} >"$PRE_D2_HANDLE/runtime-assets/state.env"
chmod 0600 "$PRE_D2_HANDLE/runtime-assets/state.env"
for unit in unihub-backend.service unihub-worker.service \
  unihub-import-worker.service unihub-retail-migrate.service; do
  cp -a --no-dereference -- "$ROOT/etc/systemd/system/$unit" \
    "$PRE_D2_HANDLE/runtime-assets/files/$unit"
done
{
  printf 'unihub-backend.service=0\n'
  printf 'unihub-worker.service=0\n'
  printf 'unihub-import-worker.service=0\n'
  printf 'unihub-grile-worker.service=0\n'
  printf 'unihub-export-worker.service=0\n'
  printf 'unihub-salary-export-worker.service=0\n'
  printf 'unihub-legacy-worker.service=0\n'
  printf 'unihub-retail-migrate.service=0\n'
} >"$PRE_D2_HANDLE/runtime-assets/enabled.env"
chmod 0600 "$PRE_D2_HANDLE/runtime-assets/enabled.env"
{
  printf 'approval_id=pre-d2-legacy-test\n'
  printf 'approved_by_os=pre-d2-legacy-test\n'
  printf 'ci_run_id=0\n'
  printf 'source_sha=%s\n' "$OLD_SHA"
  printf 'artifact_sha256=%s\n' "$(printf 'a%.0s' {1..64})"
  printf 'claimed_at_epoch=0\n'
} >"$PRE_D2_HANDLE/approval.env"
chmod 0600 "$PRE_D2_HANDLE/approval.env"
run_deploy rollback "$PRE_D2_HANDLE"
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
grep -q '^STATE=rolled_back$' "$PRE_D2_HANDLE/release.env"
if grep -q '^PROMOTION_SCHEMA_VERSION=' "$PRE_D2_HANDLE/release.env"; then
  echo "pre-D2 manual rollback added D2 fields retroactively" >&2
  exit 1
fi
if grep -Eq '^(RELEASE_ID|SOURCE_SHA|MIGRATION_HEAD|ARTIFACT_SHA256|SBOM_SHA256|DEPLOYED_AT_UTC|PREDECESSOR_RELEASE_ID|PREDECESSOR_SHA|ROLLBACK_RELEASE_ID|ROLLBACK_SHA)=' \
  "$PRE_D2_HANDLE/release.env"; then
  echo "pre-D2 manual rollback wrote unexpected D2 identity fields" >&2
  exit 1
fi
grep -q "^OLD_SHA=$OLD_SHA$" "$PRE_D2_HANDLE/release.env"
grep -q "^NEW_SHA=$OLD_SHA$" "$PRE_D2_HANDLE/release.env"
rm -rf -- "$PRE_D2_HANDLE"

git --git-dir="$REMOTE" update-ref refs/heads/main "$NEW_SHA"

set +e
run_deploy "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
REUSE_RC=$?
set -e
[[ "$REUSE_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
FAILED_BEFORE_HEALTH="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=health \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
FAIL_RC=$?
set -e
[[ "$FAIL_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ ! -e "$LIVE/docs/AUDIT_TEHNIC_RETAIL_UNIHUB_REAUDIT_2026-07-15.md" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" \
  -eq "$((FAILED_BEFORE_HEALTH + 1))" ]]
[[ ! -e "$ROOT/node-exporter/textfile/unihub_retail_deploy.prom" ]]

for VENV_FAIL_PHASE in venv_after_old_move venv_after_swap; do
  approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
  FAILED_BEFORE_VENV="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
  set +e
  RETAIL_DEPLOY_TEST_MODE=1 \
  RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
  RETAIL_DEPLOY_TEST_FAIL_PHASE="$VENV_FAIL_PHASE" \
    /usr/bin/bash -p "$DEPLOY_SCRIPT" \
      "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
  VENV_FAIL_RC=$?
  set -e
  [[ "$VENV_FAIL_RC" -ne 0 ]]
  [[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
  [[ "$(venv_identity_hash)" == "$OLD_VENV_HASH" ]]
  [[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" \
    -eq "$((FAILED_BEFORE_VENV + 1))" ]]
done

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
FAILED_BEFORE_PROMETHEUS="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=prometheus \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
PROMETHEUS_RC=$?
set -e
[[ "$PROMETHEUS_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ ! -L "$ROOT/etc/systemd/system/unihub-backend.service" ]]
grep -Fxq 'legacy unit unihub-backend.service' "$ROOT/etc/systemd/system/unihub-backend.service"
[[ ! -e "$OPS/prometheus/unihub-retail-network.env" ]]
[[ ! -e "$OPS/prometheus/scrape.d/unihub-retail.yml" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$((FAILED_BEFORE_PROMETHEUS + 1))" ]]
[[ ! -e "$ROOT/node-exporter/textfile/unihub_retail_deploy.prom" ]]

approve_release "$CI_RUN_ID" "$NEW_SHA" "$ARTIFACT_SHA256" >/dev/null
FAILED_BEFORE_PUBLIC_HEALTH="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=public_health \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$CI_RUN_ID" "$ARTIFACT_SHA256" >/dev/null 2>&1
PUBLIC_HEALTH_RC=$?
set -e
[[ "$PUBLIC_HEALTH_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(<"$LIVE/dist/index.html")" == "old frontend" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$((FAILED_BEFORE_PUBLIC_HEALTH + 1))" ]]
[[ ! -e "$ROOT/node-exporter/textfile/unihub_retail_deploy.prom" ]]

mkdir -p "$ROOT/tampered"
tar -xzf "$ARTIFACT" -C "$ROOT/tampered"
printf 'tampered\n' >"$ROOT/tampered/backend/main.py"
tar -czf "$ROOT/tampered.tar.gz" -C "$ROOT/tampered" .
TAMPER_SHA256="$(sha256sum "$ROOT/tampered.tar.gz" | awk '{print $1}')"
approve_release "$CI_RUN_ID" "$NEW_SHA" "$TAMPER_SHA256" >/dev/null
FAILED_BEFORE_TAMPER="$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)"
set +e
run_deploy "$ROOT/tampered.tar.gz" "$NEW_SHA" "$CI_RUN_ID" "$TAMPER_SHA256" \
  >"$ROOT/tampered-release.log" 2>&1
TAMPER_RC=$?
set -e
[[ "$TAMPER_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$OLD_SHA" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.failed' | wc -l)" -eq "$FAILED_BEFORE_TAMPER" ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f \
  -name "${CI_RUN_ID}-${NEW_SHA}-${TAMPER_SHA256}-*.approved" | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name '*.claimed.*' | wc -l)" -eq 0 ]]
if grep -q 'claimed approval record is missing' "$ROOT/tampered-release.log"; then
  exit 1
fi

/usr/bin/python3.12 -I -S - "$ROOT/unsafe.tar.gz" <<'PY'
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

/usr/bin/python3.12 -I -S - "$ROOT/symlink.tar.gz" <<'PY'
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
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$ARTIFACT" "$NEW_SHA" "$((CI_RUN_ID + 2))" "$ARTIFACT_SHA256" >/dev/null 2>&1
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
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$MIGRATED_ARTIFACT" "$MIGRATED_SHA" "$MIGRATED_RUN_ID" "$MIGRATED_ARTIFACT_SHA256" \
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
set +e
RETAIL_DEPLOY_TEST_MODE=1 \
RETAIL_DEPLOY_TEST_ROOT="$ROOT" \
RETAIL_DEPLOY_TEST_FAIL_PHASE=source_permissions \
  /usr/bin/bash -p "$DEPLOY_SCRIPT" "$MIGRATED_ARTIFACT" "$MIGRATED_SHA" "$MIGRATED_RUN_ID" "$MIGRATED_ARTIFACT_SHA256" \
  >"$ROOT/migrated-recovery-failure.log" 2>&1
MIGRATED_RECOVERY_RC=$?
set -e
[[ "$MIGRATED_RECOVERY_RC" -ne 0 ]]
[[ "$(git -C "$LIVE" rev-parse HEAD)" == "$MIGRATED_SHA" ]]
grep -q '^STATE=recovery_required$' "$MIGRATED_HANDLE/release.env"
[[ "$(find "$MIGRATED_HANDLE" -maxdepth 1 -type f -name 'approval.failed.*.env' | wc -l)" -eq 1 ]]
[[ "$(find "$ROOT/approval-store" -maxdepth 1 -type f -name "${MIGRATED_RUN_ID}-${MIGRATED_SHA}-${MIGRATED_ARTIFACT_SHA256}-*.failed" | wc -l)" -eq 2 ]]
grep -q 'TEST tracked source permission failure' "$ROOT/migrated-recovery-failure.log"
grep -q 'forward recovery runtime remains stopped after an incomplete transition' "$ROOT/migrated-recovery-failure.log"
[[ "$(grep -c 'TEST systemctl stop ' "$ROOT/migrated-recovery-failure.log")" -eq 2 ]]
if grep -q 'TEST systemctl restart ' "$ROOT/migrated-recovery-failure.log"; then
  exit 1
fi
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
