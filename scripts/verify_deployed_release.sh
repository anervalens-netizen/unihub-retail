#!/usr/bin/bash -p
# Read-only Release-B production acceptance authority (AC-17).
set -Eeuo pipefail
umask 077
unset BASH_ENV ENV CDPATH GLOBIGNORE PYTHONSTARTUP PYTHONINSPECT || true
export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 PYTHONDONTWRITEBYTECODE=1
export GH_HOST=github.com
unset PYTHONHOME PYTHONPATH MYPYPATH MYPY_CONFIG_FILE

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
PYTHON_BASE="/usr/bin/python3.12"
PYTHON_BASE_SHA256="1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
SYSTEM_SITECUSTOMIZE="/usr/lib/python3.12/sitecustomize.py"
SYSTEM_SITECUSTOMIZE_RESOLVED="/etc/python3.12/sitecustomize.py"
SYSTEM_SITECUSTOMIZE_SHA256="43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e"
PYTHON_RUNTIME_TREE_PROPERTY="unihub:python-runtime:site-packages-tree-sha256:v1"
PG_RESTORE="/usr/bin/pg_restore"
PG_RESTORE_SHA256="fc00112585bd75eb9eb6fcd11ca4cf7222acf10259a1f21eea4889536dee640a"
PG_RESTORE_VERSION="pg_restore (PostgreSQL) 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)"
SQLITE3="/usr/bin/sqlite3"
SQLITE3_SHA256="a17a749643e8f5abe5f8a694fe52625c6c53c68ea8546378c4a78467c14dad1c"
SQLITE3_VERSION="3.45.1 2024-01-30 16:01:20 e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257ccalt1 (64-bit)"
GH_BIN="/usr/bin/gh"
GH_BIN_SHA256="141507c337e8b202ad398550c3b73d72f5af92e86f71665214538a81efd4c409"
BROWSER_CHROME="/home/andrei/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"
BROWSER_CHROME_SHA256="2d18db9d8608b052b6a552ee00ec1e830f93692e928b65ecc67d693bd33fe801"
BROWSER_CHROME_VERSION="Google Chrome for Testing 149.0.7827.55"
DEPLOY_ENTRYPOINT="/opt/Mobiup/ops/scripts/deploy-retail-artifact.sh"
DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE_ROOT="/var/lib/unihub-retail-deploy/bootstrap-evidence"
DEPLOY_ENTRYPOINT_BACKUP_ROOT="/opt/Mobiup/ops/backups/retail-deploy-entrypoints"
PUBLIC_BASE="https://retail.unihub.ro"
LOCAL_BASE="http://127.0.0.1:9898"
PROMETHEUS_BASE="http://127.0.0.1:9090"
LIVE_ROOT="/opt/Mobiup/unihub-retail"
RUNTIME_RELEASE_BASE="/var/lib/unihub-retail-deploy/runtime-releases"
BACKUP_ROOT="/opt/Mobiup/ops/backups/retail-deploy"
BACKUP_DATA_ROOT="/opt/Mobiup/ops/backups"
BACKUP_STATUS="/opt/Mobiup/ops/backups/manifests/last-run.env"
MIGRATION_ENV="$LIVE_ROOT/.env.migrations"
GITHUB_REPOSITORY="anervalens-netizen/unihub-retail"
GITHUB_ORIGIN_URL="https://github.com/anervalens-netizen/unihub-retail.git"
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

verify_cookie_scope() {
  local manager_file="$1" forbidden_file="$2" output="$3"
  "$PYTHON_BASE" -I -S - "$manager_file" "$forbidden_file" "$PUBLIC_BASE" "$output" <<'PY'
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

manager_path, forbidden_path, base_url, output_path = sys.argv[1:]
target = urlsplit(base_url)
host = (target.hostname or "").lower()
request_path = target.path or "/"
if target.scheme != "https" or host != "retail.unihub.ro":
    raise SystemExit("cookie verifier target is not canonical Retail HTTPS")


def valid_pair(name: str, value: str) -> bool:
    return bool(name) and not any(
        ord(char) < 0x21
        or ord(char) >= 0x7f
        or char in '()<>@,;:\\"/[]?={}'
        for char in name
    ) and not any(ord(char) < 0x20 or char == ";" for char in value)


def path_matches(cookie_path: str) -> bool:
    if not cookie_path.startswith("/"):
        return False
    if request_path == cookie_path:
        return True
    return request_path.startswith(cookie_path) and (
        cookie_path.endswith("/")
        or (
            len(request_path) > len(cookie_path)
            and request_path[len(cookie_path)] == "/"
        )
    )


def inspect(path_value: str) -> dict[str, object]:
    path = Path(path_value)
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise SystemExit(f"cookie input is empty: {path.name}")
    active: list[tuple[str, bool]] = []
    for original in raw.splitlines():
        if original.startswith("#HttpOnly_"):
            active.append((original[len("#HttpOnly_") :], True))
        elif original and not original.startswith("#"):
            active.append((original, False))
    if not active:
        raise SystemExit(f"cookie input has no active record: {path.name}")

    is_netscape = any("\t" in line for line, _http_only in active)
    if not is_netscape:
        if (
            len(active) != 1
            or len(raw.splitlines()) != 1
            or not active[0][0].lower().startswith("cookie:")
        ):
            raise SystemExit(f"raw cookie input must be one strict Cookie header: {path.name}")
        header = active[0][0].split(":", 1)[1].strip()
        pairs = [item.strip().partition("=") for item in header.split(";")]
        if not pairs or any(not separator or not valid_pair(name, value) for name, separator, value in pairs):
            raise SystemExit(f"raw cookie header is malformed: {path.name}")
        names = [name for name, _separator, _value in pairs]
        if len(names) != len(set(names)):
            raise SystemExit(f"raw cookie header contains duplicate names: {path.name}")
        return {
            "kind": "raw-header",
            "record_count": len(pairs),
            "session_count": len(pairs),
            "persistent_count": 0,
            "http_only_count": 0,
        }

    now = int(time.time())
    allowed_domains = {"retail.unihub.ro", ".retail.unihub.ro"}
    records: list[dict[str, object]] = []
    identities: set[tuple[str, str, str]] = set()
    for line, http_only in active:
        parts = line.split("\t")
        if len(parts) != 7:
            raise SystemExit(f"Netscape cookie record is malformed: {path.name}")
        domain_raw, include_raw, cookie_path, secure_raw, expiry_raw, name, value = parts
        domain = domain_raw.lower()
        if domain not in allowed_domains:
            raise SystemExit(f"non-Retail cookie record rejected: {path.name}")
        if include_raw not in {"TRUE", "FALSE"} or secure_raw not in {"TRUE", "FALSE"}:
            raise SystemExit(f"Netscape cookie flags are malformed: {path.name}")
        include_subdomains = include_raw == "TRUE"
        normalized_domain = domain.lstrip(".")
        if include_subdomains != domain.startswith("."):
            raise SystemExit(f"cookie domain flag is inconsistent: {path.name}")
        if not (
            host == normalized_domain
            or (include_subdomains and host.endswith("." + normalized_domain))
        ):
            raise SystemExit(f"cookie domain does not match Retail: {path.name}")
        if not path_matches(cookie_path):
            raise SystemExit(f"cookie path does not match Retail root: {path.name}")
        if target.scheme == "https" and secure_raw != "TRUE":
            raise SystemExit(f"Retail HTTPS cookie is not Secure: {path.name}")
        try:
            expiry = int(expiry_raw)
        except ValueError as exc:
            raise SystemExit(f"cookie expiry is malformed: {path.name}") from exc
        if expiry < 0 or (expiry != 0 and expiry <= now):
            raise SystemExit(f"cookie is expired: {path.name}")
        if not valid_pair(name, value):
            raise SystemExit(f"Netscape cookie pair is malformed: {path.name}")
        identity = (normalized_domain, cookie_path, name)
        if identity in identities:
            raise SystemExit(f"duplicate Netscape cookie identity: {path.name}")
        identities.add(identity)
        records.append({"expiry": expiry, "http_only": http_only})
    return {
        "kind": "netscape",
        "record_count": len(records),
        "session_count": sum(item["expiry"] == 0 for item in records),
        "persistent_count": sum(item["expiry"] != 0 for item in records),
        "http_only_count": sum(bool(item["http_only"]) for item in records),
    }


manager = inspect(manager_path)
forbidden = inspect(forbidden_path)
payload = {
    "schema_version": 1,
    "result": "PASS",
    "target": "https://retail.unihub.ro/",
    "manager": manager,
    "forbidden": forbidden,
    "values_recorded": False,
}
Path(output_path).write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
print(manager["kind"], forbidden["kind"])
PY
}

verify_python_runtime() {
  local output="$1" previous="${2:-}"
  local venv_root="${3:-$LIVE_ROOT/backend/venv}"
  local lock_path="${4:-$LIVE_ROOT/backend/requirements.lock}"
  local sbom_path="${5:-$B_ARTIFACT_DIR/SBOM.python.cdx.json}"
  "$PYTHON_BASE" -I -S - \
    "$venv_root" \
    "$lock_path" \
    "$sbom_path" \
    "$PYTHON_BASE_SHA256" \
    "$SYSTEM_SITECUSTOMIZE" "$SYSTEM_SITECUSTOMIZE_RESOLVED" \
    "$SYSTEM_SITECUSTOMIZE_SHA256" "$PYTHON_RUNTIME_TREE_PROPERTY" \
    "$output" "$previous" <<'PY'
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys

venv, lock_path, sbom_path = map(Path, sys.argv[1:4])
(
    expected_python_sha256,
    sitecustomize_path_value,
    sitecustomize_resolved_value,
    expected_sitecustomize_sha256,
    runtime_tree_property,
    output_path,
    previous_path,
) = sys.argv[4:]
site_packages = venv / "lib/python3.12/site-packages"
bin_dir = venv / "bin"
config_path = venv / "pyvenv.cfg"
python_path = Path("/usr/bin/python3.12")
sitecustomize_path = Path(sitecustomize_path_value)
sitecustomize_resolved = Path(sitecustomize_resolved_value)
if (
    not venv.is_dir()
    or venv.is_symlink()
    or not site_packages.is_dir()
    or site_packages.is_symlink()
    or not bin_dir.is_dir()
    or bin_dir.is_symlink()
    or not config_path.is_file()
    or config_path.is_symlink()
    or not lock_path.is_file()
    or lock_path.is_symlink()
    or not sbom_path.is_file()
    or sbom_path.is_symlink()
):
    raise SystemExit("deployed Python runtime inputs are unsafe")
if hashlib.sha256(python_path.read_bytes()).hexdigest() != expected_python_sha256:
    raise SystemExit("deployed Python base interpreter digest mismatch")
if (
    not sitecustomize_path.is_file()
    or sitecustomize_path.resolve() != sitecustomize_resolved
    or not sitecustomize_resolved.is_file()
    or sitecustomize_resolved.is_symlink()
    or hashlib.sha256(sitecustomize_path.read_bytes()).hexdigest()
    != expected_sitecustomize_sha256
):
    raise SystemExit("system sitecustomize identity mismatch")
config = {
    key.strip().lower(): value.strip()
    for line in config_path.read_text(encoding="utf-8").splitlines()
    if "=" in line
    for key, value in (line.split("=", 1),)
}
expected_config = {
    "home": "/usr/bin",
    "include-system-site-packages": "false",
    "version": "3.12.3",
    "executable": "/usr/bin/python3.12",
    "command": "/usr/bin/python3.12 -m venv /opt/Mobiup/unihub-retail/backend/venv",
}
if config != expected_config:
    raise SystemExit("deployed pyvenv.cfg identity mismatch")

expected_interpreter_links = {
    venv / "bin/python": Path("python3.12"),
    venv / "bin/python3": Path("python3.12"),
    venv / "bin/python3.12": python_path,
}
for link, target in expected_interpreter_links.items():
    if (
        not link.is_symlink()
        or link.readlink() != target
        or link.resolve(strict=True) != python_path
    ):
        raise SystemExit(f"deployed Python interpreter link is invalid: {link.name}")
if set(bin_dir.iterdir()) != set(expected_interpreter_links):
    raise SystemExit("deployed Python runtime bin inventory is not interpreter-only")

canonical = lambda value: re.sub(r"[-_.]+", "-", value).lower()
expected: dict[str, str] = {}
expected_hashes: dict[str, set[str]] = {}
current_name: str | None = None
for raw in lock_path.read_text(encoding="utf-8").splitlines():
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^ ;\\]+)", raw)
    if match:
        current_name = canonical(match.group(1))
        if current_name in expected:
            raise SystemExit("duplicate locked Python distribution")
        expected[current_name] = match.group(2)
        expected_hashes[current_name] = set()
    for digest in re.findall(r"--hash=sha256:([0-9a-f]{64})", raw):
        if current_name is None:
            raise SystemExit("orphan Python lock hash")
        expected_hashes[current_name].add(digest)
if not expected or any(not hashes for hashes in expected_hashes.values()):
    raise SystemExit("Python runtime lock inventory is incomplete")

sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
if sbom.get("bomFormat") != "CycloneDX":
    raise SystemExit("Python runtime SBOM is not CycloneDX")
runtime_tree_values = [
    str(item.get("value", ""))
    for item in sbom.get("metadata", {}).get("properties", [])
    if isinstance(item, dict) and item.get("name") == runtime_tree_property
]
if (
    len(runtime_tree_values) != 1
    or not re.fullmatch(r"[0-9a-f]{64}", runtime_tree_values[0])
):
    raise SystemExit("signed Python SBOM lacks the exact runtime-tree property")
expected_tree_sha256 = runtime_tree_values[0]
sbom_versions: dict[str, str] = {}
sbom_hashes: dict[str, set[str]] = {}
for component in sbom.get("components", []):
    if not isinstance(component, dict) or not str(component.get("purl", "")).startswith("pkg:pypi/"):
        continue
    name = canonical(str(component.get("name", "")))
    version = str(component.get("version", ""))
    if not name or not version or name in sbom_versions:
        raise SystemExit("Python runtime SBOM distribution identity is invalid")
    hashes: set[str] = set()
    candidates = list(component.get("hashes", []))
    for reference in component.get("externalReferences", []):
        if isinstance(reference, dict):
            candidates.extend(reference.get("hashes", []))
    for item in candidates:
        if isinstance(item, dict) and str(item.get("alg", "")).upper().replace("-", "") == "SHA256":
            digest = str(item.get("content", "")).lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                hashes.add(digest)
    sbom_versions[name] = version
    sbom_hashes[name] = hashes
if sbom_versions != expected or sbom_hashes != expected_hashes:
    raise SystemExit("signed Python SBOM does not exactly bind requirements.lock")

distributions = {
    canonical(dist.metadata["Name"]): dist
    for dist in importlib.metadata.distributions(path=[str(site_packages)])
    if dist.metadata.get("Name")
}
bootstrap = {"pip": "24.0"}
versions = {name: dist.version for name, dist in distributions.items()}
if versions != expected | bootstrap:
    raise SystemExit(
        json.dumps(
            {
                "expected": sorted((expected | bootstrap).items()),
                "installed": sorted(versions.items()),
            },
            sort_keys=True,
        )
    )

site_resolved = site_packages.resolve()
venv_resolved = venv.resolve()
claimed_site_files: set[Path] = set()
verified_entries: list[list[str]] = []
record_failures: list[str] = []
for name in sorted(distributions):
    dist = distributions[name]
    files = tuple(dist.files or ())
    if not files or not any(Path(str(file)).name == "RECORD" for file in files):
        record_failures.append(f"{name}:missing_RECORD")
        continue
    for file in files:
        target = Path(dist.locate_file(file))
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError):
            record_failures.append(f"{name}:{file}:missing_or_unsafe")
            continue
        if target.is_symlink() or not resolved.is_file() or not resolved.is_relative_to(venv_resolved):
            record_failures.append(f"{name}:{file}:outside_or_symlink")
            continue
        if resolved.is_relative_to(site_resolved):
            claimed_site_files.add(resolved)
        if file.hash is None:
            if Path(str(file)).name != "RECORD":
                record_failures.append(f"{name}:{file}:unhashed")
            continue
        if file.hash.mode != "sha256":
            record_failures.append(f"{name}:{file}:unsupported_hash")
            continue
        actual = base64.urlsafe_b64encode(
            hashlib.sha256(resolved.read_bytes()).digest()
        ).decode().rstrip("=")
        if actual != file.hash.value:
            record_failures.append(f"{name}:{file}:hash_mismatch")
        verified_entries.append([name, str(file), actual])

pyc_files = sorted(
    str(path.relative_to(site_packages))
    for path in site_packages.rglob("*.pyc")
    if path.is_file()
)
allowed_symlinks = set(expected_interpreter_links)
unsafe_symlinks = sorted(
    str(path.relative_to(venv))
    for path in venv.rglob("*")
    if path.is_symlink() and path not in allowed_symlinks
)
unowned_files = sorted(
    str(path.relative_to(site_packages))
    for path in site_packages.rglob("*")
    if path.is_file()
    and not path.is_symlink()
    and path.resolve() not in claimed_site_files
)
if record_failures or pyc_files or unsafe_symlinks or unowned_files:
    raise SystemExit(
        json.dumps(
            {
                "record_failures": record_failures[:20],
                "pyc_files": pyc_files[:20],
                "unsafe_symlinks": unsafe_symlinks[:20],
                "unowned_files": unowned_files[:20],
            },
            sort_keys=True,
        )
    )

def stable_tree_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    if path.name != "RECORD":
        return payload
    lines: list[str] = []
    for line in payload.decode("utf-8").splitlines():
        fields = line.split(",")
        if len(fields) != 3:
            raise SystemExit("installed Python RECORD is not canonical CSV")
        if fields[0].startswith("../../../bin/"):
            continue
        lines.append(",".join(fields))
    return ("\n".join(lines) + "\n").encode()


tree_entries = [
    [
        str(path.relative_to(site_packages)),
        hashlib.sha256(stable_tree_bytes(path)).hexdigest(),
    ]
    for path in sorted(site_packages.rglob("*"))
    if path.is_file() and not path.is_symlink()
]
tree_sha256 = hashlib.sha256(
    json.dumps(tree_entries, separators=(",", ":")).encode()
).hexdigest()
if tree_sha256 != expected_tree_sha256:
    raise SystemExit("deployed Python runtime tree differs from signed artifact metadata")
environment_sha256 = hashlib.sha256(
    json.dumps(
        {
            "distributions": sorted(versions.items()),
            "record_files": verified_entries,
            "site_packages_tree_sha256": tree_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()
if previous_path:
    previous = json.loads(Path(previous_path).read_text(encoding="utf-8"))
    if (
        previous.get("site_packages_tree_sha256") != tree_sha256
        or previous.get("environment_sha256") != environment_sha256
        or previous.get("signed_site_packages_tree_sha256") != expected_tree_sha256
        or previous.get("system_sitecustomize_sha256")
        != expected_sitecustomize_sha256
        or previous.get("lock_sha256") != hashlib.sha256(lock_path.read_bytes()).hexdigest()
        or previous.get("sbom_sha256") != hashlib.sha256(sbom_path.read_bytes()).hexdigest()
    ):
        raise SystemExit("deployed Python runtime changed during AC-17")
payload = {
    "schema_version": 1,
    "result": "PASS",
    "phase": "after" if previous_path else "before",
    "python": {"path": str(python_path), "sha256": expected_python_sha256},
    "system_sitecustomize": {
        "path": str(sitecustomize_path),
        "resolved_path": str(sitecustomize_resolved),
        "sha256": expected_sitecustomize_sha256,
    },
    "system_sitecustomize_sha256": expected_sitecustomize_sha256,
    "pyvenv_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
    "lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    "sbom_sha256": hashlib.sha256(sbom_path.read_bytes()).hexdigest(),
    "locked_distribution_count": len(expected),
    "bootstrap_distributions": bootstrap,
    "verified_record_file_count": len(verified_entries),
    "site_packages_file_count": len(tree_entries),
    "site_packages_tree_sha256": tree_sha256,
    "signed_site_packages_tree_property": runtime_tree_property,
    "signed_site_packages_tree_sha256": expected_tree_sha256,
    "environment_sha256": environment_sha256,
    "pyc_file_count": 0,
    "unowned_file_count": 0,
    "interpreter_symlink_count": len(expected_interpreter_links),
    "unsafe_symlink_count": 0,
}
Path(output_path).write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
}

verify_prometheus_payloads() {
  local targets="$1" rules="$2" outbox="$3" glitch="$4" output="$5"
  "$PYTHON_BASE" -I -S - "$targets" "$rules" "$outbox" "$glitch" "$output" <<'PY'
import json
import math
from pathlib import Path
import sys

targets_path, rules_path, outbox_path, glitch_path, output_path = map(
    Path, sys.argv[1:]
)


def response(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != "success":
        raise SystemExit(f"Prometheus response is not successful: {path.name}")
    return value


targets = response(targets_path)
required_jobs = {
    "unihub-retail-web",
    "unihub-retail-operations",
    "unihub-retail-imports",
    "unihub-retail-grile",
    "unihub-retail-exports",
    "unihub-retail-salary-exports",
}
active_targets = targets.get("data", {}).get("activeTargets", [])
if not isinstance(active_targets, list):
    raise SystemExit("Prometheus active-target inventory is malformed")
retail_targets = [
    item
    for item in active_targets
    if isinstance(item, dict)
    and str(item.get("labels", {}).get("job", "")).startswith("unihub-retail-")
]
if (
    len(retail_targets) != len(required_jobs)
    or {item.get("labels", {}).get("job") for item in retail_targets}
    != required_jobs
):
    raise SystemExit("Prometheus Retail target job inventory is not exact")
targets_by_job = {
    job: [
        item
        for item in active_targets
        if isinstance(item, dict) and item.get("labels", {}).get("job") == job
    ]
    for job in required_jobs
}
if any(
    len(items) != 1
    or items[0].get("health") != "up"
    or items[0].get("lastError") != ""
    for items in targets_by_job.values()
):
    raise SystemExit("Prometheus Retail targets are not exact, UP, and error-free")
operations_targets = [
    item
    for item in active_targets
    if isinstance(item, dict)
    and item.get("labels", {}).get("job") == "unihub-retail-operations"
]
if len(operations_targets) != 1:
    raise SystemExit("Prometheus operations target is not unique")
operations_labels = operations_targets[0].get("labels", {})
if (
    not isinstance(operations_labels, dict)
    or set(operations_labels) != {"instance", "job", "service_role"}
    or operations_labels.get("job") != "unihub-retail-operations"
    or operations_labels.get("service_role") != "operations"
    or not isinstance(operations_labels.get("instance"), str)
    or not operations_labels["instance"]
):
    raise SystemExit("Prometheus operations scrape-label identity is not exact")

rules = response(rules_path)
groups = rules.get("data", {}).get("groups", [])
if not isinstance(groups, list):
    raise SystemExit("Prometheus rule-group inventory is malformed")
selected_groups = {
    name: [
        group
        for group in groups
        if isinstance(group, dict) and group.get("name") == name
    ]
    for name in ("unihub-retail-slo-recording", "unihub-retail-slo-alerts")
}
if any(len(items) != 1 for items in selected_groups.values()):
    raise SystemExit("Retail rules are not loaded")
recording_rules = selected_groups["unihub-retail-slo-recording"][0].get("rules")
alert_rules = selected_groups["unihub-retail-slo-alerts"][0].get("rules")
if (
    not isinstance(recording_rules, list)
    or not recording_rules
    or any(
        not isinstance(rule, dict)
        or rule.get("type") != "recording"
        or rule.get("health") != "ok"
        or "state" in rule
        for rule in recording_rules
    )
    or not isinstance(alert_rules, list)
    or not alert_rules
    or any(
        not isinstance(rule, dict)
        or rule.get("type") != "alerting"
        or rule.get("health") != "ok"
        or rule.get("state") != "inactive"
        for rule in alert_rules
    )
):
    raise SystemExit("Retail Prometheus rule health/type/state is not exact")

outbox = response(outbox_path)
series = outbox.get("data", {}).get("result", [])
if not isinstance(series, list):
    raise SystemExit("Prometheus outbox result is not a vector")
event_types = {
    "retail.sales_generation_promoted.v1",
    "retail.pnl_generation_promoted.v1",
    "retail.salary_import_completed.v1",
    "retail.planning_forecast_promoted.v1",
    "retail.grile_manifest_approved.v1",
}
blocking_states = {"pending", "processing", "dead"}
histogram_bounds = {
    "0.005", "0.01", "0.025", "0.05", "0.075", "0.1", "0.25",
    "0.5", "0.75", "1.0", "2.5", "5.0", "7.5", "10.0", "+Inf",
}
expected_scalar={"retail_outbox_oldest_pending_seconds","retail_outbox_head_blocked","retail_outbox_completed_total","retail_outbox_failed_total"}
histogram="retail_outbox_delivery_duration_seconds"
expected_exposition=expected_scalar|{f"{histogram}_{suffix}" for suffix in ("bucket","count","sum")}
names = {
    item.get("metric", {}).get("__name__", "")
    for item in series
    if isinstance(item, dict) and isinstance(item.get("metric"), dict)
}
if names != expected_exposition:
    raise SystemExit("exact outbox metric exposition is absent or extra")
head_name = "retail_outbox_head_blocked"
bucket_name = "retail_outbox_delivery_duration_seconds_bucket"
single_label_names = (expected_scalar - {head_name}) | {
    f"{histogram}_count",
    f"{histogram}_sum",
}
base_keys = {"__name__", "instance", "job", "service_role", "event_type"}
expected_identities: dict[str, set[tuple[str, ...]]] = {
    name: {(event_type,) for event_type in event_types}
    for name in single_label_names
}
expected_identities[head_name] = {
    (event_type, state)
    for event_type in event_types
    for state in blocking_states
}
expected_identities[bucket_name] = {
    (event_type, bound)
    for event_type in event_types
    for bound in histogram_bounds
}
actual_identities = {name: set() for name in expected_exposition}
seen_metrics: set[tuple[tuple[str, str], ...]] = set()
for item in series:
    if not isinstance(item, dict):
        raise SystemExit("Prometheus outbox series is malformed")
    metric = item.get("metric")
    value = item.get("value")
    if (
        not isinstance(metric, dict)
        or not isinstance(value, list)
        or len(value) != 2
        or not math.isfinite(float(value[1]))
        or float(value[1]) < 0
    ):
        raise SystemExit("Prometheus outbox series value is malformed or non-finite")
    name = metric.get("__name__")
    if name not in expected_exposition:
        raise SystemExit("unexpected outbox metric exposition")
    expected_keys = set(base_keys)
    if name == head_name:
        expected_keys.add("state")
    elif name == bucket_name:
        expected_keys.add("le")
    if set(metric) != expected_keys:
        raise SystemExit("outbox metric contains missing, arbitrary, or unbounded labels")
    for scrape_key in ("instance", "job", "service_role"):
        if metric.get(scrape_key) != operations_labels[scrape_key]:
            raise SystemExit("outbox metric escaped the exact operations target")
    event_type = metric.get("event_type")
    if event_type not in event_types:
        raise SystemExit("outbox metric event_type label is not finite")
    if name == head_name:
        state = metric.get("state")
        if state not in blocking_states:
            raise SystemExit("outbox head-blocked state label is not finite")
        identity = (str(event_type), str(state))
    elif name == bucket_name:
        bound = metric.get("le")
        if bound not in histogram_bounds:
            raise SystemExit("outbox histogram boundary label is not exact")
        identity = (str(event_type), str(bound))
    else:
        identity = (str(event_type),)
    canonical_metric = tuple(sorted((str(key), str(value)) for key, value in metric.items()))
    if canonical_metric in seen_metrics:
        raise SystemExit("duplicate outbox metric series")
    seen_metrics.add(canonical_metric)
    actual_identities[str(name)].add(identity)
if actual_identities != expected_identities:
    raise SystemExit("exact outbox metric/label series inventory is absent or extra")

glitch = response(glitch_path)
glitch_series = glitch.get("data", {}).get("result", [])
if (
    not isinstance(glitch_series, list)
    or len(glitch_series) != 1
    or float(glitch_series[0].get("value", [0, "nan"])[1]) != 0
):
    raise SystemExit("recent Retail GlitchTip events are nonzero or absent")

families = {
    "retail_outbox_oldest_pending_seconds",
    "retail_outbox_head_blocked",
    "retail_outbox_completed_total",
    "retail_outbox_failed_total",
    "retail_outbox_delivery_duration_seconds",
}
payload = {
    "schema_version": 1,
    "result": "PASS",
    "healthy_targets": sorted(required_jobs),
    "rule_groups": ["unihub-retail-slo-alerts", "unihub-retail-slo-recording"],
    "outbox_metric_families": sorted(families),
    "outbox_metric_exposition_names": sorted(expected_exposition),
    "outbox_metric_series_count": len(series),
    "outbox_label_schema": {
        "scrape": operations_labels,
        "event_type_values": sorted(event_types),
        "head_blocked_state_values": sorted(blocking_states),
        "histogram_le_values": sorted(histogram_bounds),
        "arbitrary_labels_allowed": False,
    },
    "glitchtip_events_1h": 0,
}
output_path.write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
}

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
  local source tmp fake_pass tcp_debug_flag sandbox_bypass_flag valid_manager valid_forbidden raw_cookie invalid_cookie
  local runtime_line venv_line dell_python_pattern
  source="$(<"$SCRIPT_PATH")"
  tcp_debug_flag="--remote-debugging""-port"
  sandbox_bypass_flag="--no-""sandbox"
  dell_python_pattern="'\$PYTHON_BASE' -I -S -"
  [[ "$source" == '#!/usr/bin/bash -p'* \
    && "$source" != '#!/usr/bin/env bash'* ]] \
    || die "self-test: privileged exact Bash shebang is missing"
  [[ "$source" == *'--request GET'* ]] || die "self-test: HTTP GET fence is missing"
  [[ "$source" == *'unexpected non-read-only probe path'* ]] || die "self-test: route allowlist is missing"
  [[ "$source" == *'"salary_export_executed":False'* ]] || die "self-test: salary export fence evidence is missing"
  [[ "$source" != *'--request '"POST"* && "$source" != *'--request '"PUT"* \
    && "$source" != *'--request '"PATCH"* && "$source" != *'--request '"DELETE"* ]] \
    || die "self-test: mutating HTTP method found"
  [[ "$source" == *'TASK_A_BRANCH="codex/retail-definitive-closure-20260812"'* \
    && "$source" == *'TASK_B_BRANCH="codex/retail-definitive-closure-b-20260813"'* ]] \
    || die "self-test: exact task branches are not frozen"
  [[ "$source" == *'Grile V2 · pilot'* \
    && "$source" == *'Statistici Salarii'* \
    && "$source" == *'Builder export Excel'* \
    && "$source" == *'mobile-grile-v2'* \
    && "$source" == *'mobile-target'* \
    && "$source" == *'mobile-salary-read'* \
    && "$source" == *'mobile-imports'* \
    && "$source" == *'mobile-exports-read'* \
    && "$source" == *'PYTHON_BASE_SHA256'* \
    && "$source" == *'refs/heads/main'* ]] \
    || die "self-test: browser/ref acceptance surface is incomplete"
  [[ "$source" == *'GH_HOST=github.com'* \
    && "$source" == *'GITHUB_ORIGIN_URL="https://github.com/anervalens-netizen/unihub-retail.git"'* \
    && "$source" == *'"--remote-debugging-pipe"'* \
    && "$source" == *'os.setuid(operator_uid)'* \
    && "$source" == *'os.setgid(operator_gid)'* \
    && "$source" != *"$tcp_debug_flag"* \
    && "$source" != *"$sandbox_bypass_flag"* ]] \
    || die "self-test: least-privilege browser or canonical GitHub binding is missing"
  # shellcheck disable=SC2016
  [[ "$source" == *'--certificate-github-workflow-sha "$expected_sha"'* \
    && "$source" == *'--certificate-github-workflow-repository "$GITHUB_REPOSITORY"'* \
    && "$source" == *'--certificate-github-workflow-ref "refs/heads/main"'* \
    && "$source" == *'--certificate-github-workflow-trigger "workflow_dispatch"'* \
    && "$source" == *'--certificate-github-workflow-name "CI"'* ]] \
    || die "self-test: Release-B Sigstore workflow claims are not exact"
  # shellcheck disable=SC2016
  [[ "$source" == *"$dell_python_pattern"* \
    && "$source" == *'generation_${BACKUP_STAMP}.sha256'* \
    && "$source" == *'generation_${BACKUP_STAMP}.result'* \
    && "$source" == *'/usr/bin/sha256sum --strict --check'* \
    && "$source" == *'[str(pg_restore), "--list", str(target)]'* \
    && "$source" == *'"PRAGMA integrity_check;"'* \
    && "$source" == *'PG_RESTORE_SHA256="fc00112585bd75eb9eb6fcd11ca4cf7222acf10259a1f21eea4889536dee640a"'* \
    && "$source" == *'"backup_generation_manifest_sha256"'* \
    && "$source" == *'"backup_generation_result_sha256"'* \
    && "$source" == *'deploy-entrypoint-bootstrap.json'* \
    && "$source" == *'rollback-python-runtime.json'* \
    && "$source" == *'rollback-python-supply.json'* \
    && "$source" == *'venv.pre-switch'* \
    && "$source" == *'python-runtime-supply.old'* ]] \
    || die "self-test: Dell isolation or exact backup-generation proof is incomplete"
  # shellcheck disable=SC2016
  [[ "$source" == *'verify_python_runtime "$WORK/fragments/python-runtime-before.json"'* \
    && "$source" == *'verify_python_runtime "$WORK/fragments/python-runtime-after.json"'* \
    && "$source" == *'"$PYTHON" -B -I -'* \
    && "$source" == *'SYSTEM_SITECUSTOMIZE_RESOLVED="/etc/python3.12/sitecustomize.py"'* \
    && "$source" == *'SYSTEM_SITECUSTOMIZE_SHA256="43d81125d92376b1a69d53a71126a041cc9a18d8080e92dea0a2ae23be138b1e"'* \
    && "$source" == *'unihub:python-runtime:site-packages-tree-sha256:v1'* \
    && "$source" == *'tree_sha256 != expected_tree_sha256'* \
    && "$source" == *'"pyc_file_count": 0'* \
    && "$source" == *'"unowned_file_count": 0'* \
    && "$source" == *'"interpreter_symlink_count": len(expected_interpreter_links)'* \
    && "$source" == *'"unsafe_symlink_count": 0'* ]] \
    || die "self-test: deployed Python runtime lock/recheck is incomplete"
  # shellcheck disable=SC2016
  runtime_line="$(grep -nF 'verify_python_runtime "$WORK/fragments/python-runtime-before.json"' \
    "$SCRIPT_PATH" | tail -n 1 | cut -d: -f1)"
  # shellcheck disable=SC2016
  venv_line="$(grep -nF '"$PYTHON" -B -I -' "$SCRIPT_PATH" | tail -n 1 | cut -d: -f1)"
  [[ "$runtime_line" =~ ^[0-9]+$ && "$venv_line" =~ ^[0-9]+$ \
    && "$runtime_line" -lt "$venv_line" ]] \
    || die "self-test: venv execution precedes base-interpreter runtime verification"
  for metric in \
    retail_outbox_oldest_pending_seconds \
    retail_outbox_head_blocked \
    retail_outbox_completed_total \
    retail_outbox_failed_total \
    retail_outbox_delivery_duration_seconds_bucket \
    retail_outbox_delivery_duration_seconds_count \
    retail_outbox_delivery_duration_seconds_sum; do
    [[ "$source" == *"$metric"* ]] \
      || die "self-test: exact outbox metric exposition is incomplete: $metric"
  done
  tmp="$(mktemp -d)"
  trap 'rm -rf -- "$tmp"' RETURN
  valid_manager="$tmp/manager.cookies"
  valid_forbidden="$tmp/forbidden.cookies"
  raw_cookie="$tmp/raw.cookies"
  invalid_cookie="$tmp/invalid.cookies"
  printf '%s\n' \
    '# Netscape HTTP Cookie File' \
    $'#HttpOnly_.retail.unihub.ro\tTRUE\t/\tTRUE\t0\tsession\tfake-manager' \
    >"$valid_manager"
  printf '%s\n' \
    '# Netscape HTTP Cookie File' \
    $'retail.unihub.ro\tFALSE\t/\tTRUE\t0\tsession\tfake-forbidden' \
    >"$valid_forbidden"
  printf '%s\n' 'Cookie: session=fake-forbidden' >"$raw_cookie"
  verify_cookie_scope "$valid_manager" "$valid_forbidden" "$tmp/cookie-scope.json" \
    >/dev/null
  verify_cookie_scope "$valid_manager" "$raw_cookie" "$tmp/raw-cookie-scope.json" \
    >/dev/null
  for invalid_record in \
    $'.unihub.ro\tTRUE\t/\tTRUE\t0\tsession\tforeign' \
    $'retail.unihub.ro\tTRUE\t/\tTRUE\t0\tsession\tinconsistent-domain-flag' \
    $'retail.unihub.ro\tFALSE\t/api\tTRUE\t0\tsession\twrong-path' \
    $'retail.unihub.ro\tFALSE\t/\tFALSE\t0\tsession\tinsecure' \
    $'retail.unihub.ro\tFALSE\t/\tTRUE\t1\tsession\texpired'; do
    printf '%s\n' '# Netscape HTTP Cookie File' "$invalid_record" >"$invalid_cookie"
    if verify_cookie_scope "$valid_manager" "$invalid_cookie" \
        "$tmp/invalid-cookie-scope.json" >/dev/null 2>&1; then
      die "self-test: unsafe cookie scope was accepted"
    fi
  done
  "$PYTHON_BASE" -I -S - "$tmp" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
jobs = {
    "unihub-retail-web": ("172.23.0.1:9898", "web"),
    "unihub-retail-operations": ("172.23.0.1:9901", "operations"),
    "unihub-retail-imports": ("172.23.0.1:9902", "imports"),
    "unihub-retail-grile": ("172.23.0.1:9903", "grile"),
    "unihub-retail-exports": ("172.23.0.1:9904", "exports"),
    "unihub-retail-salary-exports": ("172.23.0.1:9905", "salary_exports"),
}
targets = {
    "status": "success",
    "data": {
        "activeTargets": [
            {
                "health": "up",
                "lastError": "",
                "labels": {
                    "instance": instance,
                    "job": job,
                    "service_role": role,
                },
            }
            for job, (instance, role) in jobs.items()
        ]
    },
}
rules = {
    "status": "success",
    "data": {
        "groups": [
            {
                "name": "unihub-retail-slo-recording",
                "rules": [{"type": "recording", "health": "ok"}],
            },
            {
                "name": "unihub-retail-slo-alerts",
                "rules": [
                    {"type": "alerting", "health": "ok", "state": "inactive"}
                ],
            },
        ]
    },
}
event_types = (
    "retail.sales_generation_promoted.v1",
    "retail.pnl_generation_promoted.v1",
    "retail.salary_import_completed.v1",
    "retail.planning_forecast_promoted.v1",
    "retail.grile_manifest_approved.v1",
)
bounds = (
    "0.005", "0.01", "0.025", "0.05", "0.075", "0.1", "0.25",
    "0.5", "0.75", "1.0", "2.5", "5.0", "7.5", "10.0", "+Inf",
)
base = {
    "instance": "172.23.0.1:9901",
    "job": "unihub-retail-operations",
    "service_role": "operations",
}
series = []
for event_type in event_types:
    for name in (
        "retail_outbox_oldest_pending_seconds",
        "retail_outbox_completed_total",
        "retail_outbox_failed_total",
        "retail_outbox_delivery_duration_seconds_count",
        "retail_outbox_delivery_duration_seconds_sum",
    ):
        series.append({
            "metric": {"__name__": name, **base, "event_type": event_type},
            "value": [0, "0"],
        })
    for state in ("pending", "processing", "dead"):
        series.append({
            "metric": {
                "__name__": "retail_outbox_head_blocked",
                **base,
                "event_type": event_type,
                "state": state,
            },
            "value": [0, "0"],
        })
    for bound in bounds:
        series.append({
            "metric": {
                "__name__": "retail_outbox_delivery_duration_seconds_bucket",
                **base,
                "event_type": event_type,
                "le": bound,
            },
            "value": [0, "0"],
        })
(root / "prom-targets.json").write_text(json.dumps(targets), encoding="utf-8")
(root / "prom-rules.json").write_text(json.dumps(rules), encoding="utf-8")
(root / "prom-outbox.json").write_text(
    json.dumps({"status": "success", "data": {"result": series}}),
    encoding="utf-8",
)
(root / "prom-glitchtip.json").write_text(
    json.dumps({"status": "success", "data": {"result": [{"value": [0, "0"]}]}}),
    encoding="utf-8",
)
PY
  verify_prometheus_payloads \
    "$tmp/prom-targets.json" "$tmp/prom-rules.json" \
    "$tmp/prom-outbox.json" "$tmp/prom-glitchtip.json" \
    "$tmp/prometheus-pass.json"
  cp -- "$tmp/prom-rules.json" "$tmp/prom-rules-firing.json"
  "$PYTHON_BASE" -I -S - "$tmp/prom-rules-firing.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["data"]["groups"][1]["rules"][0]["state"] = "firing"
path.write_text(json.dumps(payload), encoding="utf-8")
PY
  if verify_prometheus_payloads \
      "$tmp/prom-targets.json" "$tmp/prom-rules-firing.json" \
      "$tmp/prom-outbox.json" "$tmp/prom-glitchtip.json" \
      "$tmp/prometheus-firing.json" >/dev/null 2>&1; then
    die "self-test: firing Retail alert was accepted"
  fi
  cp -- "$tmp/prom-targets.json" "$tmp/prom-targets-duplicate.json"
  "$PYTHON_BASE" -I -S - "$tmp/prom-targets-duplicate.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
duplicate = dict(payload["data"]["activeTargets"][0])
duplicate["health"] = "down"
duplicate["lastError"] = "duplicate target"
payload["data"]["activeTargets"].append(duplicate)
path.write_text(json.dumps(payload), encoding="utf-8")
PY
  if verify_prometheus_payloads \
      "$tmp/prom-targets-duplicate.json" "$tmp/prom-rules.json" \
      "$tmp/prom-outbox.json" "$tmp/prom-glitchtip.json" \
      "$tmp/prometheus-duplicate.json" >/dev/null 2>&1; then
    die "self-test: duplicate UP/DOWN Retail target was accepted"
  fi
  "$PYTHON_BASE" -I -S - "$tmp/prom-outbox.json" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
payload["data"]["result"][0]["metric"]["unbounded_user_id"] = "customer-123"
path.write_text(json.dumps(payload), encoding="utf-8")
PY
  if verify_prometheus_payloads \
      "$tmp/prom-targets.json" "$tmp/prom-rules.json" \
      "$tmp/prom-outbox.json" "$tmp/prom-glitchtip.json" \
      "$tmp/prometheus-unsafe.json" >/dev/null 2>&1; then
    die "self-test: unbounded outbox metric label was accepted"
  fi
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
  printf 'AC-17 verifier self-test PASS: fake/stale evidence, firing alert, duplicate target, and unbounded labels rejected\n'
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

[[ -x "$PG_RESTORE" && "$(sha256_file "$PG_RESTORE")" == "$PG_RESTORE_SHA256" \
  && "$($PG_RESTORE --version)" == "$PG_RESTORE_VERSION" ]] \
  || die "pg_restore is not the pinned production backup verifier"
[[ -x "$SQLITE3" && "$(sha256_file "$SQLITE3")" == "$SQLITE3_SHA256" \
  && "$($SQLITE3 --version)" == "$SQLITE3_VERSION" ]] \
  || die "sqlite3 is not the pinned production backup verifier"

for command in git ssh sudo sha256sum cosign curl systemctl journalctl tar diff awk sed stat date readlink tr id; do
  command -v "$command" >/dev/null || die "required verifier utility missing: $command"
done
[[ -x "$GH_BIN" && "$(sha256_file "$GH_BIN")" == "$GH_BIN_SHA256" ]] \
  || die "GitHub CLI is not the pinned primary binary"
"$GH_BIN" --version | grep -Eq '^gh version 2\.97\.0 ' \
  || die "GitHub CLI version mismatch"
COSIGN_BIN="$(command -v cosign)"
[[ "$(sha256_file "$COSIGN_BIN")" == "$COSIGN_SHA256" ]] \
  || die "cosign is not the frozen v3.1.3 linux-amd64 binary"
"$COSIGN_BIN" version 2>&1 | grep -Eq 'GitVersion:[[:space:]]*v3\.1\.3([[:space:]]|$)' \
  || die "cosign version output is not v3.1.3"

OPERATOR_UID="$(id -u andrei)"
for cookie_file in "$MANAGER_COOKIE_FILE" "$FORBIDDEN_COOKIE_FILE"; do
  mode="$(stat -c '%a' "$cookie_file")"
  [[ "$mode" == "400" || "$mode" == "600" ]] \
    || die "cookie file permissions must be exactly 0400 or 0600"
  owner_uid="$(stat -c '%u' "$cookie_file")"
  [[ "$owner_uid" == "0" || "$owner_uid" == "$OPERATOR_UID" ]] \
    || die "cookie file owner must be root or the andrei operator"
  [[ -s "$cookie_file" ]] || die "cookie file is empty"
done

[[ "$(git -C "$LIVE_ROOT" remote get-url origin)" == "$GITHUB_ORIGIN_URL" ]] \
  || die "primary origin URL is not the canonical GitHub repository"
[[ "$(git -C "$LIVE_ROOT" rev-parse HEAD)" == "$MAIN_B_SHA" ]] || die "live checkout is not MAIN_B_SHA"
[[ "$(git -C "$LIVE_ROOT" branch --show-current)" == "main" ]] || die "live checkout is not branch main"
[[ -z "$(git -C "$LIVE_ROOT" status --porcelain=v1 --untracked-files=all)" ]] || die "live checkout is dirty"
[[ "$(git -C "$LIVE_ROOT" rev-parse origin/main)" == "$MAIN_B_SHA" ]] || die "local origin/main is not MAIN_B_SHA"
REMOTE_MAIN="$(sudo -u andrei git -C "$LIVE_ROOT" ls-remote origin refs/heads/main)"
[[ "$REMOTE_MAIN" == "$MAIN_B_SHA"$'\t'refs/heads/main ]] \
  || die "live GitHub main is not MAIN_B_SHA"
git -C "$LIVE_ROOT" merge-base --is-ancestor "$MAIN_A_SHA" "$MAIN_B_SHA" \
  || die "MAIN_A_SHA is not an ancestor of MAIN_B_SHA"
[[ "$(git -C "$LIVE_ROOT" rev-parse "$MAIN_B_SHA:scripts/verify_deployed_release.sh")" \
   == "$(git -C "$LIVE_ROOT" hash-object "$SCRIPT_PATH")" ]] \
  || die "running verifier differs from MAIN_B_SHA"

mkdir -p "$(dirname "$EVIDENCE")"
WORK="$(mktemp -d "$(dirname "$EVIDENCE")/.ac17.XXXXXX")"
trap 'rm -rf -- "$WORK"' EXIT
mkdir "$WORK/fragments" "$WORK/raw" "$WORK/artifacts"
read -r MANAGER_COOKIE_KIND FORBIDDEN_COOKIE_KIND < <(
  verify_cookie_scope "$MANAGER_COOKIE_FILE" "$FORBIDDEN_COOKIE_FILE" \
    "$WORK/fragments/cookie-scope.json"
)
[[ "$MANAGER_COOKIE_KIND" =~ ^(netscape|raw-header)$ \
  && "$FORBIDDEN_COOKIE_KIND" =~ ^(netscape|raw-header)$ ]] \
  || die "cookie verifier returned an invalid input kind"
PYTHON="$LIVE_ROOT/backend/venv/bin/python"
[[ -x "$PYTHON" && "$(readlink -f "$PYTHON")" == "$PYTHON_BASE" \
  && "$(sha256_file "$PYTHON_BASE")" == "$PYTHON_BASE_SHA256" ]] \
  || die "deployed backend Python is not rooted in the pinned interpreter"
[[ -x "$BROWSER_CHROME" \
  && "$(sha256_file "$BROWSER_CHROME")" == "$BROWSER_CHROME_SHA256" \
  && "$($BROWSER_CHROME --version)" == "$BROWSER_CHROME_VERSION" ]] \
  || die "pinned production browser is unavailable or changed"

verify_b_artifact() {
  local dir="$1" expected_sha="$2" expected_archive_sha="$3" output="$4"
  "$PYTHON_BASE" -I -S - "$dir" "$expected_sha" "$expected_archive_sha" "$output" <<'PY'
import hashlib, json, pathlib, re, sys, tarfile
d = pathlib.Path(sys.argv[1]).resolve(); sha, expected_archive, out = sys.argv[2:]
archive_name = f"retail-release-{sha}.tar.gz"
checksummed = {"SOURCE_SHA", archive_name, "SBOM.cdx.json", "SBOM.npm.cdx.json", "SBOM.python.cdx.json", "PYTHON_RUNTIME_SUPPLY.json", "PYTHON_RUNTIME_REQUIREMENTS.lock", "PYTHON_RUNTIME_WHEELS.tar.gz", "PROVENANCE.json", "RELEASE_MANIFEST.json"}
required = checksummed | {"SHA256SUMS", "RELEASE_MANIFEST.sigstore.json"}
actual = {p.name for p in d.iterdir()}
if actual != required or any(not (d / n).is_file() or (d / n).is_symlink() for n in required): raise SystemExit("artifact inventory incomplete or unsafe")
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
frontend_input=m.get("frontendBuildInput")
if not isinstance(frontend_input,dict) or frontend_input.get("name")!="VITE_FRONTEND_GLITCHTIP_DSN" or not re.fullmatch(r"[0-9a-f]{64}",str(frontend_input.get("sha256",""))): raise SystemExit("release frontend build-input identity mismatch")
p=json.loads((d/"PROVENANCE.json").read_text()); subjects=p.get("subject")
if p.get("_type")!="https://in-toto.io/Statement/v1" or p.get("predicateType")!="https://slsa.dev/provenance/v1": raise SystemExit("provenance type mismatch")
if not isinstance(subjects,list) or len(subjects)!=1 or subjects[0].get("name")!=archive_name or subjects[0].get("digest",{}).get("sha256")!=expected_archive: raise SystemExit("provenance subject mismatch")
resolved=p.get("predicate",{}).get("buildDefinition",{}).get("resolvedDependencies",[])
external=p.get("predicate",{}).get("buildDefinition",{}).get("externalParameters",{})
if external.get("frontendBuildInput")!=frontend_input: raise SystemExit("provenance frontend build-input mismatch")
if not any(x.get("digest",{}).get("gitCommit")==sha for x in resolved if isinstance(x,dict)): raise SystemExit("provenance source mismatch")
with tarfile.open(d/archive_name,"r:gz") as tf:
    for member in tf.getmembers():
        q=pathlib.PurePosixPath(member.name)
        if q.is_absolute() or ".." in q.parts or member.issym() or member.islnk(): raise SystemExit("unsafe archive member")
payload={"schema_version":1,"result":"PASS","source_sha":sha,"archive":archive_name,"archive_sha256":expected_archive,"release_manifest_sha256":hashlib.sha256((d/"RELEASE_MANIFEST.json").read_bytes()).hexdigest(),"provenance_sha256":hashlib.sha256((d/"PROVENANCE.json").read_bytes()).hexdigest(),"sigstore_bundle_sha256":hashlib.sha256((d/"RELEASE_MANIFEST.sigstore.json").read_bytes()).hexdigest(),"frontend_build_input_sha256":frontend_input["sha256"],"inventory":entries}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY

DEPLOYED_AT="$(sed -n 's/^UPDATED_AT=//p' "$BACKUP_HANDLE/release.env")"
[[ -n "$DEPLOYED_AT" ]] || die "deploy timestamp missing"
read -r DEPLOY_HANDLE_EPOCH DEPLOYED_EPOCH < <(
  "$PYTHON_BASE" -I -S - "$(basename "$BACKUP_HANDLE")" "$DEPLOYED_AT" <<'PY'
import datetime,sys
handle,deployed=sys.argv[1:]
start=int(datetime.datetime.strptime(handle[:16],"%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())
end=int(datetime.datetime.fromisoformat(deployed.replace("Z","+00:00")).timestamp())
if start > end: raise SystemExit("invalid deploy interval")
print(start,end)
PY
)
  "$PYTHON_BASE" -I -S "$LIVE_ROOT/scripts/validate_release_sbom.py" npm "$dir/SBOM.npm.cdx.json" >/dev/null
  "$PYTHON_BASE" -I -S "$LIVE_ROOT/scripts/validate_release_sbom.py" pypi "$dir/SBOM.python.cdx.json" >/dev/null
  "$PYTHON_BASE" -I -S "$LIVE_ROOT/scripts/validate_release_sbom.py" aggregate "$dir/SBOM.cdx.json" --expected-sha "$expected_sha" >/dev/null
  "$COSIGN_BIN" verify-blob "$dir/RELEASE_MANIFEST.json" \
    --bundle "$dir/RELEASE_MANIFEST.sigstore.json" \
    --certificate-identity "https://github.com/anervalens-netizen/unihub-retail/.github/workflows/ci.yml@refs/heads/main" \
    --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
    --certificate-github-workflow-sha "$expected_sha" \
    --certificate-github-workflow-repository "$GITHUB_REPOSITORY" \
    --certificate-github-workflow-ref "refs/heads/main" \
    --certificate-github-workflow-trigger "workflow_dispatch" \
    --certificate-github-workflow-name "CI" \
    >"$WORK/raw/release-b-cosign.log" 2>&1
}

verify_b_artifact "$B_ARTIFACT_DIR" "$MAIN_B_SHA" "$B_ARCHIVE_SHA256" \
  "$WORK/fragments/release-b-artifact.json"

COSIGN_BIN="$COSIGN_BIN" "$PYTHON_BASE" -I -S \
  "$LIVE_ROOT/scripts/check_release_a_candidate.py" \
  --verify-main-evidence "$A_EVIDENCE" --expected-sha "$MAIN_A_SHA" \
  --expected-candidate-sha "$MAIN_B_SHA" --release-a-artifact-dir "$A_ARTIFACT_DIR" \
  --evidence "$WORK/fragments/release-a-verification.json" \
  >"$WORK/raw/release-a-verification.log" 2>&1
"$PYTHON_BASE" -I -S - "$WORK/fragments/release-a-verification.json" "$MAIN_A_SHA" <<'PY'
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
cmp -s "$WORK/artifacts/b/backend/requirements.lock" \
  "$LIVE_ROOT/backend/requirements.lock" \
  || die "live Python runtime lock differs from signed Release-B artifact"
require_regular "$DEPLOY_ENTRYPOINT"
[[ "$(stat -c '%u:%g:%a' "$DEPLOY_ENTRYPOINT")" == "0:0:755" ]] \
  || die "production deploy entrypoint must be root:root mode 0755"
  cmp -s "$WORK/artifacts/b/ops/deploy-retail-artifact.sh" "$DEPLOY_ENTRYPOINT" \
    || die "root-owned production deploy entrypoint differs from signed Release-B source"
  cmp -s "$WORK/artifacts/a/ops/deploy-retail-artifact.sh" \
    "$WORK/artifacts/b/ops/deploy-retail-artifact.sh" \
    || die "one-time deploy entrypoint bootstrap bytes differ between signed A and B"
  "$PYTHON_BASE" -I -S - "$DEPLOY_ENTRYPOINT" "$WORK/fragments/deploy-entrypoint.json" <<'PY'
import hashlib,json,pathlib,sys
path=pathlib.Path(sys.argv[1])
payload={"schema_version":1,"result":"PASS","path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"owner":"root","group":"root","mode":"0755"}
pathlib.Path(sys.argv[2]).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY
  DEPLOY_ENTRYPOINT_SHA256="$(sha256_file "$DEPLOY_ENTRYPOINT")"
  DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE="$DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE_ROOT/${DEPLOY_ENTRYPOINT_SHA256}.json"
  require_regular "$DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE"
  [[ "$(stat -c '%u:%g:%a' "$DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE")" == "0:0:600" ]] \
    || die "deploy entrypoint bootstrap evidence must be root:root mode 0600"
  "$PYTHON_BASE" -I -S - \
    "$DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE" "$DEPLOY_ENTRYPOINT" \
    "$DEPLOY_ENTRYPOINT_SHA256" "$MAIN_A_SHA" "$(sha256_file "$A_ARCHIVE")" \
    "$DEPLOY_ENTRYPOINT_BACKUP_ROOT" \
    "$WORK/fragments/deploy-entrypoint-bootstrap.json" <<'PY'
import hashlib,json,pathlib,re,sys
evidence_value,target,new_sha,release_a_sha,release_a_artifact_sha,backup_root_value,output=sys.argv[1:]
evidence=pathlib.Path(evidence_value).resolve()
backup_root=pathlib.Path(backup_root_value).resolve()
payload=json.loads(evidence.read_text(encoding="utf-8"))
old_sha=str(payload.get("old_sha256", ""))
backup_value=payload.get("backup_path")
installed_at=str(payload.get("installed_at", ""))
if (
    evidence.parent != pathlib.Path("/var/lib/unihub-retail-deploy/bootstrap-evidence")
    or evidence.name != f"{new_sha}.json"
    or payload.get("schema_version") != 1
    or payload.get("result") != "PASS"
    or payload.get("target") != target
    or payload.get("new_sha256") != new_sha
    or payload.get("source_release_sha") != release_a_sha
    or payload.get("source_artifact_sha256") != release_a_artifact_sha
    or payload.get("root_owned") is not True
    or payload.get("mode") != "0755"
    or re.fullmatch(r"[0-9a-f]{64}", old_sha) is None
    or old_sha == new_sha
    or re.fullmatch(r"[0-9]{8}T[0-9]{6}Z", installed_at) is None
    or not isinstance(backup_value, str)
):
    raise SystemExit("deploy entrypoint bootstrap evidence identity mismatch")
backup=pathlib.Path(backup_value).resolve()
if (
    backup.parent != backup_root
    or backup.name != f"{installed_at}-{old_sha}.sh"
    or not backup.is_file()
    or backup.is_symlink()
    or hashlib.sha256(backup.read_bytes()).hexdigest() != old_sha
):
    raise SystemExit("deploy entrypoint bootstrap rollback copy mismatch")
result={
    "schema_version":1,
    "result":"PASS",
    "release_a_sha":release_a_sha,
    "release_a_artifact_sha256":release_a_artifact_sha,
    "entrypoint_sha256":new_sha,
    "prior_entrypoint_sha256":old_sha,
    "bootstrap_evidence_sha256":hashlib.sha256(evidence.read_bytes()).hexdigest(),
    "bootstrap_backup_sha256":hashlib.sha256(backup.read_bytes()).hexdigest(),
    "bootstrap_backup_mode":"0400",
}
pathlib.Path(output).write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n")
PY
  BOOTSTRAP_BACKUP_PATH="$("$PYTHON_BASE" -I -S -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["backup_path"])' \
    "$DEPLOY_ENTRYPOINT_BOOTSTRAP_EVIDENCE")"
  [[ "$(stat -c '%u:%g:%a' "$BOOTSTRAP_BACKUP_PATH")" == "0:0:400" ]] \
    || die "deploy entrypoint bootstrap rollback copy must be root:root mode 0400"

  ROLLBACK_VENV="$BACKUP_HANDLE/venv.pre-switch"
  ROLLBACK_VENV_EVIDENCE="$BACKUP_HANDLE/venv-before.json"
  ROLLBACK_PYTHON_SUPPLY="$BACKUP_HANDLE/python-runtime-supply.old"
  require_directory "$ROLLBACK_VENV"
  require_regular "$ROLLBACK_VENV_EVIDENCE"
  require_directory "$ROLLBACK_PYTHON_SUPPLY"
  require_directory "$ROLLBACK_PYTHON_SUPPLY/wheels"
  [[ "$(stat -c '%u:%g:%a' "$ROLLBACK_VENV_EVIDENCE")" == "0:0:600" ]] \
    || die "rollback Python runtime identity must be root:root mode 0600"
  for rollback_supply_name in \
    PYTHON_RUNTIME_REQUIREMENTS.lock PYTHON_RUNTIME_SUPPLY.json SBOM.python.cdx.json; do
    require_regular "$ROLLBACK_PYTHON_SUPPLY/$rollback_supply_name"
    cmp -s "$ROLLBACK_PYTHON_SUPPLY/$rollback_supply_name" \
      "$A_ARTIFACT_DIR/$rollback_supply_name" \
      || die "rollback Python runtime supply differs from signed Release-A: $rollback_supply_name"
  done
  verify_python_runtime \
    "$WORK/fragments/rollback-python-runtime.json" "" \
    "$ROLLBACK_VENV" \
    "$ROLLBACK_PYTHON_SUPPLY/PYTHON_RUNTIME_REQUIREMENTS.lock" \
    "$ROLLBACK_PYTHON_SUPPLY/SBOM.python.cdx.json"
  "$PYTHON_BASE" -I -S - \
    "$ROLLBACK_VENV_EVIDENCE" \
    "$WORK/fragments/rollback-python-runtime.json" \
    "$ROLLBACK_PYTHON_SUPPLY/PYTHON_RUNTIME_SUPPLY.json" \
    "$ROLLBACK_PYTHON_SUPPLY/wheels" \
    "$A_ARTIFACT_DIR/PYTHON_RUNTIME_WHEELS.tar.gz" \
    "$WORK/fragments/rollback-python-supply.json" <<'PY'
import hashlib,json,pathlib,re,sys
saved_path,recomputed_path,supply_path,wheels_value,archive_value,output=map(pathlib.Path,sys.argv[1:])
saved=json.loads(saved_path.read_text(encoding="utf-8"))
recomputed=json.loads(recomputed_path.read_text(encoding="utf-8"))
supply=json.loads(supply_path.read_text(encoding="utf-8"))
wheels=wheels_value.resolve()
archive=archive_value.resolve()
expected_wheels=supply.get("wheels")
bootstrap=recomputed.get("bootstrap_distributions")
if (
    saved.get("schemaVersion") != 1
    or saved.get("legacyOpaque") is not None
    or saved.get("path") != "/opt/Mobiup/unihub-retail/backend/venv"
    or saved.get("pythonSha256") != recomputed.get("python", {}).get("sha256")
    or saved.get("requirementsSha256") != recomputed.get("lock_sha256")
    or saved.get("sbomSha256") != recomputed.get("sbom_sha256")
    or saved.get("sitePackagesTreeSha256") != recomputed.get("site_packages_tree_sha256")
    or not isinstance(bootstrap, dict)
    or saved.get("distributionCount") != recomputed.get("locked_distribution_count") + len(bootstrap)
    or saved.get("sitePackagesFileCount") != recomputed.get("site_packages_file_count")
    or not isinstance(expected_wheels, list)
    or not expected_wheels
):
    raise SystemExit("rollback Python runtime identity differs from the signed Release-A tree")
wheel_archive=supply.get("wheelArchive")
if (
    not isinstance(wheel_archive, dict)
    or wheel_archive.get("name") != archive.name
    or wheel_archive.get("sha256") != hashlib.sha256(archive.read_bytes()).hexdigest()
    or wheel_archive.get("fileCount") != len(expected_wheels)
):
    raise SystemExit("rollback Python wheel archive binding mismatch")
expected={}
for item in expected_wheels:
    if not isinstance(item,dict):
        raise SystemExit("rollback Python wheel manifest entry is invalid")
    name=item.get("name"); digest=item.get("sha256"); size=item.get("size")
    if (
        not isinstance(name,str)
        or pathlib.PurePosixPath(name).name != name
        or re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl",name) is None
        or re.fullmatch(r"[0-9a-f]{64}",str(digest)) is None
        or not isinstance(size,int)
        or size <= 0
        or name in expected
    ):
        raise SystemExit("rollback Python wheel manifest entry is unsafe")
    expected[name]=(digest,size)
actual={path.name:path for path in wheels.iterdir()}
if set(actual) != set(expected):
    raise SystemExit("rollback Python wheel inventory differs from Release-A")
for name,path in actual.items():
    digest,size=expected[name]
    if path.is_symlink() or not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f"rollback Python wheel differs from Release-A: {name}")
result={
    "schema_version":1,
    "result":"PASS",
    "rollback_identity_sha256":hashlib.sha256(saved_path.read_bytes()).hexdigest(),
    "runtime_tree_sha256":saved["sitePackagesTreeSha256"],
    "runtime_supply_sha256":hashlib.sha256(supply_path.read_bytes()).hexdigest(),
    "wheel_archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),
    "wheel_count":len(actual),
}
pathlib.Path(output).write_text(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n")
PY

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

BACKUP_STAMP="$(sed -n 's/^stamp=//p' "$BACKUP_STATUS")"
[[ "$BACKUP_STAMP" =~ ^20[0-9]{6}_[0-9]{6}$ ]] \
  || die "verified backup generation stamp is invalid"
BACKUP_GENERATION_MANIFEST="$(dirname "$BACKUP_STATUS")/generation_${BACKUP_STAMP}.sha256"
BACKUP_GENERATION_RESULT="$(dirname "$BACKUP_STATUS")/generation_${BACKUP_STAMP}.result"
require_directory "$BACKUP_DATA_ROOT"
require_regular "$BACKUP_GENERATION_MANIFEST"
require_regular "$BACKUP_GENERATION_RESULT"
"$PYTHON_BASE" -I -S - "$BACKUP_DATA_ROOT" "$BACKUP_GENERATION_MANIFEST" \
  "$BACKUP_GENERATION_RESULT" "$BACKUP_STAMP" <<'PY'
from pathlib import Path, PurePosixPath
import re
import sys

root = Path(sys.argv[1]).resolve()
manifest = Path(sys.argv[2])
result = Path(sys.argv[3])
stamp = sys.argv[4]
if (
    manifest.parent.resolve() != root / "manifests"
    or result.parent.resolve() != root / "manifests"
    or manifest.name != f"generation_{stamp}.sha256"
    or result.name != f"generation_{stamp}.result"
):
    raise SystemExit("backup generation evidence escaped its exact root/stamp")
seen: set[str] = set()
for line in manifest.read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
    if not match:
        raise SystemExit("backup generation checksum manifest is malformed")
    relative = match.group(2)
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts or relative in seen:
        raise SystemExit("backup generation checksum path is unsafe or duplicate")
    if not re.search(rf"_{re.escape(stamp)}\.(?:dump|db)$", path.name):
        raise SystemExit("backup generation member is not bound to the exact stamp")
    seen.add(relative)
    target = root.joinpath(*path.parts)
    resolved = target.resolve(strict=True)
    if (
        not resolved.is_relative_to(root)
        or not resolved.is_file()
        or target.is_symlink()
        or any(parent.is_symlink() for parent in target.parents if parent != root)
    ):
        raise SystemExit("backup generation member is unsafe")
if not seen:
    raise SystemExit("backup generation checksum manifest is empty")
PY
(
  cd "$BACKUP_DATA_ROOT"
  /usr/bin/sha256sum --strict --check "$BACKUP_GENERATION_MANIFEST"
) >"$WORK/raw/backup-sha256sum.log"
"$PYTHON_BASE" -I -S - "$BACKUP_DATA_ROOT" "$BACKUP_GENERATION_MANIFEST" \
  "$PG_RESTORE" "$SQLITE3" "$WORK/raw/backup-logical-checks.json" <<'PY'
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
manifest = Path(sys.argv[2])
pg_restore = Path(sys.argv[3])
sqlite3 = Path(sys.argv[4])
output = Path(sys.argv[5])
checks = []
for line in manifest.read_text(encoding="utf-8").splitlines():
    _digest, separator, relative = line.partition("  ")
    if not separator:
        raise SystemExit("backup manifest changed before logical verification")
    relative_path = PurePosixPath(relative)
    target = root.joinpath(*relative_path.parts).resolve(strict=True)
    if not target.is_relative_to(root):
        raise SystemExit("backup logical-check target escaped root")
    if relative_path.suffix == ".dump":
        completed = subprocess.run(
            [str(pg_restore), "--list", str(target)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not completed.stdout or completed.stderr:
            raise SystemExit("pg_restore --list returned empty output or warnings")
        checks.append({
            "kind": "pg_restore_list",
            "relative_path_sha256": hashlib.sha256(relative.encode()).hexdigest(),
            "output_sha256": hashlib.sha256(completed.stdout).hexdigest(),
            "output_bytes": len(completed.stdout),
        })
    elif relative_path.suffix == ".db":
        completed = subprocess.run(
            [str(sqlite3), "-batch", "-readonly", str(target), "PRAGMA integrity_check;"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.stdout.strip() != "ok" or completed.stderr:
            raise SystemExit("SQLite backup integrity_check did not return exact ok")
        checks.append({
            "kind": "sqlite_integrity_check",
            "relative_path_sha256": hashlib.sha256(relative.encode()).hexdigest(),
            "result_sha256": hashlib.sha256(b"ok\n").hexdigest(),
        })
    else:
        raise SystemExit("backup member has no logical verifier")
if not checks or len(checks) != len(manifest.read_text(encoding="utf-8").splitlines()):
    raise SystemExit("backup logical-check inventory is incomplete")
output.write_text(
    json.dumps({
        "schema_version": 1,
        "result": "PASS",
        "check_count": len(checks),
        "pg_restore_count": sum(item["kind"] == "pg_restore_list" for item in checks),
        "sqlite_count": sum(item["kind"] == "sqlite_integrity_check" for item in checks),
        "checks": checks,
    }, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY

"$PYTHON_BASE" -I -S - "$BACKUP_HANDLE" "$BACKUP_ROOT" "$MAIN_A_SHA" "$MAIN_B_SHA" \
  "$B_ARCHIVE_SHA256" "$BACKUP_STATUS" "$BACKUP_DATA_ROOT" \
  "$BACKUP_GENERATION_MANIFEST" "$BACKUP_GENERATION_RESULT" \
  "$WORK/raw/backup-sha256sum.log" "$WORK/raw/backup-logical-checks.json" \
  "$PG_RESTORE_SHA256" "$SQLITE3_SHA256" "$WORK/fragments/backup.json" <<'PY'
import datetime,hashlib,json,pathlib,re,sys
h=pathlib.Path(sys.argv[1]).resolve(); root=pathlib.Path(sys.argv[2]).resolve()
a,b,digest,status_path,data_root,manifest_path,result_path,checksum_log_path,logical_path,pg_restore_sha,sqlite_sha,out=sys.argv[3:]
if h.parent!=root or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}-to-[0-9a-f]{12}-[0-9a-f]{16}",h.name): raise SystemExit("backup handle identity invalid")
def env(path):
    path=pathlib.Path(path)
    result={}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#"):
            k,sep,v=line.partition("=")
            if not sep or k in result: raise SystemExit(f"invalid evidence env: {path.name}")
            result[k]=v
    return result
r=env(h/"release.env"); approval=env(h/"approval.env"); backup=env(pathlib.Path(status_path))
generation=env(pathlib.Path(result_path)); manifest=pathlib.Path(manifest_path); checksum_log=pathlib.Path(checksum_log_path)
logical_path=pathlib.Path(logical_path); logical=json.loads(logical_path.read_text())
if r.get("OLD_SHA")!=a or r.get("NEW_SHA")!=b or r.get("STATE")!="deployed": raise SystemExit("deploy release manifest mismatch")
if approval.get("source_sha")!=b or approval.get("artifact_sha256")!=digest or not approval.get("ci_run_id","").isdigit(): raise SystemExit("approval binding mismatch")
if backup.get("status")!="success" or backup.get("checksum_ok")!="1" or int(backup.get("file_count","0"))<9: raise SystemExit("verified backup status mismatch")
stamp=backup.get("stamp","")
if not re.fullmatch(r"20[0-9]{6}_[0-9]{6}",stamp): raise SystemExit("backup stamp mismatch")
manifest_lines=manifest.read_text().splitlines()
manifest_members=[]
for line in manifest_lines:
    match=re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)",line)
    if not match: raise SystemExit("backup generation manifest changed after preflight")
    manifest_members.append((match.group(1),match.group(2)))
generation_count=int(generation.get("file_count","0")); backup_count=int(backup["file_count"])
if generation.get("stamp")!=stamp or generation.get("status")!="verified" or generation_count!=backup_count or len(manifest_members)!=backup_count: raise SystemExit("backup generation result/count mismatch")
if pathlib.Path(manifest_path).name!=f"generation_{stamp}.sha256" or pathlib.Path(result_path).name!=f"generation_{stamp}.result": raise SystemExit("backup generation evidence filename mismatch")
data=pathlib.Path(data_root).resolve()
total_bytes=sum((data/relative).stat().st_size for _digest,relative in manifest_members)
if int(generation.get("total_bytes","-1"))!=total_bytes: raise SystemExit("backup generation byte count mismatch")
checksum_lines=checksum_log.read_text().splitlines()
if len(checksum_lines)!=backup_count or any(line!=f"{relative}: OK" for line,(_digest,relative) in zip(checksum_lines,manifest_members,strict=True)): raise SystemExit("sha256sum generation verification log mismatch")
if logical.get("result")!="PASS" or logical.get("check_count")!=backup_count or logical.get("pg_restore_count")+logical.get("sqlite_count")!=backup_count: raise SystemExit("backup logical verification mismatch")
handle_epoch=int(datetime.datetime.strptime(h.name[:16],"%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.timezone.utc).timestamp())
deployed_epoch=int(datetime.datetime.fromisoformat(r["UPDATED_AT"].replace("Z","+00:00")).timestamp())
backup_started=int(backup.get("started_at","0")); backup_verified=int(generation.get("verified_at","0")); backup_completed=int(backup.get("completed_at","0")); claimed=int(approval.get("claimed_at_epoch","0"))
if not handle_epoch <= backup_started <= backup_verified <= backup_completed <= deployed_epoch: raise SystemExit("backup timestamps are not bound to this deploy handle")
if not handle_epoch <= claimed <= deployed_epoch: raise SystemExit("approval claim timestamp is not bound to this deploy handle")
source_hash=h/"source.sha256"; source_archive=h/f"source-{a}.tar.gz"
if not source_hash.is_file() or not source_archive.is_file(): raise SystemExit("rollback source backup missing")
parts=source_hash.read_text().split()
if len(parts)!=2 or pathlib.Path(parts[1]).name!=source_archive.name or hashlib.sha256(source_archive.read_bytes()).hexdigest()!=parts[0]: raise SystemExit("rollback source checksum mismatch")
payload={"schema_version":1,"result":"PASS","handle":str(h),"release_env_sha256":hashlib.sha256((h/"release.env").read_bytes()).hexdigest(),"approval_env_sha256":hashlib.sha256((h/"approval.env").read_bytes()).hexdigest(),"old_sha":a,"new_sha":b,"deployed_at":r["UPDATED_AT"],"ci_run_id":approval["ci_run_id"],"approval_claimed_at_epoch":claimed,"artifact_sha256":digest,"backup_stamp":stamp,"backup_started_at":backup_started,"backup_verified_at":backup_verified,"backup_completed_at":backup_completed,"backup_file_count":backup_count,"backup_total_bytes":total_bytes,"backup_last_run_sha256":hashlib.sha256(pathlib.Path(status_path).read_bytes()).hexdigest(),"backup_generation_manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),"backup_generation_result_sha256":hashlib.sha256(pathlib.Path(result_path).read_bytes()).hexdigest(),"backup_sha256sum_log_sha256":hashlib.sha256(checksum_log.read_bytes()).hexdigest(),"backup_logical_checks_sha256":hashlib.sha256(logical_path.read_bytes()).hexdigest(),"backup_pg_restore_count":logical["pg_restore_count"],"backup_sqlite_count":logical["sqlite_count"],"pg_restore_sha256":pg_restore_sha,"sqlite3_sha256":sqlite_sha,"rollback_source_sha256":parts[0]}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY

verify_python_runtime "$WORK/fragments/python-runtime-before.json"
"$PYTHON" -B -I - "$MIGRATION_ENV" "$LIVE_ROOT/backend/db/migrations/manifest.json" \
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
            if set(types) - {"retail.sales_generation_promoted.v1"}:
                raise SystemExit("protected outbox event type was activated in production")
    finally: await conn.close()
    pathlib.Path(sys.argv[3]).write_text(json.dumps({"schema_version":1,"result":"PASS","migration_count":len(actual),"last_migration":"069_ai_cohort_and_transactional_outbox.sql","migration_manifest":actual,"outbox_states":states,"outbox_event_types":types,"outbox_receipts":receipts,"oldest_pending_seconds":pending_age,"stale_processing":stale},sort_keys=True,separators=(",",":"))+"\n")
asyncio.run(main())
PY

service_snapshot() {
  local output="$1" evidence="$2" unit pid started started_epoch cwd exe cmdline cmdline_sha
  : >"$output"
  for unit in "${EXPECTED_UNITS[@]}"; do
    systemctl is-active --quiet "$unit" || die "service inactive: $unit"
    systemctl is-enabled --quiet "$unit" || die "service disabled: $unit"
    [[ "$(systemctl show "$unit" --property=NRestarts --value)" == "0" ]] \
      || die "service has restarted since activation: $unit"
    [[ "$(systemctl show "$unit" --property=ActiveEnterTimestampMonotonic --value)" =~ ^[1-9][0-9]*$ ]] \
      || die "service activation timestamp is unavailable: $unit"
    pid="$(systemctl show "$unit" --property=MainPID --value)"
    [[ "$pid" =~ ^[1-9][0-9]*$ && -d "/proc/$pid" ]] \
      || die "service MainPID is unavailable: $unit"
    started="$(systemctl show "$unit" --property=ExecMainStartTimestamp --value)"
    started_epoch="$(date --date "$started" +%s)"
    (( DEPLOY_HANDLE_EPOCH <= started_epoch && started_epoch <= DEPLOYED_EPOCH )) \
      || die "service did not start inside the exact deploy interval: $unit"
    cwd="$(readlink -f "/proc/$pid/cwd")"
    exe="$(readlink -f "/proc/$pid/exe")"
    [[ "$cwd" == "$LIVE_ROOT/backend" && "$exe" == "$PYTHON_BASE" ]] \
      || die "service process is not bound to the deployed backend/Python: $unit"
    cmdline="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
    case "$unit" in
      unihub-backend.service) [[ "$cmdline" == *" -m uvicorn main:app "* ]] \
        || die "backend process command mismatch" ;;
      *) [[ "$cmdline" == *" worker.py"* ]] \
        || die "worker process command mismatch: $unit" ;;
    esac
    cmdline_sha="$(printf '%s' "$cmdline" | sha256sum | awk '{print $1}')"
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$unit" "$pid" "$started_epoch" "$cwd" "$exe" \
      "$cmdline_sha" >>"$output"
  done
  "$PYTHON_BASE" -I -S - "$output" "$DEPLOY_HANDLE_EPOCH" "$DEPLOYED_EPOCH" "$evidence" <<'PY'
import json,pathlib,sys
source=pathlib.Path(sys.argv[1]); lower=int(sys.argv[2]); upper=int(sys.argv[3]); out=pathlib.Path(sys.argv[4])
services=[]
for line in source.read_text().splitlines():
    unit,pid,started,cwd,exe,command_sha=line.split("\t")
    started_epoch=int(started)
    if not lower <= started_epoch <= upper: raise SystemExit("service start escaped deploy interval")
    services.append({"unit":unit,"main_pid":int(pid),"start_epoch":started_epoch,"cwd":cwd,"exe":exe,"command_sha256":command_sha})
if len(services)!=6 or len({item["unit"] for item in services})!=6: raise SystemExit("service inventory mismatch")
out.write_text(json.dumps({"schema_version":1,"result":"PASS","deploy_handle_epoch":lower,"deploy_completed_epoch":upper,"services":services},sort_keys=True,separators=(",",":"))+"\n")
PY
}
service_snapshot "$WORK/raw/services-before.txt" "$WORK/fragments/services-runtime-before.json"

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
  local name="$1" base="$2" path="$3" expected="$4" cookie="${5:-}" body status started duration cookie_kind
  local -a cookie_args=()
  is_allowed_path "$path" || die "unexpected non-read-only probe path: $path"
  body="$WORK/raw/http-${name}.body"
  started="$(date +%s%N)"
  if [[ -n "$cookie" ]]; then
    if [[ "$cookie" == "$MANAGER_COOKIE_FILE" ]]; then
      cookie_kind="$MANAGER_COOKIE_KIND"
    elif [[ "$cookie" == "$FORBIDDEN_COOKIE_FILE" ]]; then
      cookie_kind="$FORBIDDEN_COOKIE_KIND"
    else
      die "probe cookie is outside the verified cookie inventory"
    fi
    if [[ "$cookie_kind" == "raw-header" ]]; then
      cookie_args=(--header "@$cookie")
    else
      cookie_args=(--cookie "$cookie")
    fi
    status="$(curl --silent --show-error --location --max-redirs 0 --max-time 15 \
      --request GET "${cookie_args[@]}" --output "$body" --write-out '%{http_code}' "$base$path")"
  else
    status="$(curl --silent --show-error --location --max-redirs 0 --max-time 15 \
      --request GET --output "$body" --write-out '%{http_code}' "$base$path")"
  fi
  duration="$(( ($(date +%s%N) - started) / 1000000 ))"
  [[ "$status" == "$expected" ]] || die "probe $name returned $status, expected $expected"
  "$PYTHON_BASE" -I -S - "$name" "$path" "$status" "$duration" "$body" \
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

probe_authenticated_browser() {
  "$PYTHON_BASE" -I -S - "$BROWSER_CHROME" "$BROWSER_CHROME_SHA256" \
    "$BROWSER_CHROME_VERSION" "$MANAGER_COOKIE_FILE" "$PUBLIC_BASE" \
    "$WORK/fragments/browser.json" <<'PY'
from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path
import pwd
import select
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


chrome_path = Path(sys.argv[1])
chrome_sha256, chrome_version = sys.argv[2:4]
cookie_path = Path(sys.argv[4])
base_url, output_path = sys.argv[5:]


def browser_cookies(path: Path, url: str) -> list[dict[str, object]]:
    raw = path.read_text(encoding="utf-8").strip()
    target = urlsplit(url)
    host = (target.hostname or "").lower()
    if target.scheme != "https" or host != "retail.unihub.ro":
        raise SystemExit("manager browser cookie target is not canonical Retail HTTPS")
    active: list[tuple[str, bool]] = []
    for original in raw.splitlines():
        if original.startswith("#HttpOnly_"):
            active.append((original[len("#HttpOnly_") :], True))
        elif original and not original.startswith("#"):
            active.append((original, False))
    if not active:
        raise SystemExit("manager browser cookie input is empty")
    result: list[dict[str, object]] = []
    if any("\t" in line for line, _http_only in active):
        for line, http_only in active:
            parts = line.split("\t")
            if len(parts) != 7:
                raise SystemExit("manager Netscape cookie record is malformed")
            domain_raw, include_raw, cookie_path_value, secure_raw, expiry_raw, name, value = parts
            domain = domain_raw.lower()
            if domain not in {"retail.unihub.ro", ".retail.unihub.ro"}:
                raise SystemExit("manager browser rejected a non-Retail cookie")
            if include_raw not in {"TRUE", "FALSE"} or secure_raw != "TRUE":
                raise SystemExit("manager browser cookie flags are invalid")
            normalized_domain = domain.lstrip(".")
            if (include_raw == "TRUE") != domain.startswith("."):
                raise SystemExit("manager browser cookie domain flag is inconsistent")
            if not (
                host == normalized_domain
                or (include_raw == "TRUE" and host.endswith("." + normalized_domain))
            ):
                raise SystemExit("manager browser cookie domain does not match Retail")
            if cookie_path_value != "/":
                raise SystemExit("manager browser cookie path does not match Retail root")
            try:
                expiry = int(expiry_raw)
            except ValueError as exc:
                raise SystemExit("manager browser cookie expiry is malformed") from exc
            if expiry < 0 or (expiry and expiry <= int(time.time())):
                raise SystemExit("manager browser cookie is expired")
            cookie: dict[str, object] = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie_path_value,
                "secure": True,
                "httpOnly": http_only,
            }
            if expiry:
                cookie["expires"] = float(expiry)
            result.append(cookie)
    else:
        if (
            len(active) != 1
            or len(raw.splitlines()) != 1
            or not active[0][0].lower().startswith("cookie:")
        ):
            raise SystemExit("manager raw cookie must be one strict Cookie header")
        header = active[0][0].split(":", 1)[1].strip()
        for item in header.split(";"):
            name, separator, value = item.strip().partition("=")
            if not separator or not name or any(char.isspace() for char in name):
                raise SystemExit("manager raw cookie contains an invalid pair")
            result.append({"name": name, "value": value, "url": url, "secure": True})
    return result


if hashlib.sha256(chrome_path.read_bytes()).hexdigest() != chrome_sha256:
    raise SystemExit("browser digest changed")
version = subprocess.check_output([str(chrome_path), "--version"], text=True).strip()
if version != chrome_version:
    raise SystemExit("browser version changed")
if os.geteuid() != 0:
    raise SystemExit("browser controller must start as root before dropping browser privileges")
operator = pwd.getpwnam("andrei")
operator_uid = operator.pw_uid
operator_gid = operator.pw_gid

profile = tempfile.mkdtemp(prefix="retail-ac17-browser-")
os.chown(profile, operator_uid, operator_gid)
os.chmod(profile, 0o700)
raw_command_read, raw_command_write = os.pipe()
raw_response_read, raw_response_write = os.pipe()
# Preserve all four ends above the conventional descriptor range, then bind
# only Chromium's private CDP ends to FD 3/4 before spawning. Passing those
# exact descriptors keeps close_fds from discarding the channel.
high_command_read = fcntl.fcntl(raw_command_read, fcntl.F_DUPFD_CLOEXEC, 10)
command_write = fcntl.fcntl(raw_command_write, fcntl.F_DUPFD_CLOEXEC, 10)
response_read = fcntl.fcntl(raw_response_read, fcntl.F_DUPFD_CLOEXEC, 10)
high_response_write = fcntl.fcntl(raw_response_write, fcntl.F_DUPFD_CLOEXEC, 10)
for descriptor in (
    raw_command_read,
    raw_command_write,
    raw_response_read,
    raw_response_write,
):
    os.close(descriptor)
os.dup2(high_command_read, 3)
os.dup2(high_response_write, 4)
os.close(high_command_read)
os.close(high_response_write)
browser_command_read = 3
browser_response_write = 4
os.set_inheritable(browser_command_read, True)
os.set_inheritable(browser_response_write, True)


def configure_browser_child() -> None:
    os.setsid()
    os.setgroups([])
    os.setgid(operator_gid)
    os.setuid(operator_uid)


process: subprocess.Popen[bytes] | None = None
try:
    process = subprocess.Popen(
        [
            str(chrome_path),
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-default-apps",
            "--disable-sync",
            "--no-first-run",
            "--remote-debugging-pipe",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={
            "HOME": operator.pw_dir,
            "USER": operator.pw_name,
            "LOGNAME": operator.pw_name,
            "PATH": "/usr/bin:/bin",
        },
        pass_fds=(3, 4),
        preexec_fn=configure_browser_child,
    )
    os.close(browser_command_read)
    browser_command_read = -1
    os.close(browser_response_write)
    browser_response_write = -1

    incoming = bytearray()
    sequence = [0]
    observed_same_origin_methods: set[str] = set()

    def send_message(payload: dict[str, object]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\0"
        while data:
            written = os.write(command_write, data)
            if written <= 0:
                raise RuntimeError("browser CDP command pipe closed")
            data = data[written:]

    def receive_message(deadline: float) -> dict[str, object]:
        while True:
            marker = incoming.find(0)
            if marker >= 0:
                raw = bytes(incoming[:marker])
                del incoming[: marker + 1]
                if not raw:
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise RuntimeError("browser CDP emitted a non-object message")
                return value
            if process is None or process.poll() is not None:
                raise RuntimeError("pinned browser exited before CDP response")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("browser CDP response timed out")
            readable, _, _ = select.select([response_read], [], [], remaining)
            if not readable:
                raise TimeoutError("browser CDP response timed out")
            chunk = os.read(response_read, 65536)
            if not chunk:
                raise RuntimeError("browser CDP response pipe closed")
            incoming.extend(chunk)

    def command(
        method: str,
        params: dict[str, object] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, object]:
        sequence[0] += 1
        request_id = sequence[0]
        request: dict[str, object] = {
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        if session_id is not None:
            request["sessionId"] = session_id
        send_message(request)
        deadline = time.monotonic() + 15
        while True:
            response = receive_message(deadline)
            if response.get("method") == "Network.requestWillBeSent":
                network_request = response.get("params", {}).get("request", {})
                if not isinstance(network_request, dict):
                    raise RuntimeError("browser emitted malformed network evidence")
                request_url = str(network_request.get("url", ""))
                request_method = str(network_request.get("method", "")).upper()
                if request_url.startswith(base_url):
                    observed_same_origin_methods.add(request_method)
                    if request_method not in {"GET", "HEAD"}:
                        raise RuntimeError(
                            "browser attempted a non-read-only same-origin request"
                        )
                continue
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise RuntimeError(f"CDP command failed: {method}")
            result = response.get("result", {})
            if not isinstance(result, dict):
                raise RuntimeError(f"CDP command returned malformed result: {method}")
            return result

    targets = command("Target.getTargets").get("targetInfos", [])
    page_target = next(
        (
            item
            for item in targets
            if isinstance(item, dict) and item.get("type") == "page"
        ),
        None,
    )
    if page_target is None:
        target_id = str(command("Target.createTarget", {"url": "about:blank"})["targetId"])
    else:
        target_id = str(page_target["targetId"])
    page_session = str(
        command(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )["sessionId"]
    )

    def page_command(
        method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]:
        return command(method, params, session_id=page_session)

    def evaluate(expression: str) -> object:
        result = page_command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        return result.get("result", {}).get("value")

    def wait_for_text(marker: str) -> None:
        encoded = json.dumps(marker)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if evaluate(f"document.body?.innerText.includes({encoded}) === true"):
                body = str(evaluate("document.body?.innerText || ''"))
                forbidden = (
                    "Nu ești autentificat",
                    "nu a putut fi afișată",
                    "nu a putut afisa aplicația",
                )
                if any(value in body for value in forbidden):
                    raise RuntimeError("authenticated browser reached a fatal UI state")
                return
            time.sleep(0.25)
        raise TimeoutError(f"browser marker did not appear: {marker}")

    def drain_network_events(seconds: float = 2.0) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                response = receive_message(min(deadline, time.monotonic() + 0.25))
            except TimeoutError:
                continue
            if response.get("method") != "Network.requestWillBeSent":
                continue
            network_request = response.get("params", {}).get("request", {})
            if not isinstance(network_request, dict):
                raise RuntimeError("browser emitted malformed network evidence")
            request_url = str(network_request.get("url", ""))
            request_method = str(network_request.get("method", "")).upper()
            if request_url.startswith(base_url):
                observed_same_origin_methods.add(request_method)
                if request_method not in {"GET", "HEAD"}:
                    raise RuntimeError(
                        "browser attempted a delayed non-read-only same-origin request"
                    )

    def click_button(label: str) -> None:
        encoded = json.dumps(label)
        clicked = evaluate(
            "(() => { const visible = e => { const r=e.getBoundingClientRect(); "
            "const s=getComputedStyle(e); return r.width>0 && r.height>0 && s.visibility!=='hidden' "
            "&& s.display!=='none'; }; const b=[...document.querySelectorAll('button')]"
            f".find(e => visible(e) && (e.textContent?.trim()==={encoded} || "
            f"[...e.querySelectorAll('span')].some(s => s.textContent?.trim()==={encoded}))); "
            "if (!b) return false; b.click(); return true; })()"
        )
        if clicked is not True:
            raise RuntimeError(f"visible browser button not found: {label}")

    checkpoints: list[dict[str, str]] = []

    def exercise_journey(*, mobile: bool) -> None:
        names = {
            "dashboard": "mobile-dashboard" if mobile else "dashboard",
            "grile": "mobile-grile-v2" if mobile else "grile-v2",
            "target": "mobile-target" if mobile else "target",
            "salary": "mobile-salary-read" if mobile else "salary-read",
            "imports": "mobile-imports" if mobile else "imports",
            "exports": "mobile-exports-read" if mobile else "exports-read",
        }
        page_command("Page.navigate", {"url": base_url})
        wait_for_text("Sales Hub")
        if mobile:
            mobile_nav = evaluate(
                "(() => { const e=document.querySelector('.mobile-bottom-nav'); "
                "return !!e && getComputedStyle(e).display!=='none' "
                "&& e.getBoundingClientRect().height>0; })()"
            )
            if mobile_nav is not True:
                raise RuntimeError("mobile navigation is not visibly rendered")
        checkpoints.append({"surface": names["dashboard"], "marker": "Sales Hub"})

        click_button("Agenti")
        wait_for_text("Prezentare generală")
        click_button("Grile")
        wait_for_text("Grila actuală")
        click_button("V2 · pilot")
        wait_for_text("Grile V2 · pilot")
        checkpoints.append(
            {"surface": names["grile"], "marker": "Grile V2 · pilot"}
        )

        click_button("Management")
        wait_for_text("Manageri")
        click_button("Calculator Target")
        wait_for_text("Calculator Target")
        checkpoints.append(
            {"surface": names["target"], "marker": "Calculator Target"}
        )
        click_button("Salarii")
        wait_for_text("Statistici Salarii")
        checkpoints.append(
            {"surface": names["salary"], "marker": "Statistici Salarii"}
        )

        click_button("Setari")
        wait_for_text("Preferințe")
        click_button("Importuri")
        wait_for_text("Import fișier vânzări")
        checkpoints.append(
            {"surface": names["imports"], "marker": "Import fișier vânzări"}
        )
        click_button("Exporturi")
        wait_for_text("Builder export Excel")
        checkpoints.append(
            {"surface": names["exports"], "marker": "Builder export Excel"}
        )

    page_command("Network.enable")
    page_command(
        "Network.setCookies",
        {"cookies": browser_cookies(cookie_path, base_url)},
    )
    page_command("Page.enable")
    page_command("Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
    exercise_journey(mobile=False)

    page_command("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
    exercise_journey(mobile=True)
    drain_network_events()
finally:
    for descriptor in (browser_command_read, browser_response_write, command_write, response_read):
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    shutil.rmtree(profile, ignore_errors=True)

payload = {
    "schema_version": 1,
    "result": "PASS",
    "browser": chrome_version,
    "browser_sha256": chrome_sha256,
    "authenticated": True,
    "desktop_viewport": [1440, 900],
    "mobile_viewport": [390, 844],
    "checkpoints": checkpoints,
    "same_origin_http_methods": sorted(observed_same_origin_methods),
    "interaction_mode": "navigation_only",
    "control_transport": "private_cdp_pipe",
    "browser_uid": operator_uid,
    "sandbox_bypass": False,
    "business_mutations": 0,
    "final_network_drain_seconds": 2.0,
    "salary_export_executed": False,
    "cookie_recorded": False,
}
Path(output_path).write_text(
    json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
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
probe_authenticated_browser
sleep 60
probe_health_round 1
sleep 60
probe_health_round 2
service_snapshot "$WORK/raw/services-after.txt" "$WORK/fragments/services-runtime-after.json"
cmp -s "$WORK/raw/services-before.txt" "$WORK/raw/services-after.txt" \
  || die "one or more Retail services restarted during AC-17 observation"

curl --fail --silent --show-error --max-time 15 --request GET \
  "$PROMETHEUS_BASE/api/v1/targets" >"$WORK/raw/prom-targets.json"
curl --fail --silent --show-error --max-time 15 --request GET \
  "$PROMETHEUS_BASE/api/v1/rules" >"$WORK/raw/prom-rules.json"
curl --fail --silent --show-error --max-time 15 --request GET --get \
  --data-urlencode 'query={__name__=~"^(?:retail_outbox_oldest_pending_seconds|retail_outbox_head_blocked|retail_outbox_completed_total|retail_outbox_failed_total|retail_outbox_delivery_duration_seconds_(?:bucket|count|sum))$"}' \
  "$PROMETHEUS_BASE/api/v1/query" >"$WORK/raw/prom-outbox.json"
curl --fail --silent --show-error --max-time 15 --request GET --get \
  --data-urlencode 'query=unihub_glitchtip_events_1h{project="unihub-retail"}' \
  "$PROMETHEUS_BASE/api/v1/query" >"$WORK/raw/prom-glitchtip.json"
verify_prometheus_payloads \
  "$WORK/raw/prom-targets.json" "$WORK/raw/prom-rules.json" \
  "$WORK/raw/prom-outbox.json" "$WORK/raw/prom-glitchtip.json" \
  "$WORK/fragments/prometheus.json"

JOURNAL_ARGS=()
for unit in "${EXPECTED_UNITS[@]}"; do JOURNAL_ARGS+=("--unit=$unit"); done
journalctl --no-pager --since "$DEPLOYED_AT" --output=short-iso \
  "${JOURNAL_ARGS[@]}" >"$WORK/raw/journal.txt"
"$PYTHON_BASE" -I -S - "$WORK/raw/journal.txt" "$WORK/fragments/journal.json" <<'PY'
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

"$PYTHON_BASE" -I -S - "$LIVE_ROOT" "$MAIN_B_SHA" "$GITHUB_ORIGIN_URL" \
  "$WORK/fragments/refs-primary.json" <<'PY'
import hashlib,json,pathlib,subprocess,sys
root,sha,canonical_origin,out=sys.argv[1:]
blocked_branches={
 "codex/retail-definitive-closure-20260812",
 "codex/retail-definitive-closure-b-20260813",
 "codex/retail-close-authority","codex/retail-close-contracts",
 "codex/retail-close-correctness","codex/retail-close-frontend",
 "codex/retail-close-outbox-contract","codex/retail-close-preview-v3",
 "codex/retail-close-scale-authority",
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
origin=git("remote","get-url","origin")
refs=git("for-each-ref","--format=%(refname) %(objectname)","refs/heads","refs/remotes/origin").splitlines()
worktrees=git("worktree","list","--porcelain").splitlines()
bad_refs=[line for line in refs if line.split()[0].removeprefix("refs/heads/").removeprefix("refs/remotes/origin/") in blocked_branches]
bad_worktrees=[line for line in worktrees if (line.startswith("worktree ") and line[9:] in blocked_worktrees) or (line.startswith("branch refs/heads/") and line[18:] in blocked_branches)]
if origin!=canonical_origin or git("rev-parse","HEAD")!=sha or git("rev-parse","origin/main")!=sha or git("branch","--show-current")!="main" or git("status","--porcelain=v1","--untracked-files=all") or bad_refs or bad_worktrees:
 raise SystemExit("primary Git/task-ref reconciliation failed")
payload={"schema_version":1,"result":"PASS","host":"server","head":sha,"origin_main":sha,"origin_url":origin,"branch":"main","status_clean":True,"refs_sha256":hashlib.sha256(("\n".join(refs)+"\n").encode()).hexdigest(),"worktree_manifest_sha256":hashlib.sha256(("\n".join(worktrees)+"\n").encode()).hexdigest(),"blocked_branches":sorted(blocked_branches),"blocked_worktrees":sorted(blocked_worktrees),"task_refs":[],"task_worktrees":[]}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY

DELL_RECONCILE_COMMAND="actual=\$(/usr/bin/sha256sum '$PYTHON_BASE'); actual=\${actual%% *}; [ \"\$actual\" = '$PYTHON_BASE_SHA256' ] || exit 91; exec /usr/bin/env -i HOME=/home/andrei PATH=/usr/bin:/bin PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1 '$PYTHON_BASE' -I -S - '$MAIN_B_SHA' '$GITHUB_ORIGIN_URL'"
sudo -u andrei ssh -o BatchMode=yes -o ConnectTimeout=10 dell-standby \
  "$DELL_RECONCILE_COMMAND" <<'PY' \
  | tee "$WORK/fragments/refs-dell.json" >/dev/null
import hashlib,json,pathlib,socket,subprocess,sys
sha,canonical_origin=sys.argv[1:]; root="/opt/Mobiup/unihub-retail"
blocked_branches={
 "codex/retail-definitive-closure-20260812",
 "codex/retail-definitive-closure-b-20260813",
 "codex/retail-close-authority","codex/retail-close-contracts",
 "codex/retail-close-correctness","codex/retail-close-frontend",
 "codex/retail-close-outbox-contract","codex/retail-close-preview-v3",
 "codex/retail-close-scale-authority",
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
origin=git("remote","get-url","origin")
refs=git("for-each-ref","--format=%(refname) %(objectname)","refs/heads","refs/remotes/origin").splitlines()
worktrees=git("worktree","list","--porcelain").splitlines()
remote_heads=git("ls-remote","--heads","origin").splitlines()
bad_refs=[line for line in refs if line.split()[0].removeprefix("refs/heads/").removeprefix("refs/remotes/origin/") in blocked_branches]
bad_remote=[line for line in remote_heads if line.split()[1].removeprefix("refs/heads/") in blocked_branches]
bad_worktrees=[line for line in worktrees if (line.startswith("worktree ") and line[9:] in blocked_worktrees) or (line.startswith("branch refs/heads/") and line[18:] in blocked_branches)]
if socket.gethostname()!="dell-standby" or origin!=canonical_origin or git("rev-parse","HEAD")!=sha or git("rev-parse","origin/main")!=sha or git("branch","--show-current")!="main" or git("status","--porcelain=v1","--untracked-files=all") or bad_refs or bad_remote or bad_worktrees:
 raise SystemExit("Dell Git/task-ref reconciliation failed")
print(json.dumps({"schema_version":1,"result":"PASS","host":"dell-standby","head":sha,"origin_main":sha,"origin_url":origin,"branch":"main","status_clean":True,"refs_sha256":hashlib.sha256(("\n".join(refs)+"\n").encode()).hexdigest(),"remote_heads_sha256":hashlib.sha256(("\n".join(remote_heads)+"\n").encode()).hexdigest(),"worktree_manifest_sha256":hashlib.sha256(("\n".join(worktrees)+"\n").encode()).hexdigest(),"blocked_branches":sorted(blocked_branches),"blocked_worktrees":sorted(blocked_worktrees),"task_refs":[],"task_remote_refs":[],"task_worktrees":[]},sort_keys=True,separators=(",",":")))
PY

sudo -u andrei /usr/bin/env GH_HOST=github.com GH_PAGER=cat NO_COLOR=1 GH_PROMPT_DISABLED=1 \
  "$GH_BIN" pr view "$RELEASE_A_PR" --repo "$GITHUB_REPOSITORY" \
  --json number,state,isDraft,headRefName,baseRefName,mergeCommit,url \
  | tee "$WORK/raw/pr-a.json" >/dev/null
sudo -u andrei /usr/bin/env GH_HOST=github.com GH_PAGER=cat NO_COLOR=1 GH_PROMPT_DISABLED=1 \
  "$GH_BIN" pr view "$RELEASE_B_PR" --repo "$GITHUB_REPOSITORY" \
  --json number,state,isDraft,headRefName,baseRefName,mergeCommit,url \
  | tee "$WORK/raw/pr-b.json" >/dev/null
sudo -u andrei git -C "$LIVE_ROOT" ls-remote --heads origin \
  refs/heads/main "refs/heads/$TASK_A_BRANCH" "refs/heads/$TASK_B_BRANCH" \
  | tee "$WORK/raw/task-remote-heads.txt" >/dev/null
"$PYTHON_BASE" -I -S - "$WORK/raw/pr-a.json" "$WORK/raw/pr-b.json" \
  "$WORK/raw/task-remote-heads.txt" "$MAIN_A_SHA" "$MAIN_B_SHA" \
  "$RELEASE_A_PR" "$RELEASE_B_PR" "$TASK_A_BRANCH" "$TASK_B_BRANCH" \
  "$WORK/fragments/refs-github.json" <<'PY'
import hashlib,json,pathlib,sys
pa,pb,heads,a,b,an,bn,ab,bb,out=sys.argv[1:]
av=json.loads(pathlib.Path(pa).read_text()); bv=json.loads(pathlib.Path(pb).read_text())
def valid(value,number,branch,sha):
 return value.get("number")==int(number) and value.get("state")=="MERGED" and value.get("isDraft") is False and value.get("headRefName")==branch and value.get("baseRefName")=="main" and value.get("mergeCommit",{}).get("oid")==sha
remote=pathlib.Path(heads).read_text()
remote_lines=remote.splitlines()
if remote_lines != [f"{b}\trefs/heads/main"]: raise SystemExit("GitHub main/task-ref reconciliation failed")
if not valid(av,an,ab,a) or not valid(bv,bn,bb,b): raise SystemExit("GitHub PR reconciliation failed")
payload={"schema_version":1,"result":"PASS","repository":"anervalens-netizen/unihub-retail","remote_main":b,"release_a":{"number":int(an),"branch":ab,"merge_sha":a,"state":"MERGED"},"release_b":{"number":int(bn),"branch":bb,"merge_sha":b,"state":"MERGED"},"task_remote_heads":[],"queries_sha256":hashlib.sha256(pathlib.Path(pa).read_bytes()+pathlib.Path(pb).read_bytes()+pathlib.Path(heads).read_bytes()).hexdigest()}
pathlib.Path(out).write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
PY
rm -f -- "$WORK/raw/pr-a.json" "$WORK/raw/pr-b.json" "$WORK/raw/task-remote-heads.txt"

verify_python_runtime "$WORK/fragments/python-runtime-after.json" \
  "$WORK/fragments/python-runtime-before.json"

"$PYTHON_BASE" -I -S - "$WORK" "$EVIDENCE" "$MAIN_A_SHA" "$MAIN_B_SHA" "$SCRIPT_PATH" \
  "$A_ARTIFACT_DIR" "$B_ARTIFACT_DIR" "$BACKUP_HANDLE" "$PROBE_MONTH" \
  "$PYTHON_BASE_SHA256" "$GH_BIN_SHA256" <<'PY'
import hashlib,json,pathlib,sys,time
work,evidence,a,b,script,adir,bdir,backup,month,python_sha,gh_sha=sys.argv[1:]
w=pathlib.Path(work); fragments={}
for p in sorted((w/"fragments").glob("*.json")):
    value=json.loads(p.read_text())
    if value.get("result") not in (None,"PASS"): raise SystemExit(f"non-PASS fragment: {p.name}")
    fragments[p.name] = {"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"evidence":value}
required={"release-a-verification.json","release-b-artifact.json","deploy-entrypoint.json","deploy-entrypoint-bootstrap.json","rollback-python-runtime.json","rollback-python-supply.json","backup.json","cookie-scope.json","python-runtime-before.json","python-runtime-after.json","schema-outbox.json","prometheus.json","journal.json","refs-primary.json","refs-dell.json","refs-github.json","browser.json","http-dashboard.json","http-target.json","http-salary-agents.json","http-salary-records.json","http-grile.json","http-settings-imports.json","http-settings-exports.json","http-settings-resumable.json","http-salary-forbidden.json"}
required |= {f"http-{where}-{kind}-{n}.json" for n in range(3) for where in ("local","public") for kind in (("livez","readyz") if where=="local" else ("health","readyz"))}
missing=sorted(required-set(fragments))
if missing: raise SystemExit(f"AC-17 fragment inventory incomplete: {missing}")
raw_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((w/"raw").iterdir()) if p.is_file()}
payload={"schema_version":1,"result":"PASS","main_a_sha":a,"main_b_sha":b,"probe_month":month,"observed_seconds":120,"verified_at_epoch":int(time.time()),"verifier":{"path":"scripts/verify_deployed_release.sh","sha256":hashlib.sha256(pathlib.Path(script).read_bytes()).hexdigest()},"toolchain":{"python":{"path":"/usr/bin/python3.12","sha256":python_sha},"gh":{"path":"/usr/bin/gh","sha256":gh_sha}},"external_inputs":{"release_a_artifact_dir":str(pathlib.Path(adir).resolve()),"release_b_artifact_dir":str(pathlib.Path(bdir).resolve()),"backup_handle":str(pathlib.Path(backup).resolve())},"commands":{"http_method":"GET only","health_rounds":[0,60,120],"database_transaction":"READ ONLY","journal_since":"backup release UPDATED_AT"},"fragments":fragments,"raw_output_sha256":raw_hashes,"salary_export_executed":False,"finance_apply_executed":False,"target_finalize_executed":False,"grile_destructive_executed":False,"deployment_mutation_executed":False,"cookies_recorded":False}
dest=pathlib.Path(evidence); dest.mkdir(mode=0o700)
(dest/"evidence.json").write_text(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n")
for p in sorted((w/"fragments").glob("*.json")): (dest/p.name).write_bytes(p.read_bytes())
PY

chmod -R go-rwx "$EVIDENCE"
printf 'AC-17 deployed release verification PASS: %s (%s)\n' "$MAIN_B_SHA" "$EVIDENCE"
