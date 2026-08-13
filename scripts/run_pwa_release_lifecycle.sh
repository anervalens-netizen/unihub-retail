#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" \
  || die "must run inside a Git worktree"
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
  npm_config_offline=true npm ci --offline --ignore-scripts --include=dev
  node_modules/.bin/vite build
)
[[ -s "$BASE_SOURCE/dist/sw.js" ]] \
  || die "previous release did not produce dist/sw.js"

PWA_PREVIOUS_DIST="$BASE_SOURCE/dist" \
PWA_CANDIDATE_DIST="$REPO_ROOT/dist" \
  "$REPO_ROOT/node_modules/.bin/playwright" test \
    --config="$REPO_ROOT/playwright.pwa-workbox.config.ts"
