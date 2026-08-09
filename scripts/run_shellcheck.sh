#!/usr/bin/env bash
set -euo pipefail

command -v shellcheck >/dev/null || {
  echo "shellcheck is required" >&2
  exit 1
}
mapfile -d '' scripts < <(git ls-files -z -- '*.sh')
test "${#scripts[@]}" -gt 0
shellcheck --severity=warning --external-sources "${scripts[@]}"
