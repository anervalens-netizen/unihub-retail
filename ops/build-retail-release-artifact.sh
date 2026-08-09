#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

[[ "$#" -eq 2 ]] \
  || die "usage: $PROGRAM <40-char-source-sha> <empty-output-directory>"

SOURCE_SHA="$1"
OUTPUT_DIR="$2"
[[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || die "source SHA must be exactly 40 lowercase hex characters"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "must run inside a Git worktree"
[[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" == "$SOURCE_SHA" ]] \
  || die "source SHA must equal the checked-out HEAD"
[[ -d "$REPO_ROOT/dist" && -f "$REPO_ROOT/dist/index.html" \
  && ! -L "$REPO_ROOT/dist/index.html" && -s "$REPO_ROOT/dist/index.html" ]] \
  || die "tested frontend build is missing"
if find "$REPO_ROOT/dist" -type l -print -quit | grep -q .; then
  die "tested frontend build must not contain symlinks"
fi

[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] \
  || die "output directory already exists"
OUTPUT_PARENT="$(dirname -- "$OUTPUT_DIR")"
OUTPUT_NAME="$(basename -- "$OUTPUT_DIR")"
[[ -d "$OUTPUT_PARENT" && ! -L "$OUTPUT_PARENT" ]] \
  || die "output parent must be an existing directory"

BUILD_DIR="$(mktemp -d "$OUTPUT_PARENT/.${OUTPUT_NAME}.XXXXXX")"
trap 'rm -rf -- "$BUILD_DIR"' EXIT
SOURCE_DIR="$BUILD_DIR/source"
ARCHIVE_NAME="retail-release-${SOURCE_SHA}.tar.gz"

mkdir -p "$SOURCE_DIR"
git -C "$REPO_ROOT" archive --format=tar "$SOURCE_SHA" \
  | tar --extract --file=- --directory="$SOURCE_DIR"
[[ ! -e "$SOURCE_DIR/dist" && ! -L "$SOURCE_DIR/dist" ]] \
  || die "source SHA must not track frontend build output"
cp -a -- "$REPO_ROOT/dist" "$SOURCE_DIR/dist"

tar --create \
  --file "$BUILD_DIR/${ARCHIVE_NAME%.gz}" \
  --directory "$SOURCE_DIR" \
  --sort=name \
  --mtime='@0' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  .
gzip -n "$BUILD_DIR/${ARCHIVE_NAME%.gz}"
printf '%s\n' "$SOURCE_SHA" >"$BUILD_DIR/SOURCE_SHA"
python3 - "$REPO_ROOT" "$BUILD_DIR" "$SOURCE_SHA" "$ARCHIVE_NAME" \
  "${RELEASE_BUILDER_ID:-local:ops/build-retail-release-artifact.sh}" \
  "${RELEASE_INVOCATION_ID:-local}" <<'PY'
import hashlib
import json
import pathlib
import re
import sys

repo, output, source_sha, archive_name, builder_id, invocation_id = sys.argv[1:]
repo_path = pathlib.Path(repo)
output_path = pathlib.Path(output)
archive_path = output_path / archive_name

components = []
lock = json.loads((repo_path / "package-lock.json").read_text(encoding="utf-8"))
for package_path, package in sorted(lock.get("packages", {}).items()):
    if not package_path or not package_path.startswith("node_modules/"):
        continue
    name = package.get("name") or package_path.removeprefix("node_modules/")
    version = package.get("version")
    if version:
        components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:npm/{name}@{version}"})
requirement = re.compile(r"^([A-Za-z0-9_.-]+)==([^ ;\\]+)")
for line in (repo_path / "backend/requirements.lock").read_text(encoding="utf-8").splitlines():
    match = requirement.match(line)
    if match:
        name, version = match.groups()
        components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:pypi/{name.lower()}@{version}"})
components.sort(key=lambda item: (item["purl"], item["name"]))
sbom = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "version": 1,
    "metadata": {"component": {"type": "application", "name": "unihub-retail", "version": source_sha}},
    "components": components,
}
(output_path / "SBOM.cdx.json").write_text(json.dumps(sbom, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

archive_digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
provenance = {
    "_type": "https://in-toto.io/Statement/v1",
    "subject": [{"name": archive_name, "digest": {"sha256": archive_digest}}],
    "predicateType": "https://slsa.dev/provenance/v1",
    "predicate": {
        "buildDefinition": {
            "buildType": "https://github.com/anervalens-netizen/unihub-retail/retail-release@v1",
            "externalParameters": {"sourceSha": source_sha},
            "internalParameters": {},
            "resolvedDependencies": [{"uri": "git+https://github.com/anervalens-netizen/unihub-retail", "digest": {"gitCommit": source_sha}}],
        },
        "runDetails": {"builder": {"id": builder_id}, "metadata": {"invocationId": invocation_id}},
    },
}
(output_path / "PROVENANCE.json").write_text(json.dumps(provenance, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

evidence = {}
for name in (archive_name, "SOURCE_SHA", "SBOM.cdx.json", "PROVENANCE.json"):
    evidence[name] = hashlib.sha256((output_path / name).read_bytes()).hexdigest()
manifest = {"schemaVersion": 1, "sourceSha": source_sha, "archive": archive_name, "sha256": evidence}
(output_path / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
(
  cd "$BUILD_DIR"
  sha256sum SOURCE_SHA "$ARCHIVE_NAME" SBOM.cdx.json PROVENANCE.json RELEASE_MANIFEST.json > SHA256SUMS
)

mv -- "$BUILD_DIR" "$OUTPUT_DIR"
trap - EXIT
printf '%s\n' "$OUTPUT_DIR/$ARCHIVE_NAME"
