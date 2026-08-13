#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
NODE="/opt/codex-desktop/resources/node-runtime/bin/node"
NPM_CLI="/opt/codex-desktop/resources/node-runtime/lib/node_modules/npm/bin/npm-cli.js"
NODE_SHA256="81925c0995b5c1427b5d538e6a90ca2fdc4daffb786b09af749beaf7369d4e90"
NPM_CLI_SHA256="8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7"

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "must run inside a Git worktree"
[[ -x "$NODE" && -f "$NPM_CLI" \
  && "$(sha256sum "$NODE" | awk '{print $1}')" == "$NODE_SHA256" \
  && "$(sha256sum "$NPM_CLI" | awk '{print $1}')" == "$NPM_CLI_SHA256" ]] \
  || die "pinned Node.js/npm runtime is unavailable"
BASE_SHA="${PWA_BASE_SHA:-}"
if [[ -z "$BASE_SHA" ]]; then
  BASE_SHA="$(git -C "$REPO_ROOT" merge-base HEAD origin/main 2>/dev/null)" \
    || die "set PWA_BASE_SHA or provide origin/main"
fi
[[ "$BASE_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || die "PWA_BASE_SHA must be exactly 40 lowercase hex characters"
git -C "$REPO_ROOT" cat-file -e "$BASE_SHA^{commit}" 2>/dev/null \
  || die "base commit $BASE_SHA is not available locally"
[[ -s "$REPO_ROOT/dist/sw.js" ]] \
  || die "candidate dist/sw.js is missing; run npm run build first"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/retail-pwa-lifecycle.XXXXXX")"
trap 'rm -rf -- "$WORK_DIR"' EXIT
BASE_SOURCE="$WORK_DIR/source"
mkdir -p "$BASE_SOURCE"
git -C "$REPO_ROOT" archive --format=tar "$BASE_SHA" \
  | tar --extract --file=- --directory="$BASE_SOURCE"

(
  cd "$BASE_SOURCE"
  npm_config_offline=true "$NODE" "$NPM_CLI" ci --offline --ignore-scripts --include=dev
  "$NODE" node_modules/vite/bin/vite.js build
)
[[ -s "$BASE_SOURCE/dist/sw.js" ]] \
  || die "previous release did not produce dist/sw.js"

PWA_PREVIOUS_DIST="$BASE_SOURCE/dist" \
PWA_CANDIDATE_DIST="$REPO_ROOT/dist" \
  "$NODE" "$REPO_ROOT/node_modules/@playwright/test/cli.js" test \
    --config="$REPO_ROOT/playwright.pwa-workbox.config.ts"
