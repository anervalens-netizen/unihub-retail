#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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
npm_sbom_source="${NPM_SBOM_PATH:-}"
python_sbom_source="${PYTHON_SBOM_PATH:-}"
if [[ -n "$npm_sbom_source" ]]; then
  [[ -f "$npm_sbom_source" && ! -L "$npm_sbom_source" ]] || die "npm SBOM input is unsafe"
  cp -- "$npm_sbom_source" "$BUILD_DIR/SBOM.npm.cdx.json"
else
  (cd "$REPO_ROOT" && npm sbom --package-lock-only --omit=dev --sbom-format cyclonedx --sbom-type application) \
    >"$BUILD_DIR/SBOM.npm.cdx.json"
fi
if [[ -n "$python_sbom_source" ]]; then
  [[ -f "$python_sbom_source" && ! -L "$python_sbom_source" ]] || die "Python SBOM input is unsafe"
  cp -- "$python_sbom_source" "$BUILD_DIR/SBOM.python.cdx.json"
else
  cyclonedx_py="${CYCLONEDX_PY:-$SCRIPT_DIR/../backend/venv/bin/cyclonedx-py}"
  [[ -x "$cyclonedx_py" ]] || die "cyclonedx-py is required for faithful Python SBOM generation"
  "$cyclonedx_py" requirements "$REPO_ROOT/backend/requirements.lock" \
    --output-reproducible --output-format JSON \
    --output-file "$BUILD_DIR/SBOM.python.cdx.json"
fi
python3 "$SCRIPT_DIR/../scripts/validate_release_sbom.py" npm "$BUILD_DIR/SBOM.npm.cdx.json"
python3 "$SCRIPT_DIR/../scripts/validate_release_sbom.py" pypi "$BUILD_DIR/SBOM.python.cdx.json"

python3 - "$REPO_ROOT" "$BUILD_DIR" "$SOURCE_SHA" "$ARCHIVE_NAME" \
  "${RELEASE_BUILDER_ID:-local:ops/build-retail-release-artifact.sh}" \
  "${RELEASE_INVOCATION_ID:-local}" <<'PY'
import hashlib
import json
import pathlib
import sys
import uuid

repo, output, source_sha, archive_name, builder_id, invocation_id = sys.argv[1:]
repo_path = pathlib.Path(repo)
output_path = pathlib.Path(output)
archive_path = output_path / archive_name

def prefixed_inventory(filename, prefix, required_scope=False):
    payload = json.loads((output_path / filename).read_text(encoding="utf-8"))
    components = list(payload.get("components", []))
    metadata_component = payload.get("metadata", {}).get("component")
    metadata_ref = (
        metadata_component.get("bom-ref")
        if isinstance(metadata_component, dict)
        else None
    )
    component_refs = {
        component.get("bom-ref")
        for component in components
        if isinstance(component, dict)
    }
    if isinstance(metadata_component, dict) and metadata_ref not in component_refs:
        components.append(metadata_component)
    refs = {}
    canonical_components = []
    canonical_by_ref = {}
    for component in components:
        old_ref = component.get("bom-ref")
        if isinstance(old_ref, str):
            identity = tuple(component.get(key) for key in ("type", "name", "version", "purl"))
            existing = canonical_by_ref.get(old_ref)
            if existing is not None:
                existing_identity = tuple(existing.get(key) for key in ("type", "name", "version", "purl"))
                if identity != existing_identity:
                    raise SystemExit(f"conflicting duplicate CycloneDX identity: {prefix}:{old_ref}")
                continue
            refs[old_ref] = f"{prefix}:{old_ref}"
            component["bom-ref"] = refs[old_ref]
            canonical_by_ref[old_ref] = component
            canonical_components.append(component)
        if required_scope and str(component.get("purl", "")).startswith("pkg:pypi/"):
            component["scope"] = "required"
    dependencies_by_ref = {}
    for dependency in payload.get("dependencies", []):
        ref = refs.get(dependency.get("ref"))
        if not ref:
            continue
        depends_on = dependencies_by_ref.setdefault(ref, [])
        for item in dependency.get("dependsOn", []):
            target = refs.get(item)
            if target and target not in depends_on:
                depends_on.append(target)
    dependencies = [
        {"ref": ref, "dependsOn": depends_on}
        for ref, depends_on in dependencies_by_ref.items()
    ]
    roots = []
    if isinstance(metadata_ref, str) and metadata_ref in refs:
        roots.append(refs[metadata_ref])
    elif prefix == "python":
        roots.extend(component["bom-ref"] for component in components if component.get("scope") == "required")
    return canonical_components, dependencies, roots

npm_components, npm_dependencies, npm_roots = prefixed_inventory("SBOM.npm.cdx.json", "npm")
python_components, python_dependencies, python_roots = prefixed_inventory(
    "SBOM.python.cdx.json", "python", required_scope=True
)
root_ref = f"pkg:github/anervalens-netizen/unihub-retail@{source_sha}"
sbom = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, root_ref)}",
    "version": 1,
    "metadata": {"component": {
        "bom-ref": root_ref,
        "type": "application",
        "name": "unihub-retail",
        "version": source_sha,
        "purl": root_ref,
    }},
    "components": npm_components + python_components,
    "dependencies": [
        {"ref": root_ref, "dependsOn": npm_roots + python_roots},
        *npm_dependencies,
        *python_dependencies,
    ],
    "compositions": [{"aggregate": "complete", "assemblies": [root_ref]}],
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
for name in (
    archive_name, "SOURCE_SHA", "SBOM.cdx.json", "SBOM.npm.cdx.json",
    "SBOM.python.cdx.json", "PROVENANCE.json",
):
    evidence[name] = hashlib.sha256((output_path / name).read_bytes()).hexdigest()
manifest = {"schemaVersion": 1, "sourceSha": source_sha, "archive": archive_name, "sha256": evidence}
(output_path / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
python3 "$SCRIPT_DIR/../scripts/validate_release_sbom.py" aggregate \
  "$BUILD_DIR/SBOM.cdx.json" --expected-sha "$SOURCE_SHA"
(
  cd "$BUILD_DIR"
  sha256sum SOURCE_SHA "$ARCHIVE_NAME" SBOM.cdx.json SBOM.npm.cdx.json \
    SBOM.python.cdx.json PROVENANCE.json RELEASE_MANIFEST.json > SHA256SUMS
)

mv -- "$BUILD_DIR" "$OUTPUT_DIR"
trap - EXIT
printf '%s\n' "$OUTPUT_DIR/$ARCHIVE_NAME"
