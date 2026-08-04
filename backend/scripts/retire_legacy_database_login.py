#!/usr/bin/env python3
"""Fence or restore the fixed legacy Retail DB LOGIN during controlled cutover."""
from __future__ import annotations

import argparse
import asyncio
import os

from db.connection import connect_database_url


LEGACY_ROLE = "unihub_runtime"


async def set_legacy_login_state(
    owner_url: str, *, allow_login: bool
) -> dict[str, bool]:
    connection = await connect_database_url(
        owner_url, application_name="unihub-retail-legacy-login-cutover"
    )
    try:
        await connection.execute(
            "SELECT pg_advisory_lock(hashtext('unihub-retail:legacy-login-cutover'))"
        )
        role = await connection.fetchrow(
            """
            SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolbypassrls, rolreplication
            FROM pg_roles
            WHERE rolname = $1
            """,
            LEGACY_ROLE,
        )
        if role is None:
            raise RuntimeError("Legacy Retail database role does not exist")
        if any(
            bool(role[name])
            for name in (
                "rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls",
                "rolreplication",
            )
        ):
            raise RuntimeError("Legacy Retail database role has unexpected privileged flags")
        active_sessions = int(
            await connection.fetchval(
                "SELECT count(*) FROM pg_stat_activity WHERE usename = $1 AND pid <> pg_backend_pid()",
                LEGACY_ROLE,
            )
        )
        if active_sessions:
            raise RuntimeError("Legacy Retail database role still has active sessions")
        member_count = int(
            await connection.fetchval(
                """
                SELECT count(*)
                FROM pg_auth_members AS membership
                JOIN pg_roles AS parent ON parent.oid = membership.roleid
                WHERE parent.rolname = $1
                """,
                LEGACY_ROLE,
            )
        )
        if member_count:
            raise RuntimeError("Legacy Retail database role still has member roles")

        expected_before = not allow_login
        if bool(role["rolcanlogin"]) != expected_before:
            raise RuntimeError("Legacy Retail database LOGIN is not in the expected pre-cutover state")
        command = "LOGIN" if allow_login else "NOLOGIN"
        await connection.execute(f"ALTER ROLE {LEGACY_ROLE} {command}")
        verified = bool(
            await connection.fetchval(
                "SELECT rolcanlogin = $2 FROM pg_roles WHERE rolname = $1",
                LEGACY_ROLE,
                allow_login,
            )
        )
        if not verified:
            raise RuntimeError("Legacy Retail database LOGIN state verification failed")
        return {
            "legacy_login_allowed": allow_login,
            "no_active_sessions": True,
            "no_member_roles": True,
        }
    finally:
        await connection.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--apply", action="store_true", help="Set unihub_runtime NOLOGIN.")
    action.add_argument(
        "--rollback", action="store_true", help="Restore LOGIN without changing its credential."
    )
    args = parser.parse_args()
    owner_url = os.getenv("MIGRATION_DATABASE_URL")
    if not owner_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required")
    checks = await set_legacy_login_state(owner_url, allow_login=args.rollback)
    print(
        "legacy_database_login_verified=true allowed="
        + str(checks["legacy_login_allowed"]).lower()
    )


if __name__ == "__main__":
    asyncio.run(main())
