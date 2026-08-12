#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

PROGRAM="$(basename "$0")"
MODE="${1:-verify}"
LIVE_ROOT="/opt/Mobiup/unihub-retail"
SOURCE_ENV="$LIVE_ROOT/.env.worker"
SALARY_ENV="$LIVE_ROOT/.env.salary-export-worker"
SALARY_ENV_GROUP="unihub-salary-export"
DB_CONTAINER="unihub_postgres"
DB_NAME="unihub"
AUTHORITY_ROLE="unihub_salary_export"
LOGIN_ROLE="unihub_salary_export_worker"
DB_HOST="127.0.0.1"
DB_PORT="5432"
TEMP_ENV=""
runtime_password=""

die() {
  printf '%s: %s\n' "$PROGRAM" "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "$TEMP_ENV" ]]; then
    rm -f -- "$TEMP_ENV"
  fi
  runtime_password=""
}
trap cleanup EXIT

[[ "$#" -le 1 && ("$MODE" == "apply" || "$MODE" == "verify") ]] \
  || die "usage: $PROGRAM [apply|verify]"
[[ "$EUID" -eq 0 ]] || die "salary export database provisioning requires root"
[[ -d "$LIVE_ROOT" && ! -L "$LIVE_ROOT" ]] \
  || die "Retail live root is unavailable or unsafe"
[[ -f "$SOURCE_ENV" && ! -L "$SOURCE_ENV" ]] \
  || die "operations worker environment is unavailable or unsafe"
getent group "$SALARY_ENV_GROUP" >/dev/null \
  || die "salary export OS group must be provisioned first"
command -v docker >/dev/null || die "docker is unavailable"
command -v openssl >/dev/null || die "openssl is unavailable"
command -v psql >/dev/null || die "PostgreSQL client is unavailable"
[[ "$(docker inspect --format '{{.State.Running}}' "$DB_CONTAINER" 2>/dev/null)" == "true" ]] \
  || die "Retail PostgreSQL container is not running"

admin_psql() {
  docker exec -i "$DB_CONTAINER" sh -lc \
    'exec psql --no-psqlrc --set=ON_ERROR_STOP=1 --quiet --username="$POSTGRES_USER" --dbname=unihub'
}

admin_scalar() {
  local sql="$1"
  docker exec -i "$DB_CONTAINER" sh -lc \
    'exec psql --no-psqlrc --set=ON_ERROR_STOP=1 --tuples-only --no-align --quiet --username="$POSTGRES_USER" --dbname=unihub --command "$1"' \
    sh "$sql"
}

read_salary_environment() {
  local database_url count
  [[ -f "$SALARY_ENV" && ! -L "$SALARY_ENV" ]] \
    || die "salary export environment is unavailable or unsafe"
  count="$(grep -Ec '^DATABASE_URL=' "$SALARY_ENV" || true)"
  [[ "$count" -eq 1 ]] || die "salary export environment must contain one DATABASE_URL"
  database_url="$(sed -n 's/^DATABASE_URL=//p' "$SALARY_ENV")"
  if [[ "$database_url" =~ ^postgresql://unihub_salary_export_worker:([0-9a-f]{64})@127[.]0[.]0[.]1:5432/unihub$ ]]; then
    runtime_password="${BASH_REMATCH[1]}"
  else
    die "salary export DATABASE_URL contract is invalid"
  fi
}

write_salary_environment() {
  local source_count line database_url
  source_count="$(grep -Ec '^DATABASE_URL=' "$SOURCE_ENV" || true)"
  [[ "$source_count" -eq 1 ]] \
    || die "operations worker environment must contain one DATABASE_URL"
  database_url="postgresql://$LOGIN_ROLE:$runtime_password@$DB_HOST:$DB_PORT/$DB_NAME"
  TEMP_ENV="$(mktemp /run/unihub-salary-export-env.XXXXXX)"
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == DATABASE_URL=* ]]; then
      printf 'DATABASE_URL=%s\n' "$database_url"
    else
      printf '%s\n' "$line"
    fi
  done <"$SOURCE_ENV" >"$TEMP_ENV"
  [[ "$(grep -Ec '^DATABASE_URL=' "$TEMP_ENV")" -eq 1 ]] \
    || die "generated salary export environment is invalid"
  install -m 0640 -o root -g "$SALARY_ENV_GROUP" -- "$TEMP_ENV" "$SALARY_ENV"
  rm -f -- "$TEMP_ENV"
  TEMP_ENV=""
}

apply_database_contract() {
  admin_psql <<SQL
BEGIN;
DO \$provision\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$AUTHORITY_ROLE') THEN
        CREATE ROLE $AUTHORITY_ROLE
            NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$LOGIN_ROLE') THEN
        CREATE ROLE $LOGIN_ROLE
            LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
            NOREPLICATION NOBYPASSRLS;
    END IF;
END
\$provision\$;
ALTER ROLE $AUTHORITY_ROLE WITH
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
    NOREPLICATION NOBYPASSRLS;
ALTER ROLE $LOGIN_ROLE WITH
    LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT
    NOREPLICATION NOBYPASSRLS PASSWORD '$runtime_password';
DO \$memberships\$
DECLARE
    membership RECORD;
BEGIN
    FOR membership IN
        SELECT parent.rolname
        FROM pg_auth_members AS edge
        JOIN pg_roles AS parent ON parent.oid = edge.roleid
        JOIN pg_roles AS member ON member.oid = edge.member
        WHERE member.rolname = '$AUTHORITY_ROLE'
    LOOP
        EXECUTE format('REVOKE %I FROM $AUTHORITY_ROLE', membership.rolname);
    END LOOP;
    FOR membership IN
        SELECT parent.rolname
        FROM pg_auth_members AS edge
        JOIN pg_roles AS parent ON parent.oid = edge.roleid
        JOIN pg_roles AS member ON member.oid = edge.member
        WHERE member.rolname = '$LOGIN_ROLE'
    LOOP
        EXECUTE format('REVOKE %I FROM $LOGIN_ROLE', membership.rolname);
    END LOOP;
END
\$memberships\$;
GRANT $AUTHORITY_ROLE TO $LOGIN_ROLE WITH INHERIT TRUE, SET FALSE;
REVOKE ALL PRIVILEGES ON DATABASE $DB_NAME FROM $LOGIN_ROLE;
GRANT CONNECT ON DATABASE $DB_NAME TO $AUTHORITY_ROLE;
DO \$contract\$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_shdepend AS dependency
        JOIN pg_roles AS principal ON principal.oid = dependency.refobjid
        WHERE dependency.refclassid = 'pg_authid'::regclass
          AND principal.rolname = '$LOGIN_ROLE'
          AND dependency.deptype IN ('a', 'o')
    ) THEN
        RAISE EXCEPTION
            '$LOGIN_ROLE has a direct grant, default ACL, or owned object';
    END IF;
    IF (SELECT count(*) FROM pg_auth_members AS edge
        JOIN pg_roles AS member ON member.oid = edge.member
        WHERE member.rolname = '$AUTHORITY_ROLE') <> 0 THEN
        RAISE EXCEPTION '$AUTHORITY_ROLE inherits an unexpected role';
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_auth_members AS edge
        JOIN pg_roles AS parent ON parent.oid = edge.roleid
        JOIN pg_roles AS member ON member.oid = edge.member
        WHERE member.rolname = '$LOGIN_ROLE'
          AND parent.rolname = '$AUTHORITY_ROLE'
          AND edge.inherit_option
          AND NOT edge.set_option
    ) OR (SELECT count(*) FROM pg_auth_members AS edge
          JOIN pg_roles AS member ON member.oid = edge.member
          WHERE member.rolname = '$LOGIN_ROLE') <> 1 THEN
        RAISE EXCEPTION '$LOGIN_ROLE membership contract is invalid';
    END IF;
END
\$contract\$;
COMMIT;
SQL
}

verify_database_contract() {
  local authority_flags login_flags memberships authority_parents effective direct_authority can_connect
  authority_flags="$(admin_scalar \
    "SELECT rolcanlogin, rolsuper, rolinherit, rolcreatedb, rolcreaterole, rolbypassrls, rolreplication FROM pg_roles WHERE rolname = '$AUTHORITY_ROLE'")"
  [[ "$authority_flags" == "f|f|f|f|f|f|f" ]] \
    || die "salary export authority flags are invalid"
  login_flags="$(admin_scalar \
    "SELECT rolcanlogin, rolsuper, rolinherit, rolcreatedb, rolcreaterole, rolbypassrls, rolreplication FROM pg_roles WHERE rolname = '$LOGIN_ROLE'")"
  [[ "$login_flags" == "t|f|t|f|f|f|f" ]] \
    || die "salary export LOGIN flags are invalid"
  memberships="$(admin_scalar \
    "SELECT parent.rolname || '|' || edge.inherit_option::text || '|' || edge.set_option::text FROM pg_auth_members AS edge JOIN pg_roles AS parent ON parent.oid=edge.roleid JOIN pg_roles AS member ON member.oid=edge.member WHERE member.rolname='$LOGIN_ROLE' ORDER BY parent.rolname")"
  [[ "$memberships" == "$AUTHORITY_ROLE|true|false" ]] \
    || die "salary export LOGIN membership contract is invalid"
  authority_parents="$(admin_scalar \
    "SELECT count(*) FROM pg_auth_members AS edge JOIN pg_roles AS member ON member.oid=edge.member WHERE member.rolname='$AUTHORITY_ROLE'")"
  [[ "$authority_parents" == "0" ]] \
    || die "salary export authority inherits an unexpected role"
  effective="$(admin_scalar \
    "SELECT candidate.rolname FROM pg_roles AS candidate JOIN pg_roles AS member ON member.rolname='$LOGIN_ROLE' WHERE candidate.oid<>member.oid AND pg_has_role(member.oid,candidate.oid,'member') ORDER BY candidate.rolname")"
  [[ "$effective" == "$AUTHORITY_ROLE" ]] \
    || die "salary export LOGIN has unexpected transitive authority"
  direct_authority="$(admin_scalar \
    "WITH target AS (SELECT oid FROM pg_roles WHERE rolname='$LOGIN_ROLE') SELECT EXISTS (SELECT 1 FROM pg_shdepend AS dependency CROSS JOIN target WHERE dependency.refclassid='pg_authid'::regclass AND dependency.refobjid=target.oid AND dependency.deptype IN ('a','o'))")"
  [[ "$direct_authority" == "f" ]] \
    || die "salary export LOGIN has a direct grant, default ACL, or owned object"
  can_connect="$(admin_scalar \
    "SELECT has_database_privilege('$LOGIN_ROLE', '$DB_NAME', 'CONNECT')")"
  [[ "$can_connect" == "t" ]] || die "salary export LOGIN cannot connect to Retail"
}

verify_login() {
  local authenticated
  authenticated="$(
    PGPASSWORD="$runtime_password" psql --no-psqlrc --set=ON_ERROR_STOP=1 \
      --tuples-only --no-align --quiet \
      --host="$DB_HOST" --port="$DB_PORT" --username="$LOGIN_ROLE" --dbname="$DB_NAME" \
      --command='SELECT current_user || chr(124) || session_user'
  )"
  [[ "$authenticated" == "$LOGIN_ROLE|$LOGIN_ROLE" ]] \
    || die "salary export LOGIN authentication failed"
}

if [[ "$MODE" == "apply" ]]; then
  if [[ -e "$SALARY_ENV" || -L "$SALARY_ENV" ]]; then
    read_salary_environment
  else
    runtime_password="$(openssl rand -hex 32)"
    [[ "$runtime_password" =~ ^[0-9a-f]{64}$ ]] \
      || die "generated database credential is invalid"
  fi
  apply_database_contract
  write_salary_environment
else
  read_salary_environment
fi

[[ "$(stat -c '%U:%G:%a' "$SALARY_ENV")" == "root:$SALARY_ENV_GROUP:640" ]] \
  || die "salary export environment ownership contract is invalid"
verify_database_contract
verify_login

printf 'retail_salary_export_database_verified=true authority=%s login=%s mode=%s\n' \
  "$AUTHORITY_ROLE" "$LOGIN_ROLE" "$MODE"
