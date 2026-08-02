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
(
  cd "$BUILD_DIR"
  sha256sum SOURCE_SHA "$ARCHIVE_NAME" > SHA256SUMS
)

mv -- "$BUILD_DIR" "$OUTPUT_DIR"
trap - EXIT
printf '%s\n' "$OUTPUT_DIR/$ARCHIVE_NAME"
