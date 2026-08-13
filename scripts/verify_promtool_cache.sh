#!/usr/bin/bash -p

set -Eeuo pipefail

unset \
  PYTHONHOME PYTHONPATH PYTHONSTARTUP PYTHONINSPECT \
  MYPYPATH MYPY_CONFIG_FILE \
  NODE_OPTIONS NODE_PATH \
  BASH_ENV ENV CDPATH GLOBIGNORE || true
export PYTHONNOUSERSITE=1 PYTHONSAFEPATH=1

PYTHON="/usr/bin/python3.12"
PYTHON_SHA256="1643dacd9feaedc58f3cc581e4d22577dfe25c09b10282936186ccf0f2e61118"
[[ -x "$PYTHON" \
  && "$(sha256sum "$PYTHON" | awk '{print $1}')" == "$PYTHON_SHA256" ]] || {
  printf 'Pinned Python runtime unavailable.\n' >&2
  exit 1
}

usage() {
  printf '%s\n' \
    "usage: ${0##*/} prepare --version VERSION --sha256 SHA --cache-dir DIR --destination FILE --evidence FILE" \
    "       ${0##*/} self-test --evidence FILE" >&2
}

write_evidence() {
  local path="$1" version="$2" source="$3" downloads="$4" archive_sha="$5" binary_sha="$6"
  mkdir -p "$(dirname "$path")"
  "$PYTHON" -I -S - "$path" "$version" "$source" "$downloads" "$archive_sha" "$binary_sha" <<'PY'
import json
from pathlib import Path
import sys

path, version, source, downloads, archive_sha, binary_sha = sys.argv[1:]
payload = {
    "schema_version": 1,
    "result": "PASS",
    "version": version,
    "source": source,
    "download_count": int(downloads),
    "archive_sha256": archive_sha,
    "promtool_sha256": binary_sha,
}
Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
}

prepare() {
  local version="" expected_sha="" cache_dir="" destination="" evidence=""
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --version) version="$2"; shift 2 ;;
      --sha256) expected_sha="$2"; shift 2 ;;
      --cache-dir) cache_dir="$2"; shift 2 ;;
      --destination) destination="$2"; shift 2 ;;
      --evidence) evidence="$2"; shift 2 ;;
      *) usage; return 2 ;;
    esac
  done
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'Invalid Prometheus version.\n' >&2; return 2; }
  [[ "$expected_sha" =~ ^[0-9a-f]{64}$ ]] || { printf 'Invalid Prometheus SHA-256.\n' >&2; return 2; }
  [[ -n "$cache_dir" && -n "$destination" && -n "$evidence" ]] || { usage; return 2; }

  mkdir -p "$cache_dir" "$(dirname "$destination")"
  local source="" download_count=0 archive_sha="$expected_sha"
  local archive="$cache_dir/prometheus-${version}.linux-amd64.tar.gz"
  local lock="$cache_dir/prometheus-${version}.lock"
  exec 9>"$lock"
  flock 9
  if [[ ! -f "$archive" ]] \
      || ! printf '%s  %s\n' "$expected_sha" "$archive" | sha256sum --check --status -; then
    local download_tmp
    download_tmp="$(mktemp "$cache_dir/.prometheus-download.XXXXXX")"
    if [[ -n "${PROMTOOL_TEST_SOURCE_ARCHIVE:-}" && "${UNIHUB_RUNNING_TESTS:-0}" == "1" ]]; then
      cp -- "$PROMTOOL_TEST_SOURCE_ARCHIVE" "$download_tmp"
    else
      curl --fail --silent --show-error --location \
        --connect-timeout 10 --max-time 120 --retry 2 \
        "https://github.com/prometheus/prometheus/releases/download/v${version}/prometheus-${version}.linux-amd64.tar.gz" \
        --output "$download_tmp"
    fi
    printf '%s  %s\n' "$expected_sha" "$download_tmp" | sha256sum --check --status -
    mv -- "$download_tmp" "$archive"
    download_count=1
    source="download"
  else
    source="cache"
  fi
  local extract_dir
  extract_dir="$(mktemp -d)"
  trap 'rm -rf -- "$extract_dir"' RETURN
  tar --extract --gzip --file "$archive" --directory "$extract_dir" \
    --strip-components=1 "prometheus-${version}.linux-amd64/promtool"
  install -m 0755 "$extract_dir/promtool" "$destination"
  rm -rf -- "$extract_dir"
  trap - RETURN
  "$destination" --version 2>&1 | grep -Eq "(^|[ ,])${version}([ ,]|$)"
  local binary_sha
  binary_sha="$(sha256sum "$destination" | awk '{print $1}')"
  write_evidence "$evidence" "$version" "$source" "$download_count" "$archive_sha" "$binary_sha"
  # Keep the per-version lock across verification, extraction, install
  # and evidence creation. A concurrent cache writer therefore cannot replace
  # the archive between the checksum check and the installed binary.
  flock -u 9
}

self_test() {
  local evidence=""
  while [[ "$#" -gt 0 ]]; do
    case "$1" in
      --evidence) evidence="$2"; shift 2 ;;
      *) usage; return 2 ;;
    esac
  done
  [[ -n "$evidence" ]] || { usage; return 2; }
  local test_root
  test_root="$(mktemp -d)"
  trap 'rm -rf -- "$test_root"' RETURN
  local version="3.11.3" package
  package="$test_root/prometheus-${version}.linux-amd64"
  mkdir -p "$package" "$test_root/cache" "$test_root/bin"
  printf '#!/usr/bin/env sh\nprintf "promtool, version 3.11.3\\n"\n' > "$package/promtool"
  chmod 0755 "$package/promtool"
  local source_archive="$test_root/source.tar.gz"
  tar --create --gzip --file "$source_archive" --directory "$test_root" \
    "prometheus-${version}.linux-amd64"
  local digest
  digest="$(sha256sum "$source_archive" | awk '{print $1}')"
  local cold_json="$test_root/cold.json" warm_json="$test_root/warm.json"
  UNIHUB_RUNNING_TESTS=1 \
    PROMTOOL_TEST_SOURCE_ARCHIVE="$source_archive" \
    "$0" prepare --version "$version" --sha256 "$digest" \
      --cache-dir "$test_root/cache" --destination "$test_root/bin/promtool" \
      --evidence "$cold_json"
  UNIHUB_RUNNING_TESTS=1 \
    "$0" prepare --version "$version" --sha256 "$digest" \
      --cache-dir "$test_root/cache" --destination "$test_root/bin/promtool" \
      --evidence "$warm_json"
  "$PYTHON" -I -S - "$cold_json" "$warm_json" "$evidence" <<'PY'
import json
from pathlib import Path
import sys

cold_path, warm_path, output_path = map(Path, sys.argv[1:])
cold = json.loads(cold_path.read_text(encoding="utf-8"))
warm = json.loads(warm_path.read_text(encoding="utf-8"))
if cold.get("source") != "download" or cold.get("download_count") != 1:
    raise SystemExit("cold promtool cache path did not perform exactly one bounded download")
if warm.get("source") != "cache" or warm.get("download_count") != 0:
    raise SystemExit("warm promtool cache path downloaded unexpectedly")
if cold.get("promtool_sha256") != warm.get("promtool_sha256"):
    raise SystemExit("cold and warm promtool binaries differ")
payload = {
    "schema_version": 1,
    "result": "PASS",
    "cold_download_count": 1,
    "warm_download_count": 0,
    "archive_sha256": cold["archive_sha256"],
    "promtool_sha256": cold["promtool_sha256"],
}
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  rm -rf -- "$test_root"
  trap - RETURN
}

mode="${1:-}"
[[ -n "$mode" ]] || { usage; exit 2; }
shift
case "$mode" in
  prepare) prepare "$@" ;;
  self-test) self_test "$@" ;;
  *) usage; exit 2 ;;
esac
