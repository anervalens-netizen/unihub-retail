#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$EUID" -eq 0 ]] || { echo "production Caddy promotion requires root" >&2; exit 1; }
[[ "$#" -eq 2 ]] || { echo "usage: $0 ARTIFACT_TREE SOURCE_SHA" >&2; exit 1; }

artifact_tree="$1"
source_sha="$2"
source_block="$artifact_tree/ops/caddy/retail.caddy"
caddy_root="/opt/Mobiup/infra/caddy"
caddyfile="$caddy_root/Caddyfile"
container="unihub-caddy"

[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid source SHA" >&2; exit 1; }
[[ -f "$source_block" && ! -L "$source_block" ]] || { echo "versioned Retail Caddy block missing" >&2; exit 1; }
[[ -f "$caddyfile" && ! -L "$caddyfile" ]] || { echo "shared Caddyfile missing" >&2; exit 1; }
grep -Fqx 'http://retail.unihub.ro {' "$source_block"
grep -Fq 'request_body @regular_body' "$source_block"

stage="$(mktemp --tmpdir="$caddy_root" .Caddyfile.retail.XXXXXX)"
backup="$caddy_root/Caddyfile.before-retail-$source_sha"
trap 'rm -f -- "$stage"' EXIT

python3 - "$caddyfile" "$source_block" "$stage" <<'PY'
from pathlib import Path
import sys

current_path, block_path, output_path = map(Path, sys.argv[1:])
lines = current_path.read_text(encoding="utf-8").splitlines(keepends=True)
start = next((index for index, line in enumerate(lines) if line.rstrip("\n") == "http://retail.unihub.ro {"), None)
if start is None:
    raise SystemExit("Retail Caddy site block not found")
depth = 0
end = None
for index in range(start, len(lines)):
    depth += lines[index].count("{") - lines[index].count("}")
    if depth == 0:
        end = index + 1
        break
if end is None:
    raise SystemExit("Retail Caddy site block is unbalanced")
block = block_path.read_text(encoding="utf-8")
if not block.endswith("\n"):
    block += "\n"
output_path.write_text("".join(lines[:start]) + block + "".join(lines[end:]), encoding="utf-8")
PY

chmod 0644 "$stage"
image="$(docker inspect "$container" --format '{{.Config.Image}}')"
docker run --rm --network none -v "$stage:/etc/caddy/Caddyfile:ro" "$image" \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

if [[ ! -e "$backup" ]]; then
  install -m 0644 -- "$caddyfile" "$backup"
fi
install -m 0644 -- "$stage" "$caddyfile"
if ! docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile; then
  install -m 0644 -- "$backup" "$caddyfile"
  docker exec "$container" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile || true
  echo "Caddy reload failed; previous config restored" >&2
  exit 1
fi
sha256sum "$source_block" | awk '{print $1}' >"$caddy_root/retail.caddy.sha256"
printf '%s\n' "$source_sha" >"$caddy_root/retail.caddy.source_sha"
chmod 0644 "$caddy_root/retail.caddy.sha256" "$caddy_root/retail.caddy.source_sha"
echo "Retail Caddy block promoted from $source_sha"
