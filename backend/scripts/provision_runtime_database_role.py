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
AUTHORITY_ROLES = frozenset({
    "unihub_web_read",
    "unihub_business_write",
    "unihub_sales_import",
    "unihub_finance_import",
    "unihub_operations",
    "unihub_migrate",
})
AUTHORITY_CONTRACTS = frozenset({
    frozenset({"unihub_web_read", "unihub_business_write"}),
    frozenset({"unihub_sales_import"}),
    frozenset({"unihub_finance_import"}),
    frozenset({"unihub_operations"}),
    frozenset({"unihub_migrate"}),
})


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


async def provision(
    owner_url: str,
    runtime_url: str,
    *,
    authority_roles: frozenset[str],
) -> dict[str, bool]:
    """Attach an existing service LOGIN to one exact reviewed authority contract.

    Migration 040 owns all object grants.  This command deliberately never
    creates a LOGIN, changes a password, grants broad/default object privileges,
    or combines authorities outside a named process contract.  Running ``--apply`` remains a restricted
    service-identity operation and needs the separate operational approval.
    """
    if authority_roles not in AUTHORITY_CONTRACTS:
        raise RuntimeError("Database authority contract is invalid")
    role, password, database = _runtime_credentials(runtime_url)
    quoted_role = _identifier(role)
    owner = await asyncpg.connect(owner_url, command_timeout=60)
    try:
        owner_role = await owner.fetchval("SELECT current_user")
        current_database = await owner.fetchval("SELECT current_database()")
        if role == owner_role or database != current_database:
            raise RuntimeError("Runtime role must differ from the owner on the same database")
        service_role = await owner.fetchrow(
            "SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolcreatedb "
            "FROM pg_roles WHERE rolname = $1",
            role,
        )
        if service_role is None or not service_role["rolcanlogin"]:
            raise RuntimeError("Existing LOGIN service role is required")
        if any(bool(service_role[field]) for field in ("rolsuper", "rolcreaterole", "rolcreatedb")):
            raise RuntimeError("Service LOGIN must not be privileged")
        if not service_role["rolinherit"]:
            raise RuntimeError("Service LOGIN must inherit its database authority contract")
        for authority_role in sorted(authority_roles):
            await owner.execute(f"GRANT {_identifier(authority_role)} TO {quoted_role}")
        memberships = await owner.fetch(
            """
            SELECT parent.rolname
            FROM pg_auth_members membership
            JOIN pg_roles parent ON parent.oid = membership.roleid
            JOIN pg_roles member ON member.oid = membership.member
            WHERE member.rolname = $1
              AND parent.rolname = ANY($2::text[])
            ORDER BY parent.rolname
            """,
            role,
            sorted(AUTHORITY_ROLES),
        )
        if {item["rolname"] for item in memberships} != set(authority_roles):
            raise RuntimeError("Service LOGIN must have exactly its database authority contract")
    finally:
        await owner.close()

    runtime = await asyncpg.connect(runtime_url, command_timeout=30)
    try:
        authority_memberships = True
        for authority_role in sorted(authority_roles):
            authority_memberships = authority_memberships and bool(
                await runtime.fetchval(
                    "SELECT pg_has_role(session_user, $1, 'member')", authority_role
                )
            )
        checks = {
            "not_superuser": not bool(await runtime.fetchval("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")),
            "no_create_role": not bool(await runtime.fetchval("SELECT rolcreaterole FROM pg_roles WHERE rolname=current_user")),
            "no_create_db": not bool(await runtime.fetchval("SELECT rolcreatedb FROM pg_roles WHERE rolname=current_user")),
            "private_schema_denied": not bool(await runtime.fetchval("SELECT has_schema_privilege(current_user, 'salary_private', 'USAGE')")),
            "schema_create_denied": not bool(await runtime.fetchval("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")),
            "authority_memberships": authority_memberships,
        }
    finally:
        await runtime.close()
    if not all(checks.values()):
        raise RuntimeError("Runtime database role verification failed")
    return checks


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--authority-role", choices=sorted(AUTHORITY_ROLES), action="append", default=[]
    )
    args = parser.parse_args()
    if not args.apply:
        raise RuntimeError("Use --apply to provision the runtime database role")
    authority_roles = frozenset(args.authority_role)
    if authority_roles not in AUTHORITY_CONTRACTS:
        raise RuntimeError("--authority-role must select one exact process authority contract")
    owner_url = os.getenv("MIGRATION_DATABASE_URL")
    runtime_url = os.getenv("RUNTIME_DATABASE_URL")
    if not owner_url or not runtime_url:
        raise RuntimeError("Migration and runtime database URLs are required")
    checks = await provision(owner_url, runtime_url, authority_roles=authority_roles)
    print("runtime_database_role_verified=true checks=" + str(len(checks)))


if __name__ == "__main__":
    asyncio.run(main())
