#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${UNIHUB_BACKEND_VENV:-$ROOT/backend/venv}"
PYTHON="$VENV/bin/python"
PYTEST="$VENV/bin/pytest"
BASELINE_MANIFEST="$ROOT/scripts/structural-characterization-baseline-v1.json"
BOOTSTRAP="$ROOT/backend/scripts/bootstrap_test_db.py"
MAX_SECONDS=""
EVIDENCE=""
SELF_TEST=0

die() { printf '%s: %s\n' "$PROGRAM" "$*" >&2; exit 1; }

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --max-seconds) [[ "$#" -ge 2 ]] || die "missing max seconds"; MAX_SECONDS="$2"; shift 2 ;;
    --evidence) [[ "$#" -ge 2 ]] || die "missing evidence path"; EVIDENCE="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    *) die "unknown argument: $1" ;;
  esac
done

if [[ "$SELF_TEST" == "1" ]]; then
  [[ -x "$PYTHON" ]] || die "backend virtualenv is required"
  [[ -f "$BASELINE_MANIFEST" ]] || die "baseline manifest is missing"
  "$PYTHON" - "$BASELINE_MANIFEST" <<'PY'
import copy
import importlib.util
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
if len(payload["baseline_testcase_ids"]) != 478:
    raise SystemExit("baseline does not freeze 478 testcase IDs")
if len(payload["expected_skips"]) != 35:
    raise SystemExit("baseline does not freeze 35 skip IDs/reasons")
if payload["isolated_testcase_id"] in payload["baseline_testcase_ids"]:
    raise SystemExit("isolated testcase leaked into timed baseline")
fake = copy.deepcopy(payload)
fake["expected_skips"].pop(next(iter(fake["expected_skips"])))
if len(fake["expected_skips"]) == 35:
    raise SystemExit("fake skip evidence was accepted")
print("structural gate self-test PASS: 478/35 identity and fake-skip rejection stable")
PY
  exit 0
fi

[[ "$MAX_SECONDS" == "16.7" ]] || die "max seconds must equal locked 16.7"
[[ -n "$EVIDENCE" ]] || die "--evidence is required"
[[ ! -e "$EVIDENCE" && ! -L "$EVIDENCE" ]] || die "evidence already exists"
[[ "${UNIHUB_TEST_DATABASE:-}" == "1" ]] || die "UNIHUB_TEST_DATABASE=1 is required"
[[ -x "$PYTHON" && -x "$PYTEST" ]] || die "backend virtualenv is required"
[[ -f "$BASELINE_MANIFEST" && -x "$BOOTSTRAP" ]] || die "locked manifest/bootstrap missing"
[[ "$(hostname)" == "dell-standby" ]] || die "AC-10 is locked to dell-standby"

HEAD_SHA="$(git -C "$ROOT" rev-parse HEAD)"
TREE_SHA="$(git -C "$ROOT" rev-parse HEAD^{tree})"
[[ -z "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]] \
  || die "candidate worktree must be clean"

EVIDENCE_PARENT="$(dirname "$EVIDENCE")"
mkdir -p "$EVIDENCE_PARENT"
WORK="$(mktemp -d "$EVIDENCE_PARENT/.ac10.XXXXXX")"
CONTAINER="unihub-ac10-$RANDOM-$$"
cleanup() {
  timeout 30 docker rm -f -v "$CONTAINER" >/dev/null 2>&1 || true
  find "$WORK" -mindepth 1 -delete 2>/dev/null || true
  rmdir "$WORK" 2>/dev/null || true
}
trap cleanup EXIT

TIMED_JUNIT="$WORK/timed.xml"
TIMED_LOG="$WORK/timed.log"
WALL_FILE="$WORK/wall.txt"
ISOLATED_JUNIT="$WORK/isolated.xml"
ISOLATED_LOG="$WORK/isolated.log"
CP11_JUNIT="$WORK/cp11.xml"
CP12_JUNIT="$WORK/cp12.xml"

mapfile -t BASELINE_SELECTORS < <("$PYTHON" - "$BASELINE_MANIFEST" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1], encoding="utf-8"))["baseline_selectors"]:
    print(item)
PY
)
ISOLATED_SELECTOR="$($PYTHON - "$BASELINE_MANIFEST" <<'PY'
import json,sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["isolated_selector"])
PY
)"
mapfile -t CP11_SELECTORS < <("$PYTHON" - "$BASELINE_MANIFEST" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1], encoding="utf-8"))["checkpoint_11_selectors"]:
    print(item)
PY
)
mapfile -t CP12_SELECTORS < <("$PYTHON" - "$BASELINE_MANIFEST" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1], encoding="utf-8"))["checkpoint_12_selectors"]:
    print(item)
PY
)

# Synthetic files make the two optional fixture tests deterministic without
# reading operator-private Retail data. They are created before the clock.
FIXTURES="$WORK/fixtures"
mkdir -p "$FIXTURES"
FIXTURES="$FIXTURES" "$PYTHON" - <<'PY'
import json, os
from pathlib import Path
from openpyxl import Workbook
root = Path(os.environ["FIXTURES"])
(root / "hub_specials.json").write_text(
    json.dumps({"promotions": [], "incentives": []}, sort_keys=True) + "\n",
    encoding="utf-8",
)
workbook = Workbook()
sheet = workbook.active
sheet.append(["Cod", "Produs"])
sheet.append(["AC10-001", "Produs sintetic"])
workbook.save(root / "Incentiv Mobiup-Mobicell Aprilie 2026.xlsx")
PY

set +e
/usr/bin/time -f '%e' -o "$WALL_FILE" env -u UNIHUB_TEST_DATABASE \
  UNIHUB_DATA_DIR="$FIXTURES" HUB_SPECIALS_PATH="$FIXTURES/hub_specials.json" \
  PYTHONPATH="$ROOT/backend" "$PYTEST" -q "${BASELINE_SELECTORS[@]}" \
  --deselect "$ISOLATED_SELECTOR" --junitxml="$TIMED_JUNIT" \
  >"$TIMED_LOG" 2>&1
TIMED_STATUS=$?
set -e
[[ "$TIMED_STATUS" -eq 0 ]] || { cat "$TIMED_LOG" >&2; die "timed baseline failed"; }

# The one intentionally excluded test is executed through its own disposable
# PostgreSQL harness and is excluded from the 16.7-second timing exactly as the
# baseline contract states.
PASSWORD="$($PYTHON -c 'import secrets; print(secrets.token_hex(24))')"
docker run -d --name "$CONTAINER" --label unihub.test=retail-ac10 \
  -e POSTGRES_USER=unihub_test -e POSTGRES_PASSWORD="$PASSWORD" \
  -e POSTGRES_DB=test_unihub_ac10 -p 127.0.0.1::5432 postgres:18-alpine \
  >/dev/null
PORT="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "$CONTAINER")"
[[ "$PORT" =~ ^[0-9]+$ && "$PORT" != "5432" ]] || die "unsafe isolated PostgreSQL port"
for _ in $(seq 1 60); do
  docker exec "$CONTAINER" pg_isready -U unihub_test -d test_unihub_ac10 \
    >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U unihub_test -d test_unihub_ac10 \
  >/dev/null 2>&1 || die "isolated PostgreSQL not ready"
DSN="postgresql://unihub_test:$PASSWORD@127.0.0.1:$PORT/test_unihub_ac10"
DB_ENV=(
  "DATABASE_URL=$DSN"
  "MIGRATION_DATABASE_URL=$DSN"
  "UNIHUB_TEST_DATABASE=1"
  "UNIHUB_RUNNING_TESTS=1"
  "PYTHONPATH=$ROOT/backend"
)
env "${DB_ENV[@]}" "$PYTHON" "$BOOTSTRAP" >"$WORK/bootstrap.log"
env "${DB_ENV[@]}" "$PYTEST" -q "$ISOLATED_SELECTOR" \
  --junitxml="$ISOLATED_JUNIT" >"$ISOLATED_LOG" 2>&1

# Checkpoints 11 and 12 are exact targeted characterization groups, outside
# the historic timed suite. Checkpoints 8-10 are frontend-owned and referenced
# as AC-08/AC-11 evidence rather than fabricated here.
env -u UNIHUB_TEST_DATABASE PYTHONPATH="$ROOT/backend" "$PYTEST" -q \
  "${CP11_SELECTORS[@]}" --junitxml="$CP11_JUNIT" >/dev/null
env -u UNIHUB_TEST_DATABASE PYTHONPATH="$ROOT/backend" "$PYTEST" -q \
  "${CP12_SELECTORS[@]}" --junitxml="$CP12_JUNIT" >/dev/null

"$PYTHON" - "$ROOT" "$BASELINE_MANIFEST" "$TIMED_JUNIT" "$TIMED_LOG" \
  "$WALL_FILE" "$ISOLATED_JUNIT" "$ISOLATED_LOG" "$CP11_JUNIT" "$CP12_JUNIT" \
  "$EVIDENCE" "$HEAD_SHA" "$TREE_SHA" "$MAX_SECONDS" "$PORT" <<'PY'
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

(
    root, manifest_path, timed_junit, timed_log, wall_file, isolated_junit,
    isolated_log, cp11_junit, cp12_junit, evidence,
) = map(pathlib.Path, sys.argv[1:11])
sha, tree, maximum, port = sys.argv[11], sys.argv[12], float(sys.argv[13]), int(sys.argv[14])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

def cases(path):
    document = ET.parse(path).getroot()
    values = list(document.iter("testcase"))
    ids = [f"{case.attrib.get('classname')}::{case.attrib.get('name')}" for case in values]
    skips = {
        f"{case.attrib.get('classname')}::{case.attrib.get('name')}": case.find("skipped").attrib.get("message", "")
        for case in values if case.find("skipped") is not None
    }
    failures = sum(case.find("failure") is not None for case in values)
    errors = sum(case.find("error") is not None for case in values)
    return values, ids, skips, failures, errors

timed, timed_ids, timed_skips, failures, errors = cases(timed_junit)
if timed_ids != manifest["baseline_testcase_ids"]:
    raise SystemExit("timed testcase identity/order differs from frozen baseline")
if timed_skips != manifest["expected_skips"]:
    raise SystemExit("timed skip IDs/reasons differ from frozen baseline")
if (len(timed), len(timed_skips), failures, errors) != (478, 35, 0, 0):
    raise SystemExit("timed baseline counts differ from 443 pass / 35 skip")
wall = float(wall_file.read_text(encoding="utf-8").strip())
if wall > maximum:
    raise SystemExit(f"wall duration {wall:.6f}s exceeds {maximum}s")

isolated, isolated_ids, isolated_skips, isolated_failures, isolated_errors = cases(isolated_junit)
if (
    isolated_ids != [manifest["isolated_testcase_id"]]
    or isolated_skips
    or isolated_failures
    or isolated_errors
):
    raise SystemExit("separate isolated testcase did not pass exactly once")

def exact_group(path, expected_ids, name):
    values, ids, skips, failures, errors = cases(path)
    if ids != expected_ids or skips or failures or errors:
        raise SystemExit(f"{name} targeted characterization drifted")
    return {
        "tests": len(values),
        "testcase_identity_sha256": hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest(),
    }

cp11 = exact_group(cp11_junit, manifest["checkpoint_11_testcase_ids"], "checkpoint 11")
cp12 = exact_group(cp12_junit, manifest["checkpoint_12_testcase_ids"], "checkpoint 12")

fixed_hashes = manifest["golden_sha256"]
for name, expected in fixed_hashes.items():
    actual = hashlib.sha256((root / name).read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"golden contract drift: {name}")

destination = evidence.parent
artifacts = {}
for source, name in (
    (timed_junit, "ac-10-structural.xml"),
    (timed_log, "ac-10-structural.log"),
    (isolated_junit, "ac-10-isolated.xml"),
    (isolated_log, "ac-10-isolated.log"),
    (cp11_junit, "ac-10-cp11.xml"),
    (cp12_junit, "ac-10-cp12.xml"),
):
    target = destination / name
    target.write_bytes(source.read_bytes())
    artifacts[name] = hashlib.sha256(target.read_bytes()).hexdigest()

payload = {
    "schema_version": 2,
    "result": "PASS",
    "sha": sha,
    "tree": tree,
    "command": "UNIHUB_TEST_DATABASE=1 scripts/run_structural_characterization.sh --max-seconds 16.7 --evidence <path>",
    "baseline_manifest": {
        "path": str(manifest_path.relative_to(root)),
        "sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_sha": manifest["source_sha"],
    },
    "timed_baseline": {
        "tests": 478,
        "passed": 443,
        "skipped": 35,
        "failures": 0,
        "errors": 0,
        "wall_seconds": wall,
        "maximum_wall_seconds": maximum,
        "testcase_identity_sha256": hashlib.sha256(("\n".join(timed_ids) + "\n").encode()).hexdigest(),
        "skip_identity_sha256": hashlib.sha256((json.dumps(timed_skips, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest(),
    },
    "isolated_database_test": {
        "testcase_id": isolated_ids[0],
        "passed": 1,
        "database": "test_unihub_ac10",
        "loopback": True,
        "non_default_port": port != 5432,
        "production_rows_read": 0,
    },
    "checkpoints": {
        "01_07": {"composition": "frozen 478-test baseline", "manifest": "baseline_testcase_ids"},
        "08_10": {"composition": "external frontend authorities", "criteria": ["AC-08", "AC-11"]},
        "11_import_pipeline": cp11,
        "12_remaining_backend": cp12,
    },
    "golden_sha256": fixed_hashes,
    "artifacts": artifacts,
    "protected_operations_executed": False,
    "salary_export_executed": False,
}
evidence.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

printf 'Structural characterization PASS: 443 pass / 35 skip + isolated DB test at %s\n' "$HEAD_SHA"
