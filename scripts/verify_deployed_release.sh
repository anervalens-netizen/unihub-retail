#!/usr/bin/env bash
# Read-only Release-B production acceptance authority (AC-17).
set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SELF_TEST=0
MAIN_A_SHA=""
MAIN_B_SHA=""
A_ARTIFACT_DIR=""
B_ARTIFACT_DIR=""
A_EVIDENCE=""
B_ARCHIVE_SHA256=""
BACKUP_HANDLE=""
PROBE_MONTH=""
MANAGER_COOKIE_FILE=""
FORBIDDEN_COOKIE_FILE=""
RELEASE_A_PR=""
RELEASE_B_PR=""
OBSERVE_SECONDS=120
EVIDENCE=""

COSIGN_SHA256="4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
PUBLIC_BASE="https://retail.unihub.ro"
LOCAL_BASE="http://127.0.0.1:9898"
PROMETHEUS_BASE="http://127.0.0.1:9090"
LIVE_ROOT="/opt/Mobiup/unihub-retail"
RUNTIME_RELEASE_BASE="/var/lib/unihub-retail-deploy/runtime-releases"
BACKUP_ROOT="/opt/Mobiup/ops/backups/retail-deploy"
BACKUP_STATUS="/opt/Mobiup/ops/backups/manifests/last-run.env"
MIGRATION_ENV="$LIVE_ROOT/.env.migrations"
GITHUB_REPOSITORY="anervalens-netizen/unihub-retail"
TASK_A_BRANCH="codex/retail-definitive-closure-20260812"
TASK_B_BRANCH="codex/retail-definitive-closure-b-20260813"
EXPECTED_UNITS=(
  unihub-backend.service
  unihub-worker.service
  unihub-import-worker.service
  unihub-grile-worker.service
  unihub-export-worker.service
  unihub-salary-export-worker.service
)
artifact_unit_path() {
  case "$1" in
    unihub-worker.service) printf '%s\n' "unihub-worker.service" ;;
    *) printf '%s\n' "ops/systemd/$1" ;;
  esac
}

die() { printf '%s: %s\n' "$PROGRAM" "$*" >&2; exit 1; }
usage() {
  printf '%s\n' "usage: $PROGRAM --main-a-sha SHA --main-b-sha SHA" \
    "  --release-a-artifact-dir DIR --release-b-artifact-dir DIR" \
    "  --release-a-evidence FILE --release-b-archive-sha256 SHA256" \
    "  --backup-handle DIR --probe-month YYYY-MM" \
    "  --manager-cookie-file FILE --forbidden-cookie-file FILE" \
    "  --release-a-pr 151 --release-b-pr NUMBER" \
    "  --observe-seconds 120 --evidence NEW_DIR" \
    "       $PROGRAM --self-test"
}

is_sha() { [[ "$1" =~ ^[0-9a-f]{40}$ ]]; }
is_sha256() { [[ "$1" =~ ^[0-9a-f]{64}$ ]]; }
require_regular() {
  [[ -f "$1" && ! -L "$1" ]] || die "required regular file is missing or a symlink: $1"
}
require_directory() {
  [[ -d "$1" && ! -L "$1" ]] || die "required directory is missing or a symlink: $1"
}
sha256_file() { sha256sum -- "$1" | awk '{print $1}'; }

while (($#)); do
  case "$1" in
    --self-test) SELF_TEST=1; shift ;;
    --main-a-sha) (($# >= 2)) || die "missing --main-a-sha value"; MAIN_A_SHA="$2"; shift 2 ;;
    --main-b-sha|--expected-sha) (($# >= 2)) || die "missing --main-b-sha value"; MAIN_B_SHA="$2"; shift 2 ;;
    --release-a-artifact-dir|--verify-rollback-artifact) (($# >= 2)) || die "missing Release-A artifact value"; A_ARTIFACT_DIR="$2"; shift 2 ;;
    --release-b-artifact-dir) (($# >= 2)) || die "missing Release-B artifact value"; B_ARTIFACT_DIR="$2"; shift 2 ;;
    --release-a-evidence) (($# >= 2)) || die "missing Release-A evidence value"; A_EVIDENCE="$2"; shift 2 ;;
    --release-b-archive-sha256) (($# >= 2)) || die "missing Release-B digest"; B_ARCHIVE_SHA256="$2"; shift 2 ;;
    --backup-handle) (($# >= 2)) || die "missing backup handle"; BACKUP_HANDLE="$2"; shift 2 ;;
    --probe-month) (($# >= 2)) || die "missing probe month"; PROBE_MONTH="$2"; shift 2 ;;
    --manager-cookie-file) (($# >= 2)) || die "missing manager cookie file"; MANAGER_COOKIE_FILE="$2"; shift 2 ;;
    --forbidden-cookie-file) (($# >= 2)) || die "missing forbidden cookie file"; FORBIDDEN_COOKIE_FILE="$2"; shift 2 ;;
    --release-a-pr) (($# >= 2)) || die "missing Release-A PR"; RELEASE_A_PR="$2"; shift 2 ;;
    --release-b-pr) (($# >= 2)) || die "missing Release-B PR"; RELEASE_B_PR="$2"; shift 2 ;;
    --observe-seconds) (($# >= 2)) || die "missing observation duration"; OBSERVE_SECONDS="$2"; shift 2 ;;
    --evidence) (($# >= 2)) || die "missing evidence path"; EVIDENCE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

self_test() {
  local source tmp fake_pass
  source="$(<"$SCRIPT_PATH")"
  [[ "$source" == *'--request GET'* ]] || die "self-test: HTTP GET fence is missing"
  [[ "$source" == *'unexpected non-read-only probe path'* ]] || die "self-test: route allowlist is missing"
  [[ "$source" == *'"salary_export_executed":False'* ]] || die "self-test: salary export fence evidence is missing"
  [[ "$source" != *'--request '"POST"* && "$source" != *'--request '"PUT"* \
    && "$source" != *'--request '"PATCH"* && "$source" != *'--request '"DELETE"* ]] \
    || die "self-test: mutating HTTP method found"
  [[ "$source" == *'TASK_A_BRANCH="codex/retail-definitive-closure-20260812"'* \
    && "$source" == *'TASK_B_BRANCH="codex/retail-definitive-closure-b-20260813"'* ]] \
    || die "self-test: exact task branches are not frozen"
  tmp="$(mktemp -d)"
  trap 'rm -rf -- "$tmp"' RETURN
  fake_pass="$tmp/manual-pass.json"
  printf '{"result":"PASS"}\n' >"$fake_pass"
  if AC17_SELF_TEST_CHILD=1 "$SCRIPT_PATH" \
      --main-a-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
      --main-b-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
      --release-a-artifact-dir "$fake_pass" \
      --release-b-artifact-dir "$fake_pass" \
      --release-a-evidence "$fake_pass" \
      --release-b-archive-sha256 cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
      --backup-handle "$tmp/missing-backup" --probe-month 2026-08 \
      --manager-cookie-file "$fake_pass" --forbidden-cookie-file "$fake_pass" \
      --release-a-pr 151 --release-b-pr 152 \
      --observe-seconds 120 --evidence "$tmp/new-evidence" >/dev/null 2>&1; then
    die "self-test: a manual PASS file was accepted as an artifact"
  fi
  mkdir "$tmp/stale-evidence"
  if AC17_SELF_TEST_CHILD=1 "$SCRIPT_PATH" \
      --main-a-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
      --main-b-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
      --release-a-artifact-dir "$tmp/a" --release-b-artifact-dir "$tmp/b" \
      --release-a-evidence "$fake_pass" \
      --release-b-archive-sha256 cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc \
      --backup-handle "$tmp/backup" --probe-month 2026-08 \
      --manager-cookie-file "$fake_pass" --forbidden-cookie-file "$fake_pass" \
      --release-a-pr 151 --release-b-pr 152 \
      --observe-seconds 120 --evidence "$tmp/stale-evidence" >/dev/null 2>&1; then
    die "self-test: stale evidence was accepted"
  fi
  printf 'AC-17 verifier self-test PASS: fake PASS and stale evidence rejected before probes\n'
}

if [[ "$SELF_TEST" == "1" ]]; then
  [[ -z "$MAIN_A_SHA$MAIN_B_SHA$A_ARTIFACT_DIR$B_ARTIFACT_DIR$EVIDENCE" ]] \
    || die "--self-test cannot be combined with production arguments"
  self_test
  exit 0
fi

[[ -z "${AC17_SELF_TEST_CHILD:-}" ]] || {
  # Child rejection tests must never progress past pure argument/path validation.
  if ! is_sha "$MAIN_A_SHA" || ! is_sha "$MAIN_B_SHA" \
    || [[ "$MAIN_A_SHA" == "$MAIN_B_SHA" ]]; then
    die "invalid self-test SHA pair"
  fi
  [[ ! -e "$EVIDENCE" && ! -L "$EVIDENCE" ]] || die "evidence path already exists"
  require_directory "$A_ARTIFACT_DIR"
  die "self-test child unexpectedly passed its fake input boundary"
}

is_sha "$MAIN_A_SHA" || die "--main-a-sha must be 40 lowercase hex"
is_sha "$MAIN_B_SHA" || die "--main-b-sha must be 40 lowercase hex"
[[ "$MAIN_A_SHA" != "$MAIN_B_SHA" ]] || die "Release A and B SHA must differ"
is_sha256 "$B_ARCHIVE_SHA256" || die "Release-B archive digest must be 64 lowercase hex"
[[ "$PROBE_MONTH" =~ ^20[0-9]{2}-(0[1-9]|1[0-2])$ ]] || die "probe month must be YYYY-MM"
[[ "$RELEASE_A_PR" == "151" ]] || die "Release-A PR must be exact task PR 151"
[[ "$RELEASE_B_PR" =~ ^[1-9][0-9]*$ && "$RELEASE_B_PR" != "$RELEASE_A_PR" ]] \
  || die "Release-B PR must be a distinct positive number"
[[ "$OBSERVE_SECONDS" == "120" ]] || die "AC-17 observation must be exactly 120 seconds"
[[ -n "$EVIDENCE" && "$EVIDENCE" == /* ]] || die "evidence must be a new absolute directory"
[[ ! -e "$EVIDENCE" && ! -L "$EVIDENCE" ]] || die "evidence path already exists"
require_directory "$A_ARTIFACT_DIR"
require_directory "$B_ARTIFACT_DIR"
require_regular "$A_EVIDENCE"
require_directory "$BACKUP_HANDLE"
require_regular "$MANAGER_COOKIE_FILE"
require_regular "$FORBIDDEN_COOKIE_FILE"
[[ "$EUID" -eq 0 ]] || die "production verification requires sudo/root for protected read-only evidence"
[[ "$(hostname)" == "server" ]] || die "AC-17 production verifier must run on primary host server"
[[ "$SCRIPT_PATH" == "$LIVE_ROOT/scripts/verify_deployed_release.sh" ]] \
  || die "AC-17 must run from the deployed primary checkout"

for command in git gh ssh sudo python3 sha256sum cosign curl systemctl journalctl tar diff awk sed stat; do
  command -v "$command" >/dev/null || die "required verifier utility missing: $command"
done
COSIGN_BIN="$(command -v cosign)"
[[ "$(sha256_file "$COSIGN_BIN")" == "$COSIGN_SHA256" ]] \
  || die "cosign is not the frozen v3.1.3 linux-amd64 binary"
"$COSIGN_BIN" version 2>&1 | grep -Eq 'GitVersion:[[:space:]]*v3\.1\.3([[:space:]]|$)' \
  || die "cosign version output is not v3.1.3"

for cookie_file in "$MANAGER_COOKIE_FILE" "$FORBIDDEN_COOKIE_FILE"; do
  mode="$(stat -c '%a' "$cookie_file")"
  ((10#$mode <= 600)) || die "cookie file permissions must be 0600 or stricter"
  [[ -s "$cookie_file" ]] || die "cookie file is empty"
done

[[ "$(git -C "$LIVE_ROOT" rev-parse HEAD)" == "$MAIN_B_SHA" ]] || die "live checkout is not MAIN_B_SHA"
[[ "$(git -C "$LIVE_ROOT" branch --show-current)" == "main" ]] || die "live checkout is not branch main"
[[ -z "$(git -C "$LIVE_ROOT" status --porcelain=v1 --untracked-files=all)" ]] || die "live checkout is dirty"
[[ "$(git -C "$LIVE_ROOT" rev-parse origin/main)" == "$MAIN_B_SHA" ]] || die "local origin/main is not MAIN_B_SHA"
git -C "$LIVE_ROOT" merge-base --is-ancestor "$MAIN_A_SHA" "$MAIN_B_SHA" \
  || die "MAIN_A_SHA is not an ancestor of MAIN_B_SHA"
[[ "$(git -C "$LIVE_ROOT" rev-parse "$MAIN_B_SHA:scripts/verify_deployed_release.sh")" \
   == "$(git -C "$LIVE_ROOT" hash-object "$SCRIPT_PATH")" ]] \
  || die "running verifier differs from MAIN_B_SHA"

mkdir -p "$(dirname "$EVIDENCE")"
WORK="$(mktemp -d "$(dirname "$EVIDENCE")/.ac17.XXXXXX")"
trap 'rm -rf -- "$WORK"' EXIT
mkdir "$WORK/fragments" "$WORK/raw" "$WORK/artifacts"
PYTHON="$LIVE_ROOT/backend/venv/bin/python"
[[ -x "$PYTHON" ]] || die "deployed backend Python is unavailable"

verify_b_artifact() {
  local dir="$1" expected_sha="$2" expected_archive_sha="$3" output="$4"
  "$PYTHON" - "$dir" "$expected_sha" "$expected_archive_sha" "$output" <<'PY'
import hashlib, json, pathlib, re, sys, tarfile
d = pathlib.Path(sys.argv[1]).resolve(); sha, expected_archive, out = sys.argv[2:]
archive_name = f"retail-release-{sha}.tar.gz"
checksummed = {"SOURCE_SHA", archive_name, "SBOM.cdx.json", "SBOM.npm.cdx.json", "SBOM.python.cdx.json", "PROVENANCE.json", "RELEASE_MANIFEST.json"}
required = checksummed | {"SHA256SUMS", "RELEASE_MANIFEST.sigstore.json"}
actual = {p.name for p in d.iterdir() if p.is_file() and not p.is_symlink()}
if not required <= actual or any((d / n).is_symlink() for n in required): raise SystemExit("artifact inventory incomplete or unsafe")
if (d / "SOURCE_SHA").read_text().strip() != sha: raise SystemExit("SOURCE_SHA mismatch")
entries = {}
for line in (d / "SHA256SUMS").read_text().splitlines():
    parts=line.split()
    if len(parts)!=2 or not re.fullmatch(r"[0-9a-f]{64}",parts[0]): raise SystemExit("invalid SHA256SUMS")
    name=parts[1].lstrip("*")
    if pathlib.Path(name).name != name or name in entries: raise SystemExit("unsafe checksum path")
    entries[name]=parts[0]
if set(entries)!=checksummed: raise SystemExit("checksum inventory mismatch")
for name,digest in entries.items():
    if hashlib.sha256((d/name).read_bytes()).hexdigest()!=digest: raise SystemExit(f"checksum mismatch: {name}")
if entries[archive_name] != expected_archive: raise SystemExit("Release-B archive digest mismatch")
m=json.loads((d/"RELEASE_MANIFEST.json").read_text())
if m.get("schemaVersion")!=1 or m.get("sourceSha")!=sha or m.get("archive")!=archive_name: raise SystemExit("release manifest identity mismatch")
if m.get("sha256") != {n: entries[n] for n in checksummed if n!="RELEASE_MANIFEST.json"}: raise SystemExit("release manifest digests mismatch")
p=json.loads((d/"PROVENANCE.json").read_text()); subjects=p.get("subject")
if p.get("_type")!="https://in-toto.io/Statement/v1" or p.get("predicateType")!="https://slsa.dev/provenance/v1": raise SystemExit("provenance type mismatch")
if not isinstance(subjects,list) or len(subjects)!=1 or subjects[0].get("name")!=archive_name or subjects[0].get("digest",{}).get("sha256")!=expected_archive: raise SystemExit("provenance subject mismatch")
resolved=p.get("predicate",{}).get("buildDefinition",{}).get("resolvedDependencies",[])
if not any(x.get("digest",{}).get("gitCommit")==sha for x in resolved if isinstance(x,dict)): raise SystemExit("provenance source mismatch")
with tarfile.open(d/archive_name,"r:gz") as tf:
    for member in tf.getmembers():
        q=pathlib.PurePosixPath(member.name)
        if q.is_absolute() or ".." in q.parts or member.issym() or member.islnk(): raise SystemExit("unsafe archive member")
payload={"schema_version":1,"result":"PASS","source_sha":sha,"archive":archive_name,"archive_sha256":expected_archive,"release_manifest_sha256":hashlib.sha256((d/"RELEASE_MANIFEST.json").read_bytes()).hexdigest(),"provenance_sha256":hashlib.sha256((d/"PROVENANCE.json").read_bytes()).hexdigest(),"sigstore_bundle_sha256":hashlib.sha256((d/"RELEASE_MANIFEST.sigstore.json").read_bytes()).hexdigest(),"inventory":entries}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY
  "$PYTHON" "$LIVE_ROOT/scripts/validate_release_sbom.py" npm "$dir/SBOM.npm.cdx.json" >/dev/null
  "$PYTHON" "$LIVE_ROOT/scripts/validate_release_sbom.py" pypi "$dir/SBOM.python.cdx.json" >/dev/null
  "$PYTHON" "$LIVE_ROOT/scripts/validate_release_sbom.py" aggregate "$dir/SBOM.cdx.json" --expected-sha "$expected_sha" >/dev/null
  "$COSIGN_BIN" verify-blob "$dir/RELEASE_MANIFEST.json" \
    --bundle "$dir/RELEASE_MANIFEST.sigstore.json" \
    --certificate-identity "https://github.com/anervalens-netizen/unihub-retail/.github/workflows/ci.yml@refs/heads/main" \
    --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
    >"$WORK/raw/release-b-cosign.log" 2>&1
}

verify_b_artifact "$B_ARTIFACT_DIR" "$MAIN_B_SHA" "$B_ARCHIVE_SHA256" \
  "$WORK/fragments/release-b-artifact.json"

COSIGN_BIN="$COSIGN_BIN" PYTHONPATH="$LIVE_ROOT/backend" "$PYTHON" \
  "$LIVE_ROOT/scripts/check_release_a_candidate.py" \
  --verify-main-evidence "$A_EVIDENCE" --expected-sha "$MAIN_A_SHA" \
  --expected-candidate-sha "$MAIN_B_SHA" --release-a-artifact-dir "$A_ARTIFACT_DIR" \
  --evidence "$WORK/fragments/release-a-verification.json" \
  >"$WORK/raw/release-a-verification.log" 2>&1
"$PYTHON" - "$WORK/fragments/release-a-verification.json" "$MAIN_A_SHA" <<'PY'
import json,pathlib,sys
p=json.loads(pathlib.Path(sys.argv[1]).read_text())
if p.get("result")!="PASS" or p.get("expected_release_a_sha")!=sys.argv[2]: raise SystemExit("Release-A checker did not authorize exact SHA")
PY

B_ARCHIVE="$B_ARTIFACT_DIR/retail-release-$MAIN_B_SHA.tar.gz"
A_ARCHIVE="$A_ARTIFACT_DIR/retail-release-$MAIN_A_SHA.tar.gz"
require_regular "$B_ARCHIVE"
require_regular "$A_ARCHIVE"
mkdir "$WORK/artifacts/a" "$WORK/artifacts/b"
tar -xzf "$A_ARCHIVE" -C "$WORK/artifacts/a"
tar -xzf "$B_ARCHIVE" -C "$WORK/artifacts/b"
cmp -s "$WORK/artifacts/a/backend/db/migrations/manifest.json" \
  "$WORK/artifacts/b/backend/db/migrations/manifest.json" \
  || die "rollback artifact A does not carry the additive schema-069 manifest"

RUNTIME_RELEASE="$RUNTIME_RELEASE_BASE/$MAIN_B_SHA"
require_directory "$RUNTIME_RELEASE"
diff -qr -- "$WORK/artifacts/b/dist" "$LIVE_ROOT/dist" >"$WORK/raw/frontend-diff.log" \
  || die "live frontend differs from signed Release-B artifact"
for unit in "${EXPECTED_UNITS[@]}"; do
  artifact_unit="$(artifact_unit_path "$unit")"
  require_regular "$RUNTIME_RELEASE/systemd/$unit"
  [[ -L "/etc/systemd/system/$unit" ]] || die "systemd unit is not an immutable runtime symlink: $unit"
  [[ "$(readlink -f "/etc/systemd/system/$unit")" == "$RUNTIME_RELEASE/systemd/$unit" ]] \
    || die "systemd unit is not bound to MAIN_B_SHA: $unit"
  cmp -s "$WORK/artifacts/b/$artifact_unit" "$RUNTIME_RELEASE/systemd/$unit" \
    || die "runtime unit differs from signed Release-B artifact: $unit"
done
cmp -s "$WORK/artifacts/b/ops/observability/retail-slo-rules.yml" \
  "$RUNTIME_RELEASE/retail-slo-rules.yml" || die "runtime Prometheus rules differ from artifact"
cmp -s "$RUNTIME_RELEASE/retail-slo-rules.yml" \
  /opt/Mobiup/infra/observability/prometheus/rules/retail-slo-rules.yml \
  || die "active Prometheus rules differ from MAIN_B_SHA"

"$PYTHON" - "$BACKUP_HANDLE" "$BACKUP_ROOT" "$MAIN_A_SHA" "$MAIN_B_SHA" \
  "$B_ARCHIVE_SHA256" "$BACKUP_STATUS" "$WORK/fragments/backup.json" <<'PY'
import datetime,hashlib,json,pathlib,re,sys
h=pathlib.Path(sys.argv[1]).resolve(); root=pathlib.Path(sys.argv[2]).resolve()
a,b,digest,status_path,out=sys.argv[3:]
if h.parent!=root or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-to-[0-9a-f]{12}-[0-9a-f]{16}",h.name): raise SystemExit("backup handle identity invalid")
def env(path):
    result={}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            k,sep,v=line.partition("=")
            if not sep or k in result: raise SystemExit(f"invalid evidence env: {path.name}")
            result[k]=v
    return result
r=env(h/"release.env"); approval=env(h/"approval.env"); backup=env(pathlib.Path(status_path))
if r.get("OLD_SHA")!=a or r.get("NEW_SHA")!=b or r.get("STATE")!="deployed": raise SystemExit("deploy release manifest mismatch")
if approval.get("source_sha")!=b or approval.get("artifact_sha256")!=digest or not approval.get("ci_run_id","").isdigit(): raise SystemExit("approval binding mismatch")
if backup.get("status")!="success" or backup.get("checksum_ok")!="1" or int(backup.get("file_count","0"))<9: raise SystemExit("verified backup status mismatch")
handle_epoch=int(datetime.datetime.strptime(h.name[:16],"%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())
deployed_epoch=int(datetime.datetime.fromisoformat(r["UPDATED_AT"].replace("Z","+00:00")).timestamp())
backup_started=int(backup.get("started_at","0")); backup_completed=int(backup.get("completed_at","0")); claimed=int(approval.get("claimed_at_epoch","0"))
if not handle_epoch <= backup_started <= backup_completed <= deployed_epoch: raise SystemExit("backup timestamps are not bound to this deploy handle")
if not handle_epoch <= claimed <= deployed_epoch: raise SystemExit("approval claim timestamp is not bound to this deploy handle")
source_hash=h/"source.sha256"; source_archive=h/f"source-{a}.tar.gz"
if not source_hash.is_file() or not source_archive.is_file(): raise SystemExit("rollback source backup missing")
parts=source_hash.read_text().split()
if len(parts)!=2 or pathlib.Path(parts[1]).name!=source_archive.name or hashlib.sha256(source_archive.read_bytes()).hexdigest()!=parts[0]: raise SystemExit("rollback source checksum mismatch")
payload={"schema_version":1,"result":"PASS","handle":str(h),"release_env_sha256":hashlib.sha256((h/"release.env").read_bytes()).hexdigest(),"approval_env_sha256":hashlib.sha256((h/"approval.env").read_bytes()).hexdigest(),"old_sha":a,"new_sha":b,"deployed_at":r["UPDATED_AT"],"ci_run_id":approval["ci_run_id"],"approval_claimed_at_epoch":claimed,"artifact_sha256":digest,"backup_stamp":backup.get("stamp"),"backup_started_at":backup_started,"backup_completed_at":backup_completed,"backup_file_count":int(backup["file_count"]),"rollback_source_sha256":parts[0]}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY

"$PYTHON" - "$MIGRATION_ENV" "$LIVE_ROOT/backend/db/migrations/manifest.json" \
  "$WORK/fragments/schema-outbox.json" <<'PY'
import asyncio,json,os,pathlib,sys
import asyncpg
def env(path):
    result={}
    for raw in pathlib.Path(path).read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("export "): line=line[7:]
        k,sep,v=line.partition("=")
        if sep: result[k]=v.strip().strip('"').strip("'")
    return result
async def main():
    cfg=env(sys.argv[1]); dsn=cfg.get("MIGRATION_DATABASE_URL")
    if not dsn: raise SystemExit("MIGRATION_DATABASE_URL unavailable")
    expected=json.loads(pathlib.Path(sys.argv[2]).read_text())["migrations"]
    conn=await asyncpg.connect(dsn)
    try:
        async with conn.transaction(readonly=True):
            rows=await conn.fetch("SELECT filename, checksum FROM schema_migrations ORDER BY filename")
            actual={r["filename"]:r["checksum"] for r in rows}
            if actual!=expected or "069_ai_cohort_and_transactional_outbox.sql" not in actual: raise SystemExit("production migration ledger mismatch")
            states={r["state"]:int(r["n"]) for r in await conn.fetch("SELECT state,count(*) n FROM retail_outbox_events GROUP BY state")}
            dead=states.get("dead",0)
            stale=int(await conn.fetchval("SELECT count(*) FROM retail_outbox_events WHERE state='processing' AND lease_until < now()") or 0)
            pending_age=float(await conn.fetchval("SELECT COALESCE(EXTRACT(EPOCH FROM now()-min(created_at)),0) FROM retail_outbox_events WHERE state='pending'") or 0)
            receipts=int(await conn.fetchval("SELECT count(*) FROM retail_outbox_consumer_receipts") or 0)
            if dead or stale or pending_age>=60: raise SystemExit("production outbox health contract failed")
            types={r["event_type"]:int(r["n"]) for r in await conn.fetch("SELECT event_type,count(*) n FROM retail_outbox_events GROUP BY event_type ORDER BY event_type")}
    finally: await conn.close()
    pathlib.Path(sys.argv[3]).write_text(json.dumps({"schema_version":1,"result":"PASS","migration_count":len(actual),"last_migration":"069_ai_cohort_and_transactional_outbox.sql","migration_manifest":actual,"outbox_states":states,"outbox_event_types":types,"outbox_receipts":receipts,"oldest_pending_seconds":pending_age,"stale_processing":stale},sort_keys=True,separators=(",",":"))+"\n")
asyncio.run(main())
PY

service_snapshot() {
  local output="$1" unit
  : >"$output"
  for unit in "${EXPECTED_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" || die "service inactive: $unit"
    systemctl is-enabled --quiet "$unit" || die "service disabled: $unit"
    [[ "$(systemctl show "$unit" --property=NRestarts --value)" == "0" ]] \
      || die "service has restarted since activation: $unit"
    [[ "$(systemctl show "$unit" --property=ActiveEnterTimestampMonotonic --value)" =~ ^[1-9][0-9]*$ ]] \
      || die "service activation timestamp is unavailable: $unit"
    systemctl show "$unit" --property=Id,ActiveState,SubState,NRestarts,ActiveEnterTimestampMonotonic,ExecMainStartTimestamp --no-pager \
      | tr '\n' ' ' >>"$output"
    printf '\n' >>"$output"
  done
}
service_snapshot "$WORK/raw/services-before.txt"

ALLOWED_READ_PATHS=(
  /health /readyz /livez
  "/api/dashboard/all?month=$PROBE_MONTH"
  /api/target-calculator/scenarios
  /salarii/agents/summary?limit=1
  /salarii/records?limit=1
  "/api/grile/pilot-v2?month=$PROBE_MONTH"
  /api/import/history
  /api/exports/catalog
  /api/exports/operations/resumable
)
is_allowed_path() {
  local candidate="$1" allowed
  for allowed in "${ALLOWED_READ_PATHS[@]}"; do [[ "$candidate" == "$allowed" ]] && return 0; done
  return 1
}
probe_get() {
  local name="$1" base="$2" path="$3" expected="$4" cookie="${5:-}" body status started duration
  is_allowed_path "$path" || die "unexpected non-read-only probe path: $path"
  body="$WORK/raw/http-${name}.body"
  started="$(date +%s%N)"
  if [[ -n "$cookie" ]]; then
    status="$(curl --silent --show-error --location --max-redirs 0 --max-time 15 \
      --request GET --cookie "$cookie" --output "$body" --write-out '%{http_code}' "$base$path")"
  else
    status="$(curl --silent --show-error --location --max-redirs 0 --max-time 15 \
      --request GET --output "$body" --write-out '%{http_code}' "$base$path")"
  fi
  duration="$(( ($(date +%s%N) - started) / 1000000 ))"
  [[ "$status" == "$expected" ]] || die "probe $name returned $status, expected $expected"
  "$PYTHON" - "$name" "$path" "$status" "$duration" "$body" \
    "$WORK/fragments/http-${name}.json" <<'PY'
import hashlib,json,pathlib,sys
name,path,status,duration,body,out=sys.argv[1:]
b=pathlib.Path(body).read_bytes()
payload={"name":name,"method":"GET","path":path,"status":int(status),"duration_ms":int(duration),"body_bytes":len(b),"body_sha256":hashlib.sha256(b).hexdigest()}
if status=="200" and (path.startswith("/api/") or path.startswith("/salarii/")):
    value=json.loads(b); payload["json_type"]=type(value).__name__
    if name=="grile":
        stores=[s for m in value.get("managers",[]) for s in m.get("stores",[])]
        if value.get("store_count")!=21 or len(stores)!=21 or len({s.get("site_code") for s in stores})!=21: raise SystemExit("Grile V2 snapshot is not exact 21/21")
        payload["grile_store_count"]=21; payload["grile_unique_store_count"]=21; payload["google_io_executed"]=False
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY
}

probe_health_round() {
  local round="$1"
  probe_get "local-livez-$round" "$LOCAL_BASE" /livez 200
  probe_get "local-readyz-$round" "$LOCAL_BASE" /readyz 200
  probe_get "public-health-$round" "$PUBLIC_BASE" /health 200
  probe_get "public-readyz-$round" "$PUBLIC_BASE" /readyz 200
}

probe_health_round 0
probe_get dashboard "$PUBLIC_BASE" "/api/dashboard/all?month=$PROBE_MONTH" 200 "$MANAGER_COOKIE_FILE"
probe_get target "$PUBLIC_BASE" /api/target-calculator/scenarios 200 "$MANAGER_COOKIE_FILE"
probe_get salary-agents "$PUBLIC_BASE" /salarii/agents/summary?limit=1 200 "$MANAGER_COOKIE_FILE"
probe_get salary-records "$PUBLIC_BASE" /salarii/records?limit=1 200 "$MANAGER_COOKIE_FILE"
probe_get grile "$PUBLIC_BASE" "/api/grile/pilot-v2?month=$PROBE_MONTH" 200 "$MANAGER_COOKIE_FILE"
probe_get settings-imports "$PUBLIC_BASE" /api/import/history 200 "$MANAGER_COOKIE_FILE"
probe_get settings-exports "$PUBLIC_BASE" /api/exports/catalog 200 "$MANAGER_COOKIE_FILE"
probe_get settings-resumable "$PUBLIC_BASE" /api/exports/operations/resumable 200 "$MANAGER_COOKIE_FILE"
probe_get salary-forbidden "$PUBLIC_BASE" /salarii/agents/summary?limit=1 403 "$FORBIDDEN_COOKIE_FILE"
sleep 60
probe_health_round 1
sleep 60
probe_health_round 2
service_snapshot "$WORK/raw/services-after.txt"
cmp -s "$WORK/raw/services-before.txt" "$WORK/raw/services-after.txt" \
  || die "one or more Retail services restarted during AC-17 observation"

curl --fail --silent --show-error --max-time 15 --request GET \
  "$PROMETHEUS_BASE/api/v1/targets" >"$WORK/raw/prom-targets.json"
curl --fail --silent --show-error --max-time 15 --request GET \
  "$PROMETHEUS_BASE/api/v1/rules" >"$WORK/raw/prom-rules.json"
curl --fail --silent --show-error --max-time 15 --request GET --get \
  --data-urlencode 'query=count({__name__=~".*outbox.*"}) by (__name__)' \
  "$PROMETHEUS_BASE/api/v1/query" >"$WORK/raw/prom-outbox.json"
curl --fail --silent --show-error --max-time 15 --request GET --get \
  --data-urlencode 'query=unihub_glitchtip_events_1h{project="unihub-retail"}' \
  "$PROMETHEUS_BASE/api/v1/query" >"$WORK/raw/prom-glitchtip.json"
"$PYTHON" - "$WORK/raw/prom-targets.json" "$WORK/raw/prom-rules.json" \
  "$WORK/raw/prom-outbox.json" "$WORK/raw/prom-glitchtip.json" \
  "$WORK/fragments/prometheus.json" <<'PY'
import json,math,pathlib,sys
targets,rules,outbox,glitch,out=map(pathlib.Path,sys.argv[1:])
t=json.loads(targets.read_text()); required={"unihub-retail-web","unihub-retail-operations","unihub-retail-imports","unihub-retail-grile","unihub-retail-exports","unihub-retail-salary-exports"}
healthy={x.get("labels",{}).get("job") for x in t.get("data",{}).get("activeTargets",[]) if x.get("health")=="up"}
if not required<=healthy: raise SystemExit("Prometheus Retail targets are not all UP")
r=json.loads(rules.read_text()); groups=r.get("data",{}).get("groups",[])
if not any(g.get("name")=="unihub-retail-slo-recording" for g in groups) or not any(g.get("name")=="unihub-retail-slo-alerts" for g in groups): raise SystemExit("Retail rules are not loaded")
bad=[x for g in groups for x in g.get("rules",[]) if x.get("health") not in (None,"ok")]
if bad: raise SystemExit("unhealthy Prometheus rule")
o=json.loads(outbox.read_text()).get("data",{}).get("result",[]); names=sorted({x.get("metric",{}).get("__name__","") for x in o})
if not names or not all(math.isfinite(float(x.get("value",[0,"nan"])[1])) for x in o): raise SystemExit("outbox metrics absent or non-finite")
for token in ("pending","head_blocked","completed","failed","duration"):
    if not any(token in n for n in names): raise SystemExit(f"outbox metric family missing: {token}")
g=json.loads(glitch.read_text()).get("data",{}).get("result",[])
if len(g)!=1 or float(g[0].get("value",[0,"nan"])[1])!=0: raise SystemExit("recent Retail GlitchTip events are nonzero or absent")
pathlib.Path(out).write_text(json.dumps({"schema_version":1,"result":"PASS","healthy_targets":sorted(required),"rule_groups":["unihub-retail-slo-alerts","unihub-retail-slo-recording"],"outbox_metric_names":names,"glitchtip_events_1h":0},sort_keys=True,separators=(",",":"))+"\n")
PY

DEPLOYED_AT="$(sed -n 's/^UPDATED_AT=//p' "$BACKUP_HANDLE/release.env")"
[[ -n "$DEPLOYED_AT" ]] || die "deploy timestamp missing"
JOURNAL_ARGS=()
for unit in "${EXPECTED_UNITS[@]}"; do JOURNAL_ARGS+=("--unit=$unit"); done
journalctl --no-pager --since "$DEPLOYED_AT" --output=short-iso \
  "${JOURNAL_ARGS[@]}" >"$WORK/raw/journal.txt"
"$PYTHON" - "$WORK/raw/journal.txt" "$WORK/fragments/journal.json" <<'PY'
import collections,hashlib,json,pathlib,re,sys
lines=pathlib.Path(sys.argv[1]).read_text(errors="replace").splitlines()
fatal=re.compile(r"traceback|critical|panic|unhandled exception|segmentation fault",re.I)
warn=re.compile(r"\bwarn(?:ing)?\b",re.I); volatile=re.compile(r"\b(?:[0-9a-f]{8,}|\d{2,}|sp1_[0-9a-f]{64})\b",re.I)
google_get=re.compile(r"\bGET\b[^\n]*(?:sheets\.googleapis\.com|www\.googleapis\.com/.*/spreadsheets)",re.I)
fatals=[x for x in lines if fatal.search(x)]
google_get_count=sum(bool(google_get.search(x)) for x in lines)
fingerprints=collections.Counter(hashlib.sha256(volatile.sub("<v>",x).encode()).hexdigest() for x in lines if warn.search(x))
repeated={k:v for k,v in fingerprints.items() if v>=3}
if fatals or repeated or google_get_count: raise SystemExit("journal contains fatal, repeated warning or Google Sheets GET pattern")
pathlib.Path(sys.argv[2]).write_text(json.dumps({"schema_version":1,"result":"PASS","line_count":len(lines),"raw_sha256":hashlib.sha256(("\n".join(lines)+"\n").encode()).hexdigest(),"fatal_count":len(fatals),"warning_fingerprint_counts":dict(fingerprints),"repeated_warning_fingerprints":repeated,"google_sheets_get_count":google_get_count},sort_keys=True,separators=(",",":"))+"\n")
PY
rm -f -- "$WORK/raw/journal.txt"

"$PYTHON" - "$LIVE_ROOT" "$MAIN_B_SHA" "$WORK/fragments/refs-primary.json" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root,sha,out=sys.argv[1:]
blocked_branches={
 "codex/retail-definitive-closure-20260812",
 "codex/retail-definitive-closure-b-20260813",
 "codex/retail-close-authority","codex/retail-close-contracts",
 "codex/retail-close-correctness","codex/retail-close-frontend",
 "codex/retail-close-outbox-contract","codex/retail-close-scale-authority",
 "codex/retail-close-structural",
}
blocked_worktrees={
 "/opt/Mobiup/.worktrees/retail-close-authority",
 "/opt/Mobiup/.worktrees/retail-close-contracts",
 "/opt/Mobiup/.worktrees/retail-close-correctness",
 "/opt/Mobiup/.worktrees/retail-close-frontend",
 "/opt/Mobiup/.worktrees/retail-close-outbox-contract",
 "/opt/Mobiup/.worktrees/retail-close-preview",
 "/opt/Mobiup/.worktrees/retail-close-scale",
 "/opt/Mobiup/.worktrees/retail-close-structural",
}
def git(*args): return subprocess.check_output(["git","-C",root,*args],text=True).strip()
refs=git("for-each-ref","--format=%(refname) %(objectname)","refs/heads","refs/remotes/origin").splitlines()
worktrees=git("worktree","list","--porcelain").splitlines()
bad_refs=[line for line in refs if line.split()[0].removeprefix("refs/heads/").removeprefix("refs/remotes/origin/") in blocked_branches]
bad_worktrees=[line for line in worktrees if (line.startswith("worktree ") and line[9:] in blocked_worktrees) or (line.startswith("branch refs/heads/") and line[18:] in blocked_branches)]
if git("rev-parse","HEAD")!=sha or git("rev-parse","origin/main")!=sha or git("branch","--show-current")!="main" or git("status","--porcelain=v1","--untracked-files=all") or bad_refs or bad_worktrees:
 raise SystemExit("primary Git/task-ref reconciliation failed")
payload={"schema_version":1,"result":"PASS","host":"server","head":sha,"origin_main":sha,"branch":"main","status_clean":True,"refs_sha256":hashlib.sha256(("\n".join(refs)+"\n").encode()).hexdigest(),"worktree_manifest_sha256":hashlib.sha256(("\n".join(worktrees)+"\n").encode()).hexdigest(),"blocked_branches":sorted(blocked_branches),"blocked_worktrees":sorted(blocked_worktrees),"task_refs":[],"task_worktrees":[]}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY

sudo -u andrei ssh -o BatchMode=yes -o ConnectTimeout=10 dell-standby \
  python3 - "$MAIN_B_SHA" <<'PY' \
  | tee "$WORK/fragments/refs-dell.json" >/dev/null
import hashlib,json,pathlib,socket,subprocess,sys
sha=sys.argv[1]; root="/opt/Mobiup/unihub-retail"
blocked_branches={
 "codex/retail-definitive-closure-20260812",
 "codex/retail-definitive-closure-b-20260813",
 "codex/retail-close-authority","codex/retail-close-contracts",
 "codex/retail-close-correctness","codex/retail-close-frontend",
 "codex/retail-close-outbox-contract","codex/retail-close-scale-authority",
 "codex/retail-close-structural",
}
blocked_worktrees={
 "/opt/Mobiup/.worktrees/retail-close-authority",
 "/opt/Mobiup/.worktrees/retail-close-contracts",
 "/opt/Mobiup/.worktrees/retail-close-correctness",
 "/opt/Mobiup/.worktrees/retail-close-frontend",
 "/opt/Mobiup/.worktrees/retail-close-outbox-contract",
 "/opt/Mobiup/.worktrees/retail-close-preview",
 "/opt/Mobiup/.worktrees/retail-close-scale",
 "/opt/Mobiup/.worktrees/retail-close-structural",
}
def git(*args): return subprocess.check_output(["git","-C",root,*args],text=True).strip()
refs=git("for-each-ref","--format=%(refname) %(objectname)","refs/heads","refs/remotes/origin").splitlines()
worktrees=git("worktree","list","--porcelain").splitlines()
remote_heads=git("ls-remote","--heads","origin").splitlines()
bad_refs=[line for line in refs if line.split()[0].removeprefix("refs/heads/").removeprefix("refs/remotes/origin/") in blocked_branches]
bad_remote=[line for line in remote_heads if line.split()[1].removeprefix("refs/heads/") in blocked_branches]
bad_worktrees=[line for line in worktrees if (line.startswith("worktree ") and line[9:] in blocked_worktrees) or (line.startswith("branch refs/heads/") and line[18:] in blocked_branches)]
if socket.gethostname()!="dell-standby" or git("rev-parse","HEAD")!=sha or git("rev-parse","origin/main")!=sha or git("branch","--show-current")!="main" or git("status","--porcelain=v1","--untracked-files=all") or bad_refs or bad_remote or bad_worktrees:
 raise SystemExit("Dell Git/task-ref reconciliation failed")
print(json.dumps({"schema_version":1,"result":"PASS","host":"dell-standby","head":sha,"origin_main":sha,"branch":"main","status_clean":True,"refs_sha256":hashlib.sha256(("\n".join(refs)+"\n").encode()).hexdigest(),"remote_heads_sha256":hashlib.sha256(("\n".join(remote_heads)+"\n").encode()).hexdigest(),"worktree_manifest_sha256":hashlib.sha256(("\n".join(worktrees)+"\n").encode()).hexdigest(),"blocked_branches":sorted(blocked_branches),"blocked_worktrees":sorted(blocked_worktrees),"task_refs":[],"task_remote_refs":[],"task_worktrees":[]},sort_keys=True,separators=(",",":")))
PY

sudo -u andrei gh pr view "$RELEASE_A_PR" --repo "$GITHUB_REPOSITORY" \
  --json number,state,isDraft,headRefName,baseRefName,mergeCommit,url \
  | tee "$WORK/raw/pr-a.json" >/dev/null
sudo -u andrei gh pr view "$RELEASE_B_PR" --repo "$GITHUB_REPOSITORY" \
  --json number,state,isDraft,headRefName,baseRefName,mergeCommit,url \
  | tee "$WORK/raw/pr-b.json" >/dev/null
sudo -u andrei git -C "$LIVE_ROOT" ls-remote --heads origin \
  "refs/heads/$TASK_A_BRANCH" "refs/heads/$TASK_B_BRANCH" \
  | tee "$WORK/raw/task-remote-heads.txt" >/dev/null
"$PYTHON" - "$WORK/raw/pr-a.json" "$WORK/raw/pr-b.json" \
  "$WORK/raw/task-remote-heads.txt" "$MAIN_A_SHA" "$MAIN_B_SHA" \
  "$RELEASE_A_PR" "$RELEASE_B_PR" "$TASK_A_BRANCH" "$TASK_B_BRANCH" \
  "$WORK/fragments/refs-github.json" <<'PY'
import hashlib,json,pathlib,sys
pa,pb,heads,a,b,an,bn,ab,bb,out=sys.argv[1:]
av=json.loads(pathlib.Path(pa).read_text()); bv=json.loads(pathlib.Path(pb).read_text())
def valid(value,number,branch,sha):
 return value.get("number")==int(number) and value.get("state")=="MERGED" and value.get("isDraft") is False and value.get("headRefName")==branch and value.get("baseRefName")=="main" and value.get("mergeCommit",{}).get("oid")==sha
remote=pathlib.Path(heads).read_text()
if not valid(av,an,ab,a) or not valid(bv,bn,bb,b) or remote.strip(): raise SystemExit("GitHub PR/task-ref reconciliation failed")
payload={"schema_version":1,"result":"PASS","repository":"anervalens-netizen/unihub-retail","release_a":{"number":int(an),"branch":ab,"merge_sha":a,"state":"MERGED"},"release_b":{"number":int(bn),"branch":bb,"merge_sha":b,"state":"MERGED"},"task_remote_heads":[],"queries_sha256":hashlib.sha256(pathlib.Path(pa).read_bytes()+pathlib.Path(pb).read_bytes()+pathlib.Path(heads).read_bytes()).hexdigest()}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY
rm -f -- "$WORK/raw/pr-a.json" "$WORK/raw/pr-b.json" "$WORK/raw/task-remote-heads.txt"

"$PYTHON" - "$WORK" "$EVIDENCE" "$MAIN_A_SHA" "$MAIN_B_SHA" "$SCRIPT_PATH" \
  "$A_ARTIFACT_DIR" "$B_ARTIFACT_DIR" "$BACKUP_HANDLE" "$PROBE_MONTH" <<'PY'
import hashlib,json,pathlib,sys,time
work,evidence,a,b,script,adir,bdir,backup,month=sys.argv[1:]
w=pathlib.Path(work); fragments={}
for p in sorted((w/"fragments").glob("*.json")):
    value=json.loads(p.read_text())
    if value.get("result") not in (None,"PASS"): raise SystemExit(f"non-PASS fragment: {p.name}")
    fragments[p.name] = {"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"evidence":value}
required={"release-a-verification.json","release-b-artifact.json","backup.json","schema-outbox.json","prometheus.json","journal.json","refs-primary.json","refs-dell.json","refs-github.json","http-dashboard.json","http-target.json","http-salary-agents.json","http-salary-records.json","http-grile.json","http-settings-imports.json","http-settings-exports.json","http-settings-resumable.json","http-salary-forbidden.json"}
required |= {f"http-{where}-{kind}-{n}.json" for n in range(3) for where in ("local","public") for kind in (("livez","readyz") if where=="local" else ("health","readyz"))}
missing=sorted(required-set(fragments))
if missing: raise SystemExit(f"AC-17 fragment inventory incomplete: {missing}")
raw_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((w/"raw").iterdir()) if p.is_file()}
payload={"schema_version":1,"result":"PASS","main_a_sha":a,"main_b_sha":b,"probe_month":month,"observed_seconds":120,"verified_at_epoch":int(time.time()),"verifier":{"path":"scripts/verify_deployed_release.sh","sha256":hashlib.sha256(pathlib.Path(script).read_bytes()).hexdigest()},"external_inputs":{"release_a_artifact_dir":str(pathlib.Path(adir).resolve()),"release_b_artifact_dir":str(pathlib.Path(bdir).resolve()),"backup_handle":str(pathlib.Path(backup).resolve())},"commands":{"http_method":"GET only","health_rounds":[0,60,120],"database_transaction":"READ ONLY","journal_since":"backup release UPDATED_AT"},"fragments":fragments,"raw_output_sha256":raw_hashes,"salary_export_executed":False,"finance_apply_executed":False,"target_finalize_executed":False,"grile_destructive_executed":False,"deployment_mutation_executed":False,"cookies_recorded":False}
dest=pathlib.Path(evidence); dest.mkdir(mode=0o700)
(dest/"evidence.json").write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
for p in sorted((w/"fragments").glob("*.json")): (dest/p.name).write_bytes(p.read_bytes())
PY

chmod -R go-rwx "$EVIDENCE"
printf 'AC-17 deployed release verification PASS: %s (%s)\n' "$MAIN_B_SHA" "$EVIDENCE"
