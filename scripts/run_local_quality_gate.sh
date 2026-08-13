#!/usr/bin/bash -p

set -Eeuo pipefail
umask 077

unset \
  PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONINSPECT \
  MYPYPATH MYPY_CONFIG_FILE \
  NODE_OPTIONS NODE_PATH \
  BASH_ENV ENV CDPATH GLOBIGNORE || true

PROGRAM="$(basename "$0")"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/backend/venv/bin/python"
PYTHON_BASE="/usr/bin/python3.12"
EXPECTED_PYTHON_SHA256="1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
EXPECTED_SYSTEM_SITECUSTOMIZE_SHA256="43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e"
EXPECTED_SITE_PACKAGES_SHA256="81524f503c2b5b2e66bba0ab4cf434e53f79f3fbcd390f6e3aba884acb50848d"
NODE=""
NPM_CLI=""
EXPECTED_COSIGN_SHA256="4629c757b7618056f8ddd7e2625ae9fdd94c0372a65049520bc7d9df9efc7f71"
EXPECTED_NODE_SHA256="81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90"
EXPECTED_NPM_CLI_SHA256="8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7"
SHA=""
EVIDENCE=""
RELEASE_A_SHA="${MAIN_A_SHA:-}"
RELEASE_A_ARTIFACT="${ARTIFACT_A_DIR:-}"
SEQUENTIAL=0
SELF_TEST=0
INTERNAL_MODE=""
INTERNAL_EVIDENCE=""
CURRENT_TREE=""
INPUT_SHA256=""
STEPS_DIR=""
SELF_TEST_TEMP=""
INTERNAL_TEMP=""

cleanup_transient() {
  if [[ -n "$SELF_TEST_TEMP" && -d "$SELF_TEST_TEMP" ]]; then
    rm -rf -- "$SELF_TEST_TEMP"
  fi
  if [[ -n "$INTERNAL_TEMP" && -d "$INTERNAL_TEMP" ]]; then
    rm -rf -- "$INTERNAL_TEMP"
  fi
}
trap cleanup_transient EXIT

die() { printf '%s: %s\n' "$PROGRAM" "$*" >&2; exit 1; }

verify_python_identity() {
  [[ -x "$PYTHON" && "$(readlink -f "$PYTHON")" == "$PYTHON_BASE" \
    && "$(sha256sum "$PYTHON_BASE" | awk '{print $1}')" == "$EXPECTED_PYTHON_SHA256" ]] \
    || die "backend Python is not rooted in the pinned /usr/bin/python3.12"
}

usage() {
  printf 'usage: %s --sha <40-char-sha> --sequential --evidence <dir> [--release-a-sha <sha>] [--release-a-artifact-dir <dir>]\n' "$PROGRAM" >&2
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --sha) [[ "$#" -ge 2 ]] || die "missing --sha value"; SHA="$2"; shift 2 ;;
    --sequential) SEQUENTIAL=1; shift ;;
    --evidence) [[ "$#" -ge 2 ]] || die "missing --evidence value"; EVIDENCE="$2"; shift 2 ;;
    --release-a-sha) [[ "$#" -ge 2 ]] || die "missing Release-A SHA"; RELEASE_A_SHA="$2"; shift 2 ;;
    --release-a-artifact-dir) [[ "$#" -ge 2 ]] || die "missing Release-A artifact"; RELEASE_A_ARTIFACT="$2"; shift 2 ;;
    --self-test) SELF_TEST=1; shift ;;
    --internal-secret-scan) [[ "$#" -ge 2 ]] || die "missing internal evidence"; INTERNAL_MODE="secret"; INTERNAL_EVIDENCE="$2"; shift 2 ;;
    --internal-operational) [[ "$#" -ge 2 ]] || die "missing internal evidence"; INTERNAL_MODE="operational"; INTERNAL_EVIDENCE="$2"; shift 2 ;;
    --internal-python-cache-clean) [[ "$#" -ge 2 ]] || die "missing internal evidence"; INTERNAL_MODE="python-cache-clean"; INTERNAL_EVIDENCE="$2"; shift 2 ;;
    --internal-python-lock) [[ "$#" -ge 2 ]] || die "missing internal evidence"; INTERNAL_MODE="python-lock"; INTERNAL_EVIDENCE="$2"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

sha256_text() {
  "$PYTHON_BASE" -I -S -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
}

validate_pass_record() {
  local record="$1" command_sha="$2"
  [[ -f "$record" && ! -L "$record" ]] || return 1
  "$PYTHON_BASE" -I -S - "$record" "$SHA" "$CURRENT_TREE" "$INPUT_SHA256" "$command_sha" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

def tree_digest(root: Path) -> str:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise SystemExit(1)
        if path.is_file():
            entries.append(
                [path.relative_to(root).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()]
            )
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

record_path = Path(sys.argv[1])
payload = json.loads(record_path.read_text(encoding="utf-8"))
expected = {
    "schema_version": 1,
    "result": "PASS",
    "sha": sys.argv[2],
    "tree": sys.argv[3],
    "input_sha256": sys.argv[4],
    "command_sha256": sys.argv[5],
}
if any(payload.get(key) != value for key, value in expected.items()):
    raise SystemExit(1)
log = Path(str(payload.get("log", "")))
if not log.is_file() or log.is_symlink():
    raise SystemExit(1)
if hashlib.sha256(log.read_bytes()).hexdigest() != payload.get("log_sha256"):
    raise SystemExit(1)
for item in payload.get("outputs", []):
    path = Path(str(item.get("path", "")))
    kind = item.get("type")
    if path.is_symlink() or kind not in {"file", "directory"}:
        raise SystemExit(1)
    if kind == "file":
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item.get("sha256"):
            raise SystemExit(1)
    elif not path.is_dir() or tree_digest(path) != item.get("sha256"):
        raise SystemExit(1)
    if kind == "file" and path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            if value.get("result") in {"FAIL", "BLOCKED"} or value.get("pass") is False:
                raise SystemExit(1)
PY
}

write_pass_record() {
  local record="$1" command_sha="$2" log="$3" outputs_raw="$4"
  "$PYTHON_BASE" -I -S - "$record" "$SHA" "$CURRENT_TREE" "$INPUT_SHA256" "$command_sha" "$log" "$outputs_raw" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

def tree_digest(root: Path) -> str:
    entries = []
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise SystemExit(f"required step output contains symlink: {item}")
        if item.is_file():
            entries.append(
                [item.relative_to(root).as_posix(), hashlib.sha256(item.read_bytes()).hexdigest()]
            )
    return hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

record, sha, tree, input_sha, command_sha, log, raw_outputs = sys.argv[1:]
log_path = Path(log).resolve()
outputs = []
for raw in filter(None, raw_outputs.split("|")):
    path = Path(raw).resolve()
    if path.is_symlink() or not (path.is_file() or path.is_dir()):
        raise SystemExit(f"required step output is absent or unsafe: {path}")
    kind = "file" if path.is_file() else "directory"
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if kind == "file" else tree_digest(path)
    outputs.append({"path": str(path), "type": kind, "sha256": digest})
payload = {
    "schema_version": 1,
    "result": "PASS",
    "sha": sha,
    "tree": tree,
    "input_sha256": input_sha,
    "command_sha256": command_sha,
    "log": str(log_path),
    "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
    "outputs": outputs,
}
Path(record).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

run_step() {
  local id="$1" command="$2" outputs_raw="${3:-}"
  local command_sha record log
  verify_python_identity
  command_sha="$(printf '%s' "$command" | sha256_text)"
  record="$STEPS_DIR/$id.json"
  log="$STEPS_DIR/$id.log"
  # Installed Python and Node environments are mutable inputs. Every dependency
  # validation and downstream gate runs on each invocation; no stale PASS can
  # survive an in-place environment mutation.
  [[ ! -L "$record" && ! -L "$log" ]] || die "unsafe step evidence: $id"
  printf 'RUN %s\n' "$id"
  set +e
  (
    cd "$ROOT"
    export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1
    export PYTHONDONTWRITEBYTECODE=1
    export npm_config_offline=true VITE_FRONTEND_GLITCHTIP_DSN=
    PATH="$(dirname "$NODE"):/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    export PATH
    unset \
      PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONINSPECT \
      MYPYPATH MYPY_CONFIG_FILE \
      NODE_OPTIONS NODE_PATH \
      BASH_ENV ENV CDPATH GLOBIGNORE
    bash -Eeuo pipefail -c "$command"
  ) >"$log" 2>&1
  local status=$?
  set -e
  if [[ "$status" -ne 0 ]]; then
    tail -200 "$log" >&2 || true
    die "step $id failed with exit $status"
  fi
  write_pass_record "$record" "$command_sha" "$log" "$outputs_raw"
}

self_test() {
  [[ "$ROOT" == */unihub-retail ]] || die "repository root resolution failed"
  local record log forbidden command_sha output_a output_b output_c
  SELF_TEST_TEMP="$(mktemp -d)"
  SHA="1111111111111111111111111111111111111111"
  CURRENT_TREE="2222222222222222222222222222222222222222"
  INPUT_SHA256="$(printf stable | sha256sum | awk '{print $1}')"
  log="$SELF_TEST_TEMP/fake.log"
  printf 'manual PASS\n' >"$log"
  record="$SELF_TEST_TEMP/fake.json"
  printf '{"schema_version":1,"result":"PASS"}\n' >"$record"
  command_sha="$(printf command | sha256sum | awk '{print $1}')"
  if validate_pass_record "$record" "$command_sha"; then
    die "self-test accepted a hand-written PASS"
  fi
  output_a="$SELF_TEST_TEMP/a.json"
  output_b="$SELF_TEST_TEMP/b.xml"
  output_c="$SELF_TEST_TEMP/tree"
  mkdir "$output_c"
  printf '{"result":"PASS"}\n' >"$output_a"
  printf '<testsuite tests="1"/>\n' >"$output_b"
  printf 'bound tree\n' >"$output_c/member.txt"
  write_pass_record "$record" "$command_sha" "$log" "$output_a|$output_b|$output_c"
  validate_pass_record "$record" "$command_sha" || die "self-test rejected a genuine bound PASS"
  printf 'tampered\n' >>"$log"
  if validate_pass_record "$record" "$command_sha"; then
    die "self-test accepted tampered evidence"
  fi
  printf 'manual PASS\n' >"$log"
  printf 'manual tree change\n' >>"$output_c/member.txt"
  if validate_pass_record "$record" "$command_sha"; then
    die "self-test accepted tampered directory output"
  fi
  forbidden="$(printf '%s%s|%s%s|%s%s|%s%s|%s%s|%s%s|%s%s' \
    create_salary_ export_operation reserve_ salary SalaryExports Service \
    enqueue_salary_ export /salarii/ exports finalize_ scenario save_final_ targets)"
  if sed '/^self_test()/,/^}/d' "$0" | grep -Eq "$forbidden"; then
    die "self-test found a protected operation in the local gate"
  fi
  printf 'local quality gate self-test PASS: restart binding, tamper and protected-operation guards\n'
}

internal_secret_scan() {
  local output="$1" raw
  [[ "$output" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe secret evidence path"
  [[ ! -e "$output" || ( -f "$output" && ! -L "$output" ) ]] || die "unsafe secret evidence target"
  mkdir -p "$(dirname "$output")"
  raw="${output%.json}.raw.json"
  mapfile -d '' tracked_files < <(
    git -C "$ROOT" ls-files -z -- . \
      ':(exclude).secrets.baseline' \
      ':(exclude).bandit-baseline.json' \
      ':(exclude)backend/db/migrations/manifest.json' \
      ':(exclude).agent/contract-lock.json' \
      ':(exclude)docs/contracts/ai-governance-golden-v1.json' \
      ':(exclude)docs/contracts/business-golden-v2.json' \
      ':(exclude)docs/contracts/query-parameter-policy-v1.json' \
      ':(exclude)scripts/frontend-critical-coverage.json' \
      ':(exclude)scripts/python-complexity-contract-v1.json' \
      ':(exclude)scripts/release-a-source-contract-v1.json' \
      ':(exclude)scripts/release-b-authority-contract-v1.json' \
      ':(exclude)scripts/check_release_a_candidate.py' \
      ':(exclude)scripts/verify_promtool_cache.sh' \
      ':(exclude)backend/scripts/run_outbox_slo_workload.py' \
      ':(exclude)scripts/run_outbox_slo_gate.py' \
      ':(exclude)scripts/run_structural_characterization.sh' \
      ':(exclude)scripts/structural-characterization-baseline-v1.json' \
      ':(exclude)backend/scripts/run_retail_scale_profile.py' \
      ':(exclude)scripts/run_retail_scale_gate.sh' \
      ':(exclude)scripts/run_local_quality_gate.sh' \
      ':(exclude)scripts/verify_deployed_release.sh' \
      ':(exclude)ops/build-retail-release-artifact.sh' \
      ':(exclude)backend/tests/test_release_contract_tooling_security.py' \
      ':(exclude)scripts/target-mutation-contract-v2.json' \
      ':(exclude)scripts/run_release_a_schema_gate.sh' \
      ':(exclude)scripts/run_real_e2e.sh' \
      ':(exclude)backend/tests/test_prometheus_topology.py' \
      ':(exclude)ops/systemd/unihub-backend.service'
  )
  [[ "${#tracked_files[@]}" -gt 0 ]] || die "tracked secret scan inventory is empty"
  "$PYTHON" -B -I -m detect_secrets.pre_commit_hook \
    --baseline "$ROOT/.secrets.baseline" "${tracked_files[@]}"
  "$PYTHON" -B -I -m detect_secrets scan \
    --disable-plugin HexHighEntropyString \
    --disable-plugin Base64HighEntropyString \
    "$ROOT/.agent/contract-lock.json" \
    "$ROOT/docs/contracts/ai-governance-golden-v1.json" \
    "$ROOT/docs/contracts/business-golden-v2.json" \
    "$ROOT/docs/contracts/query-parameter-policy-v1.json" \
    "$ROOT/scripts/frontend-critical-coverage.json" \
    "$ROOT/scripts/python-complexity-contract-v1.json" \
    "$ROOT/scripts/release-a-source-contract-v1.json" \
    "$ROOT/scripts/release-b-authority-contract-v1.json" \
    "$ROOT/scripts/check_release_a_candidate.py" \
    "$ROOT/scripts/verify_promtool_cache.sh" \
    "$ROOT/backend/scripts/run_outbox_slo_workload.py" \
    "$ROOT/scripts/run_outbox_slo_gate.py" \
    "$ROOT/scripts/run_structural_characterization.sh" \
    "$ROOT/scripts/structural-characterization-baseline-v1.json" \
    "$ROOT/backend/scripts/run_retail_scale_profile.py" \
    "$ROOT/scripts/run_retail_scale_gate.sh" \
    "$ROOT/scripts/run_local_quality_gate.sh" \
    "$ROOT/scripts/verify_deployed_release.sh" \
    "$ROOT/ops/build-retail-release-artifact.sh" \
    "$ROOT/backend/tests/test_release_contract_tooling_security.py" \
    "$ROOT/scripts/target-mutation-contract-v2.json" \
    "$ROOT/scripts/run_release_a_schema_gate.sh" \
    "$ROOT/scripts/run_real_e2e.sh" >"$raw"
  "$PYTHON" -B -I - "$raw" "$output" "${#tracked_files[@]}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

raw_path, output_path = map(Path, sys.argv[1:3])
tracked_count = int(sys.argv[3])
scan = json.loads(raw_path.read_text(encoding="utf-8"))
finding_count = sum(len(items) for items in scan.get("results", {}).values())
if finding_count:
    raise SystemExit(f"credential-shaped findings in immutable files: {finding_count}")
plugins = sorted(scan.get("plugins_used", []), key=lambda item: str(item))
payload = {
    "schema_version": 1,
    "result": "PASS",
    "tracked_file_count": tracked_count,
    "immutable_finding_count": finding_count,
    "active_plugin_count": len(plugins),
    "raw_scan_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
}

output_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
}

internal_python_lock() {
  local output="$1"
  [[ "$output" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe Python-lock evidence path"
  [[ ! -e "$output" || ( -f "$output" && ! -L "$output" ) ]] \
    || die "unsafe Python-lock evidence target"
  mkdir -p "$(dirname "$output")"
  "$PYTHON_BASE" -I -S - \
    "$ROOT/backend/venv/lib/python3.12/site-packages" \
    "$ROOT/backend/venv/pyvenv.cfg" \
    "$ROOT/backend/requirements-dev.lock" "$output" \
    "$EXPECTED_SYSTEM_SITECUSTOMIZE_SHA256" \
    "$EXPECTED_SITE_PACKAGES_SHA256" <<'PY'
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path, PurePosixPath
import re
import sys

site_packages = Path(sys.argv[1])
venv_config = Path(sys.argv[2])
lock_path, output_path = map(Path, sys.argv[3:5])
expected_sitecustomize = sys.argv[5]
expected_site_packages = sys.argv[6]
if not site_packages.is_dir() or site_packages.is_symlink():
    raise SystemExit("unsafe backend site-packages")
if not venv_config.is_file() or venv_config.is_symlink():
    raise SystemExit("unsafe backend pyvenv.cfg")
config = {
    key.strip().lower(): value.strip().lower()
    for line in venv_config.read_text(encoding="utf-8").splitlines()
    if "=" in line
    for key, value in (line.split("=", 1),)
}

if config.get("include-system-site-packages") != "false":
    raise SystemExit("backend venv must exclude system site-packages")
if (
    config.get("home") != "/usr/bin"
    or config.get("version") != "3.12.3"
    or config.get("executable") != "/usr/bin/python3.12"
    or config.get("command")
    != "/usr/bin/python3.12 -m venv /opt/mobiup/unihub-retail/backend/venv"
):
    raise SystemExit("backend pyvenv.cfg interpreter identity mismatch")
system_sitecustomize = Path("/usr/lib/python3.12/sitecustomize.py")
if (
    not system_sitecustomize.is_file()
    or system_sitecustomize.resolve() != Path("/etc/python3.12/sitecustomize.py")
    or hashlib.sha256(system_sitecustomize.read_bytes()).hexdigest()
    != expected_sitecustomize
):
    raise SystemExit("system sitecustomize identity mismatch")
sys.path.insert(0, str(site_packages))
canonical = lambda value: re.sub(r"[-_.]+", "-", value).lower()
expected = {}
for line in lock_path.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;\\]+)", line)
    if match:
        expected[canonical(match.group(1))] = match.group(2)
installed = {
    canonical(dist.metadata["Name"]): dist
    for dist in importlib.metadata.distributions()
    if dist.metadata.get("Name")
}
bootstrap = {"pip", "setuptools", "wheel"}
versions = {name: dist.version for name, dist in installed.items()}
missing = sorted(set(expected) - set(installed))
mismatched = sorted(
    [name, version, versions.get(name)]
    for name, version in expected.items()
    if versions.get(name) != version
)
extra = sorted(set(installed) - set(expected) - bootstrap)
record_failures = []
verified_files = 0
verified_entries = []
claimed_files = set()
def is_canonical_venv_bin_pyc(value):
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) == 6
        and path.parts[:5] == ("..", "..", "..", "bin", "__pycache__")
        and path.suffix == ".pyc"
    )
def is_canonical_generated_pyc(value):
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and len(path.parts) >= 2
        and path.parts[-2] == "__pycache__"
        and path.suffix == ".pyc"
        and (".." not in path.parts or is_canonical_venv_bin_pyc(value))
    )
venv_bin = site_packages.parents[2] / "bin"
for name in sorted(installed):
    dist = installed.get(name)
    if dist is None:
        continue
    for file in dist.files or ():
        target = Path(dist.locate_file(file))
        try:
            resolved = target.resolve()
            in_site_packages = resolved.is_relative_to(site_packages.resolve())
        except (OSError, ValueError):
            record_failures.append(f"{name}:{file}:unsafe_path")
            continue
        if is_canonical_generated_pyc(str(file)):
            if not in_site_packages and not (
                is_canonical_venv_bin_pyc(str(file))
                and resolved.is_relative_to(venv_bin.resolve())
            ):
                record_failures.append(f"{name}:{file}:unsafe_path")
            continue
        if in_site_packages:
            claimed_files.add(resolved)
        if not target.is_file() or target.is_symlink():
            record_failures.append(f"{name}:{file}:missing_or_unsafe")
            continue
        if file.hash is None:
            file_path = Path(str(file))
            if file_path.name != "RECORD" and file_path.suffix != ".pyc":
                record_failures.append(f"{name}:{file}:unhashed")
            continue
        if file.hash.mode != "sha256":
            record_failures.append(f"{name}:{file}:unsupported_hash")
            continue
        actual = base64.urlsafe_b64encode(
            hashlib.sha256(target.read_bytes()).digest()
        ).decode().rstrip("=")
        if actual != file.hash.value:
            record_failures.append(f"{name}:{file}:hash_mismatch")
        verified_entries.append([name, str(file), actual])
        verified_files += 1
venv_root = site_packages.parents[2]
pyc_files = sorted(
    str(path.relative_to(venv_root))
    for path in venv_root.rglob("*.pyc")
    if path.is_file()
)
unowned_files = sorted(
    str(path.relative_to(site_packages))
    for path in site_packages.rglob("*")
    if path.is_file()
    and not path.is_symlink()
    and path.suffix != ".pyc"
    and path.resolve() not in claimed_files
)
unsafe_symlinks = sorted(
    str(path.relative_to(site_packages))
    for path in site_packages.rglob("*")
    if path.is_symlink()
)
def stable_file_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.name != "RECORD":
        return payload
    lines = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if len(fields) != 3:
            raise SystemExit("Python RECORD row must contain exactly three fields")
        if is_canonical_generated_pyc(fields[0]):
            continue
        if fields[0].startswith("../../../bin/"):
            fields[1:] = ["<venv-script>", "<size>"]
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()

tree_entries = [
    [str(path.relative_to(site_packages)), hashlib.sha256(stable_file_bytes(path)).hexdigest()]
    for path in sorted(site_packages.rglob("*"))
    if path.is_file()
    and not path.is_symlink()
    and path.suffix != ".pyc"
]
site_packages_sha256 = hashlib.sha256(
    json.dumps(tree_entries, separators=(",", ":")).encode()
).hexdigest()
if (
    missing
    or mismatched
    or extra
    or record_failures
    or unowned_files
    or unsafe_symlinks
    or pyc_files
    or site_packages_sha256 != expected_site_packages
):
    raise SystemExit(
        json.dumps(
            {
                "missing": missing,
                "mismatched": mismatched,
                "extra": extra,
                "record_failures": record_failures[:20],
                "unowned_files": unowned_files[:20],
                "unsafe_symlinks": unsafe_symlinks[:20],
                "pyc_files": pyc_files[:20],
                "site_packages_sha256": site_packages_sha256,
            },
            sort_keys=True,
        )
    )
payload = {
    "schema_version": 1,
    "result": "PASS",
    "python": {
        "resolved_path": "/usr/bin/python3.12",
        "sha256": hashlib.sha256(Path("/usr/bin/python3.12").read_bytes()).hexdigest(),
        "system_sitecustomize_sha256": expected_sitecustomize,
        "pyvenv_config_sha256": hashlib.sha256(venv_config.read_bytes()).hexdigest(),
    },
    "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    "locked_distribution_count": len(expected),
    "bootstrap_distributions": sorted(set(installed) & bootstrap),
    "verified_record_file_count": verified_files,
    "site_packages_file_count": len(tree_entries),
    "site_packages_sha256": site_packages_sha256,
    "environment_sha256": hashlib.sha256(
        json.dumps(
            {
                "distributions": sorted((name, versions[name]) for name in installed),
                "record_files": verified_entries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest(),
}
output_path.write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
}

internal_python_cache_clean() {
  local output="$1"
  [[ "$output" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe Python-cache evidence path"
  [[ ! -e "$output" || ( -f "$output" && ! -L "$output" ) ]] \
    || die "unsafe Python-cache evidence target"
  mkdir -p "$(dirname "$output")"
  "$PYTHON_BASE" -I -S - \
    "$ROOT/backend/venv" "$output" <<'PY'
import json
import os
from pathlib import Path
import stat
import sys

root = Path(sys.argv[1])
output = Path(sys.argv[2])
if not root.is_dir() or root.is_symlink():
    raise SystemExit("unsafe backend site-packages")
removed = 0
cache_directories: list[Path] = []
for current, directories, files in os.walk(root, topdown=True, followlinks=False):
    base = Path(current)
    directories[:] = [
        name for name in directories if not (base / name).is_symlink()
    ]
    cache_directories.extend(
        base / name for name in directories if name == "__pycache__"
    )
    for name in files:
        path = base / name
        if path.suffix != ".pyc":
            continue
        mode = os.lstat(path).st_mode
        if not stat.S_ISREG(mode):
            raise SystemExit(f"unsafe bytecode cache entry: {path.relative_to(root)}")
        path.unlink()
        removed += 1
for path in sorted(cache_directories, key=lambda item: len(item.parts), reverse=True):
    try:
        path.rmdir()
    except OSError:
        pass
payload = {
    "schema_version": 1,
    "result": "PASS",
    "removed_pyc_count": removed,
    "pyc_remaining": sum(1 for path in root.rglob("*.pyc") if path.is_file()),
}
if payload["pyc_remaining"]:
    raise SystemExit("bytecode cache cleanup incomplete")
output.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
PY
}

internal_operational() {
  local output="$1" temp systemd_root prom_root cache_dir archive promtool
  local version="3.11.3"
  local archive_sha="9479af67673316278958cda1f39b88a09f8921084e039c65acca060d0447bb38"
  [[ "$output" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe operational evidence path"
  [[ ! -e "$output" || ( -f "$output" && ! -L "$output" ) ]] || die "unsafe operational evidence target"
  mkdir -p "$(dirname "$output")"
  INTERNAL_TEMP="$(mktemp -d)"
  temp="$INTERNAL_TEMP"
  systemd_root="$temp/systemd"
  prom_root="$temp/prometheus"
  cache_dir="${UNIHUB_PROMETHEUS_CACHE_DIR:-/opt/Mobiup/.cache/unihub-prometheus}"
  archive="$cache_dir/prometheus-${version}.linux-amd64.tar.gz"
  promtool="$prom_root/promtool"
  [[ -f "$archive" && ! -L "$archive" ]] || die "pre-provisioned Prometheus archive is required"
  printf '%s  %s\n' "$archive_sha" "$archive" | sha256sum --check --status - \
    || die "Prometheus archive digest mismatch"
  mkdir -p \
    "$systemd_root/usr/lib/systemd" \
    "$systemd_root/etc/systemd/system" \
    "$systemd_root/usr/bin" \
    "$systemd_root/opt/Mobiup/unihub-retail/backend/venv/bin" \
    "$systemd_root/opt/Mobiup/ops/prometheus" \
    "$prom_root/scrape.d"
  cp -a /usr/lib/systemd/system "$systemd_root/usr/lib/systemd/"
  cp \
    "$ROOT/ops/systemd/unihub-backend.service" \
    "$ROOT/unihub-worker.service" \
    "$ROOT/ops/systemd/unihub-import-worker.service" \
    "$ROOT/ops/systemd/unihub-grile-worker.service" \
    "$ROOT/ops/systemd/unihub-export-worker.service" \
    "$ROOT/ops/systemd/unihub-salary-export-worker.service" \
    "$ROOT/ops/systemd/unihub-legacy-worker.service" \
    "$ROOT/ops/systemd/unihub-retail-migrate.service" \
    "$systemd_root/etc/systemd/system/"
  printf '[Service]\nType=oneshot\nExecStart=/usr/bin/true\n' \
    >"$systemd_root/etc/systemd/system/docker.service"
  cp "$systemd_root/etc/systemd/system/docker.service" \
    "$systemd_root/etc/systemd/system/mobiup-dwh-postgres.service"
  touch \
    "$systemd_root/opt/Mobiup/unihub-retail/.env" \
    "$systemd_root/opt/Mobiup/unihub-retail/.env.worker" \
    "$systemd_root/opt/Mobiup/unihub-retail/.env.import-worker" \
    "$systemd_root/opt/Mobiup/unihub-retail/.env.salary-export-worker" \
    "$systemd_root/opt/Mobiup/unihub-retail/.env.migrations" \
    "$systemd_root/opt/Mobiup/ops/prometheus/unihub-retail-network.env"
  cp /usr/bin/true "$systemd_root/usr/bin/true"
  cp /usr/bin/false "$systemd_root/usr/bin/false"
  cp /usr/bin/timeout "$systemd_root/usr/bin/timeout"
  cp /usr/bin/true "$systemd_root/opt/Mobiup/unihub-retail/backend/venv/bin/python"
  cp /usr/bin/true "$systemd_root/opt/Mobiup/unihub-retail/backend/venv/bin/python3"
  systemd-analyze verify --root="$systemd_root" \
    "$systemd_root/etc/systemd/system/unihub-backend.service" \
    "$systemd_root/etc/systemd/system/unihub-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-import-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-grile-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-export-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-salary-export-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-legacy-worker.service" \
    "$systemd_root/etc/systemd/system/unihub-retail-migrate.service"
  visudo -cf "$ROOT/ops/unihub-deploy.sudoers"
  grep -Fq '/usr/local/sbin/unihub-deploy-lock acquire *' "$ROOT/ops/unihub-deploy.sudoers"
  grep -Fq '/usr/local/sbin/unihub-deploy-lock release *' "$ROOT/ops/unihub-deploy.sudoers"
  "$ROOT/scripts/verify_promtool_cache.sh" prepare \
    --version "$version" --sha256 "$archive_sha" --cache-dir "$cache_dir" \
    --destination "$promtool" --evidence "$temp/promtool-cache.json"
  "$PYTHON" -B -I - "$temp/promtool-cache.json" <<'PY'
import json
from pathlib import Path
import sys

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("result") != "PASS" or value.get("source") != "cache" or value.get("download_count") != 0:
    raise SystemExit("operational gate did not use the pre-provisioned Promtool archive")
PY
  "$promtool" check rules "$ROOT/ops/observability/retail-slo-rules.yml"
  "$PYTHON" -B -I "$ROOT/scripts/check_prometheus_contract.py"
  (
    cd "$ROOT/ops/observability"
    "$promtool" test rules retail-slo-rules.test.yml
  )
  sed 's/__PROMETHEUS_DOCKER_GATEWAY__/172.23.0.1/g' \
    "$ROOT/ops/observability/retail-process-scrape.yml" \
    >"$prom_root/scrape.d/unihub-retail.yml"
  printf '%s\n' \
    'global:' '  scrape_interval: 15s' 'scrape_config_files:' \
    "  - $prom_root/scrape.d/*.yml" >"$prom_root/prometheus.yml"
  "$promtool" check config "$prom_root/prometheus.yml"
  [[ "$(grep -Fc '172.23.0.1:' "$prom_root/scrape.d/unihub-retail.yml")" -eq 6 ]]
  if grep -Eq '__PROMETHEUS_DOCKER_GATEWAY__|0\.0\.0\.0|127\.0\.0\.1' \
    "$prom_root/scrape.d/unihub-retail.yml"; then
    return 1
  fi
  "$PYTHON" -B -I - "$temp/promtool-cache.json" "$output" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

cache_path, output_path = map(Path, sys.argv[1:])
payload = {
    "schema_version": 1,
    "result": "PASS",
    "systemd_units": 8,
    "prometheus_targets": 6,
    "promtool_cache_sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
    "network_download_count": 0,
}
output_path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
  rm -rf -- "$temp"
  INTERNAL_TEMP=""
}

verify_python_identity

if [[ -n "$INTERNAL_MODE" ]]; then
  [[ "$SELF_TEST" == "0" && -n "$INTERNAL_EVIDENCE" ]] || die "invalid internal mode"
  case "$INTERNAL_MODE" in
    secret) internal_secret_scan "$INTERNAL_EVIDENCE" ;;
    operational) internal_operational "$INTERNAL_EVIDENCE" ;;
    python-cache-clean) internal_python_cache_clean "$INTERNAL_EVIDENCE" ;;
    python-lock) internal_python_lock "$INTERNAL_EVIDENCE" ;;
    *) die "unknown internal mode" ;;
  esac
  exit 0
fi

if [[ "$SELF_TEST" == "1" ]]; then
  self_test
  exit 0
fi

[[ "$SEQUENTIAL" == "1" ]] || die "--sequential is mandatory"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "--sha must be exact lowercase 40-char hex"
[[ "$RELEASE_A_SHA" =~ ^[0-9a-f]{40}$ ]] || die "Release-A SHA is required"
[[ -n "$EVIDENCE" && -n "$RELEASE_A_ARTIFACT" ]] || die "evidence and Release-A artifact are required"
[[ "$EVIDENCE" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe evidence path"
[[ "$RELEASE_A_ARTIFACT" =~ ^[A-Za-z0-9_./-]+$ ]] || die "unsafe Release-A artifact path"
[[ "$(hostname)" == "dell-standby" ]] || die "integrated local gate is locked to dell-standby"
verify_python_identity
[[ -d "$ROOT/node_modules" ]] || die "offline node_modules is required"
NODE="/opt/codex-desktop/resources/node-runtime/bin/node"
NPM_CLI="/opt/codex-desktop/resources/node-runtime/lib/node_modules/npm/bin/npm-cli.js"
[[ -f "$NODE" && -x "$NODE" && -f "$NPM_CLI" ]] || die "Node.js/npm are required"
[[ "$NODE" != "$ROOT"/* && "$NPM_CLI" != "$ROOT"/* ]] \
  || die "Node.js/npm must not resolve from the candidate tree"
[[ "$NODE" != *[[:space:]]* && "$NPM_CLI" != *[[:space:]]* ]] \
  || die "unsafe Node.js/npm path"
[[ "$($NODE --version)" =~ ^v22\.[0-9]+\.[0-9]+$ ]] || die "Node.js 22.x is required"
[[ "$($NODE "$NPM_CLI" --version)" =~ ^10\.[0-9]+\.[0-9]+$ ]] || die "npm 10.x is required"
[[ "$(sha256sum "$NODE" | awk '{print $1}')" == "$EXPECTED_NODE_SHA256" \
  && "$(sha256sum "$NPM_CLI" | awk '{print $1}')" == "$EXPECTED_NPM_CLI_SHA256" ]] \
  || die "Node.js/npm executable digest mismatch"
[[ "$(git -C "$ROOT" rev-parse HEAD)" == "$SHA" ]] || die "--sha differs from HEAD"
[[ "$(git -C "$ROOT" rev-parse "$RELEASE_A_SHA")" == "$RELEASE_A_SHA" ]] || die "Release-A SHA is not an exact local commit"
git -C "$ROOT" merge-base --is-ancestor "$RELEASE_A_SHA" "$SHA" || die "Release-A SHA is not an ancestor"
[[ -z "$(git -C "$ROOT" status --porcelain=v1 --untracked-files=all)" ]] || die "worktree must be clean"
CURRENT_TREE="$(git -C "$ROOT" rev-parse 'HEAD^{tree}')"
[[ -d "$RELEASE_A_ARTIFACT" && ! -L "$RELEASE_A_ARTIFACT" ]] || die "Release-A artifact directory is unsafe"
RELEASE_A_ARTIFACT="$(cd "$RELEASE_A_ARTIFACT" && pwd)"

cosign_path="$(command -v cosign || true)"
[[ -x "$cosign_path" ]] || die "pre-provisioned pinned cosign is required"
[[ "$(sha256sum "$cosign_path" | awk '{print $1}')" == "$EXPECTED_COSIGN_SHA256" ]] || die "cosign digest mismatch"
"$cosign_path" version 2>&1 | grep -Eq '^GitVersion:[[:space:]]+v3\.1\.3[[:space:]]*$' || die "cosign version mismatch"

[[ ! -e "$EVIDENCE" || ( -d "$EVIDENCE" && ! -L "$EVIDENCE" ) ]] || die "evidence directory is unsafe"
mkdir -p "$EVIDENCE/steps"
[[ -d "$EVIDENCE/steps" && ! -L "$EVIDENCE/steps" ]] || die "step evidence directory is unsafe"
EVIDENCE="$(cd "$EVIDENCE" && pwd)"
STEPS_DIR="$EVIDENCE/steps"
INPUT_SHA256="$({
  printf '%s\n%s\n' "$SHA" "$CURRENT_TREE"
  sha256sum \
    scripts/release-b-authority-contract-v1.json \
    .agent/contract-lock.json \
    package-lock.json \
    backend/requirements.lock \
    backend/requirements-dev.lock
  sha256sum "$PYTHON_BASE" "$NODE" "$NPM_CLI"
} | sha256_text)"

A_SCHEMA="$RELEASE_A_ARTIFACT/schema-gate.json"
run_step node-dependencies "npm_config_offline=true $NODE $NPM_CLI ci --offline --ignore-scripts --include=dev"
run_step python-cache-preflight "scripts/run_local_quality_gate.sh --internal-python-cache-clean '$EVIDENCE/python-cache-preflight.json'" "$EVIDENCE/python-cache-preflight.json"
run_step python-dependencies "scripts/run_local_quality_gate.sh --internal-python-lock '$EVIDENCE/python-lock.json'" "$EVIDENCE/python-lock.json"
run_step authority "$PYTHON_BASE -I -S scripts/check_release_a_candidate.py --verify-main-evidence '$A_SCHEMA' --expected-sha '$RELEASE_A_SHA' --expected-candidate-sha '$SHA' --release-a-artifact-dir '$RELEASE_A_ARTIFACT' --evidence '$EVIDENCE/ac-12-release-a.json'" "$EVIDENCE/ac-12-release-a.json"
run_step python-dependency-health "$PYTHON -B -I -m pip check"
run_step vendored "$NODE scripts/verify_vendored_npm_packages.mjs"
run_step changed-complexity "$PYTHON -B -I scripts/check_changed_function_complexity.py --base '$RELEASE_A_SHA' --maximum 20"
run_step backend-suite "backend/scripts/run_tests_isolated.sh -q --tb=short --cov=. --cov-config=../.coveragerc --cov-fail-under=80 --cov-report=json:'$EVIDENCE/backend-coverage.json' --junitxml='$EVIDENCE/backend-all.xml'" "$EVIDENCE/backend-coverage.json|$EVIDENCE/backend-all.xml"
run_step backend-critical-coverage "$PYTHON -B -I backend/scripts/check_critical_coverage.py '$EVIDENCE/backend-coverage.json'"
run_step backend-changed-coverage "cd backend && '$PYTHON' -B -I ../scripts/check_changed_line_coverage.py --base '$RELEASE_A_SHA' --backend-json '$EVIDENCE/backend-coverage.json' --minimum 80"
run_step mypy "cd backend && '$PYTHON' -B -I -m mypy . --ignore-missing-imports --explicit-package-bases"
run_step mutation "$PYTHON -B -I scripts/run_targeted_mutation_tests.py"
run_step ac01-target "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/run_target_allocator_contract.py --contract scripts/target-mutation-contract-v2.json --seed 20260812 --evidence '$EVIDENCE/ac-01.json'" "$EVIDENCE/ac-01.json"
run_step ac03-backtest "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' backend/scripts/run_ai_forecast_backtest.py --contract-fixture docs/contracts/business-golden-v2.json --governance-fixture docs/contracts/ai-governance-golden-v1.json --candidate-only --seed 20260812 --evidence '$EVIDENCE/ac-03.json'" "$EVIDENCE/ac-03.json"
run_step ac05-query "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/check_query_parameter_contract.py --policy docs/contracts/query-parameter-policy-v1.json --evidence '$EVIDENCE/ac-05.json'" "$EVIDENCE/ac-05.json"
run_step ac06-docs "$PYTHON -B -I scripts/check_docs_contract.py --catalog docs/catalog.json --release docs/releases/current.json --evidence '$EVIDENCE/ac-06.json'" "$EVIDENCE/ac-06.json"
run_step ac07-golden "$PYTHON -B -I scripts/check_business_golden.py --contract docs/contracts/business-golden-v2.json --evidence '$EVIDENCE/ac-07.json'" "$EVIDENCE/ac-07.json"
run_step ac10-structural "UNIHUB_TEST_DATABASE=1 scripts/run_structural_characterization.sh --max-seconds 16.7 --evidence '$EVIDENCE/ac-10.json'" "$EVIDENCE/ac-10.json"
run_step ac10-line-ratchet "$PYTHON -B -I scripts/check_complexity_ratchet.py"
run_step ac10-ast "$PYTHON -B -I scripts/check_python_complexity_contract.py --contract scripts/python-complexity-contract-v1.json --evidence '$EVIDENCE/ac-10-complexity.json'" "$EVIDENCE/ac-10-complexity.json"
run_step ac10-architecture "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/check_backend_architecture.py"
run_step ac12-outbox "UNIHUB_TEST_DATABASE=1 $PYTHON -B -I scripts/run_outbox_slo_gate.py --seed 20260812 --warmup 500 --events 10000 --rate 20 --claimers 4 --batch-size 50 --handlers 8 --evidence '$EVIDENCE/ac-12.json'" "$EVIDENCE/ac-12.json"
run_step ac13-import-artifacts "$PYTHON -B -I -m pytest -q backend/tests/test_sales_artifact_lifecycle.py::test_retain_never_chmods_an_artifact_published_by_the_web_identity backend/tests/test_sales_artifact_lifecycle.py::test_worker_retry_repairs_post_move_db_failure_without_restart backend/tests/test_imports_coverage.py::test_publish_promo_generation_owns_deduplicated_rule_masters_and_fails_closed_on_tamper backend/tests/test_imports_coverage.py::test_publish_promo_generation_identity_binds_rule_master_bytes backend/tests/test_promo_generation_migration.py::test_migration_upgrades_active_v2_with_unowned_rule_master_atomically_and_idempotently backend/tests/test_promo_generation_migration.py::test_migration_unowned_v2_upgrade_fault_preserves_active_pointer --junitxml='$EVIDENCE/ac-13-import-artifacts.xml'" "$EVIDENCE/ac-13-import-artifacts.xml"
run_step ac13-scale "UNIHUB_TEST_DATABASE=1 scripts/run_retail_scale_gate.sh --seed 20260812 --profiles 2x,5x --exact-max-upload 33554432 --evidence '$EVIDENCE/ac-13'" "$EVIDENCE/ac-13/ac-13-scale-evidence.json"
run_step ac14-governance "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/check_ai_forecast_governance.py --contract docs/contracts/business-golden-v2.json --governance-fixture docs/contracts/ai-governance-golden-v1.json --evidence '$EVIDENCE/ac-14.json'" "$EVIDENCE/ac-14.json"

run_step frontend-coverage "$NODE node_modules/vitest/vitest.mjs run --coverage.enabled --reporter=default --reporter=junit --outputFile.junit='$EVIDENCE/ac-11.xml'" "coverage|$EVIDENCE/ac-11.xml"
run_step ac08-coverage "$NODE scripts/check_frontend_critical_coverage.mjs --manifest scripts/frontend-critical-coverage.json --coverage coverage/coverage-final.json --evidence '$EVIDENCE/ac-08.json'" "$EVIDENCE/ac-08.json"
run_step frontend-changed-coverage "$PYTHON -B -I scripts/check_changed_line_coverage.py --base '$RELEASE_A_SHA' --frontend-lcov coverage/frontend/lcov.info --minimum 80"
run_step typecheck "$NODE node_modules/@typescript/old/bin/tsc --noEmit"
run_step lint "$NODE node_modules/eslint/bin/eslint.js . --max-warnings=0"
run_step ts-complexity "$NODE scripts/check_ts_function_complexity.cjs"
run_step ac11-structure "$NODE scripts/check_frontend_structure_contract.mjs --manifest scripts/frontend-critical-coverage.json --evidence '$EVIDENCE/ac-11.json'" "$EVIDENCE/ac-11.json"
run_step build "VITE_FRONTEND_GLITCHTIP_DSN= $NODE node_modules/vite/bin/vite.js build" "dist"
run_step bundle-budget "$NODE scripts/check_bundle_budget.mjs"
run_step browser-matrix "$NODE node_modules/@playwright/test/cli.js test --config=playwright.browser-smoke.config.ts"
run_step pwa-lifecycle "PWA_BASE_SHA='$RELEASE_A_SHA' scripts/run_pwa_release_lifecycle.sh"
run_step integration-restore "REAL_E2E_SKIP_BUILD=1 scripts/run_real_e2e.sh" "test-results/real-e2e-restore-drill.json|test-results/real-e2e-restore-drill.json.sha256"

run_step openapi "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/generate_retail_contract.py --check"
run_step dependency-policy "$NODE scripts/check_dependency_policy.mjs"
run_step env-contract "$PYTHON -B -I -c 'import runpy,sys; sys.path.insert(0,\"backend\"); path=sys.argv.pop(1); runpy.run_path(path,run_name=\"__main__\")' scripts/check_env_contract.py"
run_step secrets "scripts/run_local_quality_gate.sh --internal-secret-scan '$EVIDENCE/security-secret-scan.json'" "$EVIDENCE/security-secret-scan.json"
run_step shellcheck "scripts/run_shellcheck.sh"
run_step operational "scripts/run_local_quality_gate.sh --internal-operational '$EVIDENCE/operational.json'" "$EVIDENCE/operational.json"
run_step migration-manifest "cd backend && '$PYTHON' -B -I -c 'import sys; sys.path.insert(0,\".\"); from db.migration_runner import load_migration_manifest, verify_migration_files; verify_migration_files(load_migration_manifest())'"
run_step bandit-waivers "$PYTHON -B -I scripts/check_bandit_waivers.py"
run_step bandit "$PYTHON -B -I -m bandit -r backend -x backend/tests,backend/venv -ll -ii -q -b .bandit-baseline.json"
run_step deploy-sandbox "ops/test-deploy-retail-artifact.sh"

run_step python-dependencies-final "scripts/run_local_quality_gate.sh --internal-python-lock '$EVIDENCE/python-lock-final.json'" "$EVIDENCE/python-lock-final.json"

"$PYTHON_BASE" -I -S - "$STEPS_DIR" "$EVIDENCE/local-quality-gate.json" "$SHA" "$CURRENT_TREE" "$INPUT_SHA256" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

steps_dir, output, sha, tree, input_sha = sys.argv[1:]
records = []
for path in sorted(Path(steps_dir).glob("*.json")):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("result") != "PASS" or payload.get("sha") != sha or payload.get("tree") != tree:
        raise SystemExit(f"invalid final step record: {path}")
    records.append({"id": path.stem, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
if len(records) < 30:
    raise SystemExit("integrated gate step inventory is incomplete")
payload = {
    "schema_version": 1,
    "result": "PASS",
    "sha": sha,
    "tree": tree,
    "input_sha256": input_sha,
    "sequential": True,
    "network_dependency_install": False,
    "salary_export_executed": False,
    "protected_live_promotion_executed": False,
    "steps": records,
}
Path(output).write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY

printf 'Local integrated quality gate PASS: %s (%s)\n' "$SHA" "$EVIDENCE/local-quality-gate.json"
