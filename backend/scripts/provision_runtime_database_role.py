#!/usr/bin/env python3
"""Provision and verify the non-owner database role used by web and worker."""
from __future__ import annotations

import argparse
import asyncio
import os
import re
from urllib.parse import unquote, urlparse

import asyncpg


ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
PASSWORD_RE = re.compile(r"^[A-Za-z0-9_-]{48,128}$")

SALARY_RECORD_COLUMNS = (
    "id", "year", "month", "full_name", "total_salary", "company_name",
    "site_code", "locatie", "created_at", "person_id",
)
SALARY_LINK_COLUMNS = (
    "agent_code", "site_code", "salary_full_name", "match_status",
    "match_source", "confidence", "effective_from_month", "note",
    "created_at", "updated_at", "person_id",
)


def _runtime_credentials(database_url: str) -> tuple[str, str, str]:
    parsed = urlparse(database_url)
    role = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = unquote(parsed.path.lstrip("/"))
    if not ROLE_RE.fullmatch(role) or not PASSWORD_RE.fullmatch(password) or not database:
        raise RuntimeError("Runtime database URL credentials are invalid")
    return role, password, database


def _identifier(value: str) -> str:
    if not ROLE_RE.fullmatch(value):
        raise RuntimeError("Database identifier is invalid")
    return f'"{value}"'


async def provision(owner_url: str, runtime_url: str) -> dict[str, bool]:
    role, password, database = _runtime_credentials(runtime_url)
    quoted_role = _identifier(role)
    quoted_database = _identifier(database)
    owner = await asyncpg.connect(owner_url, command_timeout=60)
    try:
        owner_role = await owner.fetchval("SELECT current_user")
        current_database = await owner.fetchval("SELECT current_database()")
        if role == owner_role or database != current_database:
            raise RuntimeError("Runtime role must differ from the owner on the same database")
        exists = await owner.fetchval("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=$1)", role)
        if not exists:
            await owner.execute(
                f"CREATE ROLE {quoted_role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
        password_literal = "'" + password.replace("'", "''") + "'"
        await owner.execute(
            f"ALTER ROLE {quoted_role} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {password_literal}"
        )
        await owner.execute(f"GRANT CONNECT, TEMPORARY ON DATABASE {quoted_database} TO {quoted_role}")
        await owner.execute(f"GRANT USAGE ON SCHEMA public TO {quoted_role}")
        await owner.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted_role}")
        await owner.execute(f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {quoted_role}")
        await owner.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {quoted_role}")
        await owner.execute(f"GRANT TRUNCATE ON premium_glass_item_models TO {quoted_role}")
        for table in ("salary_records", "agent_salary_links", "schema_meta", "schema_migrations"):
            await owner.execute(f"REVOKE ALL ON TABLE {table} FROM {quoted_role}")
        await owner.execute(
            f"GRANT SELECT ({', '.join(SALARY_RECORD_COLUMNS)}) ON salary_records TO {quoted_role}"
        )
        await owner.execute(
            f"GRANT SELECT ({', '.join(SALARY_LINK_COLUMNS)}) ON agent_salary_links TO {quoted_role}"
        )
        await owner.execute(f"GRANT SELECT ON schema_meta, schema_migrations TO {quoted_role}")
        await owner.execute(f"REVOKE ALL ON SCHEMA salary_private FROM {quoted_role}")
        await owner.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA salary_private FROM {quoted_role}")
    finally:
        await owner.close()

    runtime = await asyncpg.connect(runtime_url, command_timeout=30)
    try:
        checks = {
            "not_superuser": not bool(await runtime.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")),
            "no_create_role": not bool(await runtime.fetchval("SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user")),
            "no_create_db": not bool(await runtime.fetchval("SELECT rolcreatedb FROM pg_roles WHERE rolname=current_user")),
            "salary_person_id_read": bool(await runtime.fetchval("SELECT has_column_privilege(current_user, 'salary_records', 'person_id', 'SELECT')")),
            "salary_cnp_denied": not bool(await runtime.fetchval("SELECT has_column_privilege(current_user, 'salary_records', 'cnp', 'SELECT')")),
            "link_cnp_denied": not bool(await runtime.fetchval("SELECT has_column_privilege(current_user, 'agent_salary_links', 'salary_cnp', 'SELECT')")),
            "private_schema_denied": not bool(await runtime.fetchval("SELECT has_schema_privilege(current_user, 'salary_private', 'USAGE')")),
            "schema_create_denied": not bool(await runtime.fetchval("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")),
        }
        await runtime.fetchval("SELECT COUNT(*) FROM salary_records")
        await runtime.fetchval("SELECT COUNT(*) FROM schema_migrations")
    finally:
        await runtime.close()
    if not all(checks.values()):
        raise RuntimeError("Runtime database role verification failed")
    return checks


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        raise RuntimeError("Use --apply to provision the runtime database role")
    owner_url = os.getenv("MIGRATION_DATABASE_URL")
    runtime_url = os.getenv("RUNTIME_DATABASE_URL")
    if not owner_url or not runtime_url:
        raise RuntimeError("Migration and runtime database URLs are required")
    checks = await provision(owner_url, runtime_url)
    print("runtime_database_role_verified=true checks=" + str(len(checks)))


if __name__ == "__main__":
    asyncio.run(main())
