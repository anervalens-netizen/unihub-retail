#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
MODE="${1:-verify}"
LIVE_ROOT="/opt/Mobiup/unihub-retail"
OPERATOR_USER="andrei"
NOLOGIN_SHELL="/usr/sbin/nologin"

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

[[ "$#" -le 1 && ("$MODE" == "apply" || "$MODE" == "verify") ]] \
  || die "usage: $PROGRAM [apply|verify]"
[[ "$EUID" -eq 0 ]] || die "service identity provisioning requires root"
[[ -d "$LIVE_ROOT" && ! -L "$LIVE_ROOT" ]] \
  || die "Retail live root is unavailable or unsafe"
[[ -x "$NOLOGIN_SHELL" ]] || die "nologin shell is unavailable"
getent passwd "$OPERATOR_USER" >/dev/null \
  || die "Retail operator account is unavailable"

RETAIL_GROUP_NAMES=(
  unihub-web
  unihub-operations
  unihub-import
  unihub-grile
  unihub-export
  unihub-salary-export
  unihub-migrate
  unihub-import-spool
  unihub-promo-artifacts
  unihub-grile-artifacts
  unihub-export-artifacts
)

RETAIL_SERVICE_USERS=(
  unihub-web
  unihub-operations
  unihub-import
  unihub-grile
  unihub-export
  unihub-salary-export
  unihub-migrate
)

declare -A PRIMARY_GROUP=(
  [unihub-web]=unihub-web
  [unihub-operations]=unihub-operations
  [unihub-import]=unihub-import
  [unihub-grile]=unihub-grile
  [unihub-export]=unihub-export
  [unihub-salary-export]=unihub-salary-export
  [unihub-migrate]=unihub-migrate
)

declare -A SUPPLEMENTARY_GROUPS=(
  [unihub-web]="unihub-import-spool,unihub-promo-artifacts,unihub-grile-artifacts,unihub-export-artifacts"
  [unihub-operations]=""
  [unihub-import]="unihub-import-spool,unihub-promo-artifacts"
  [unihub-grile]="unihub-operations,unihub-grile-artifacts"
  [unihub-export]="unihub-operations,unihub-export-artifacts"
  [unihub-salary-export]="unihub-export-artifacts"
  [unihub-migrate]=""
)

declare -A ENVIRONMENT_GROUP=(
  [.env]=unihub-web
  [.env.worker]=unihub-operations
  [.env.import-worker]=unihub-import
  [.env.salary-export-worker]=unihub-salary-export
  [.env.migrations]=unihub-migrate
)

csv_sorted_lines() {
  tr ',' '\n' <<<"$1" | sed '/^$/d' | sort -u
}

expected_user_groups() {
  local user="$1"
  {
    printf '%s\n' "${PRIMARY_GROUP[$user]}"
    csv_sorted_lines "${SUPPLEMENTARY_GROUPS[$user]}"
  } | sort -u
}

ensure_group() {
  local group="$1"
  if getent group "$group" >/dev/null; then
    return
  fi
  [[ "$MODE" == "apply" ]] || die "required group is absent: $group"
  groupadd --system "$group"
}

ensure_service_user() {
  local user="$1"
  local primary="${PRIMARY_GROUP[$user]}"
  local supplementary="${SUPPLEMENTARY_GROUPS[$user]}"
  if ! getent passwd "$user" >/dev/null; then
    [[ "$MODE" == "apply" ]] || die "required service user is absent: $user"
    local -a create=(
      useradd --system --no-create-home --home-dir /nonexistent
      --shell "$NOLOGIN_SHELL" --gid "$primary"
    )
    if [[ -n "$supplementary" ]]; then
      create+=(--groups "$supplementary")
    fi
    create+=("$user")
    "${create[@]}"
  elif [[ "$MODE" == "apply" ]]; then
    usermod --gid "$primary" --home /nonexistent --shell "$NOLOGIN_SHELL" "$user"
    if [[ -n "$supplementary" ]]; then
      usermod --groups "$supplementary" "$user"
    else
      usermod --groups "$primary" "$user"
    fi
  fi
  if [[ "$MODE" == "apply" ]]; then
    usermod --lock "$user"
  fi
}

verify_service_user() {
  local user="$1"
  local entry name _password uid _gid _gecos home shell
  entry="$(getent passwd "$user")" || die "service user disappeared: $user"
  IFS=: read -r name _password uid _gid _gecos home shell <<<"$entry"
  [[ "$name" == "$user" && "$uid" =~ ^[1-9][0-9]*$ ]] \
    || die "service user identity is invalid: $user"
  [[ "$home" == "/nonexistent" && "$shell" == "$NOLOGIN_SHELL" ]] \
    || die "service user must have no home and nologin shell: $user"
  [[ "$(id -gn "$user")" == "${PRIMARY_GROUP[$user]}" ]] \
    || die "service user primary group is invalid: $user"
  diff -u \
    <(expected_user_groups "$user") \
    <(id -nG "$user" | tr ' ' '\n' | sort -u) >/dev/null \
    || die "service user supplementary groups are invalid: $user"
  [[ "$(passwd -S "$user" | awk '{print $2}')" == "L" ]] \
    || die "service user password is not locked: $user"
}

ensure_operator_memberships() {
  local required_csv
  required_csv="$(IFS=,; printf '%s' "${RETAIL_GROUP_NAMES[*]}")"
  if [[ "$MODE" == "apply" ]]; then
    usermod --append --groups "$required_csv" "$OPERATOR_USER"
  fi
  local operator_groups
  operator_groups="$(id -nG "$OPERATOR_USER" | tr ' ' '\n' | sort -u)"
  local group
  for group in "${RETAIL_GROUP_NAMES[@]}"; do
    grep -Fxq "$group" <<<"$operator_groups" \
      || die "operator is missing rollback-compatible group: $group"
  done
}

secure_environment_files() {
  local file group path
  for file in "${!ENVIRONMENT_GROUP[@]}"; do
    group="${ENVIRONMENT_GROUP[$file]}"
    path="$LIVE_ROOT/$file"
    if [[ ! -f "$path" || -L "$path" ]]; then
      if [[ "$MODE" == "apply" && "$file" == ".env.salary-export-worker" ]]; then
        continue
      fi
      die "required environment file is absent or unsafe: $file"
    fi
    if [[ "$MODE" == "apply" ]]; then
      chown root:"$group" "$path"
      chmod 0640 "$path"
    fi
    [[ "$(stat -c '%U:%G:%a' "$path")" == "root:$group:640" ]] \
      || die "environment ownership contract is invalid: $file"
  done
}

for group in "${RETAIL_GROUP_NAMES[@]}"; do
  ensure_group "$group"
done
for user in "${RETAIL_SERVICE_USERS[@]}"; do
  ensure_service_user "$user"
done
ensure_operator_memberships
for user in "${RETAIL_SERVICE_USERS[@]}"; do
  verify_service_user "$user"
done
secure_environment_files

printf 'retail_service_identities_verified=true users=%s groups=%s mode=%s\n' \
  "${#RETAIL_SERVICE_USERS[@]}" "${#RETAIL_GROUP_NAMES[@]}" "$MODE"
