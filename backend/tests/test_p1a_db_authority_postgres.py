"""P1-A isolated PostgreSQL authority matrix and immutable-evidence proof."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import date
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from db.migration_runner import run_migrations
from db.connection import (
    database_principal_has_direct_authority,
    get_pool,
    verify_database_connection_authority,
)
from config import DATABASE_AUTHORITY_CONTRACTS
from scripts.provision_runtime_database_role import provision


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/040_db_authority_append_only.sql"
OWNER_MIGRATION = ROOT / "db/migrations/041_schema_owner_handoff.sql"
AUTHORITIES = (
    "unihub_web_read",
    "unihub_business_write",
    "unihub_sales_import",
    "unihub_finance_import",
    "unihub_operations",
    "unihub_migrate",
)


def test_p1a_migration_declares_exact_authorities_and_definer_cas() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for authority in AUTHORITIES:
        assert authority in sql
    assert "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in sql
    assert "ON ALL TABLES IN SCHEMA" not in sql
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL" in sql
    assert "REVOKE CREATE ON SCHEMA public FROM PUBLIC" in sql
    for function in (
        "advance_sales_generation_head",
        "reserve_sales_import_grile_run",
        "advance_store_pnl_generation_head",
        "stage_store_pnl_generation",
        "promote_store_pnl_generation",
        "seal_store_pnl_generation",
        "complete_store_pnl_generation",
        "promote_store_pnl_shadow_generation",
        "rollback_store_pnl_shadow_pointer",
    ):
        assert f"FUNCTION public.{function}" in sql
    assert sql.count("SECURITY DEFINER") >= 7
    assert "sales staging rows are append-only; retention is a later controlled lifecycle" in sql
    assert "sales promotion ledger is append-only" in sql
    assert "store_pnl shadow evidence is append-only" in sql
    assert "category_name, amount" in sql
    assert "NOBYPASSRLS NOREPLICATION" in sql
    assert "ON salary_records TO unihub_operations" not in sql
    assert (
        "REVOKE ALL ON SEQUENCE store_pnl_generation_ledger_id_seq\n"
        "FROM PUBLIC, unihub_web_read, unihub_business_write, unihub_sales_import,"
    ) in sql

    owner_sql = OWNER_MIGRATION.read_text(encoding="utf-8")
    assert "CREATE ROLE unihub_schema_owner" in owner_sql
    assert "REASSIGN OWNED" not in owner_sql
    assert "namespace.nspname IN ('public', 'salary_private')" in owner_sql
    assert owner_sql.count("= current_user::regrole") == 3
    assert "dependency.deptype = 'e'" in owner_sql
    assert "ALTER SCHEMA public OWNER TO unihub_schema_owner" in owner_sql
    assert "public.reserve_sales_import_grile_run(text,integer)" in owner_sql
    assert "acl.grantee NOT IN (proowner, item.grantee)" in owner_sql


async def _expect_denied(connection: asyncpg.Connection, sql: str, *args: object) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await connection.execute(sql, *args)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with CREATEROLE",
)
async def test_service_login_provisioner_applies_exact_membership_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_url = os.environ["DATABASE_URL"]
    parsed = urlsplit(owner_url)
    principals = {
        "web": (f"p1a_web_{uuid4().hex[:12]}", token_urlsafe(48), True),
        "migrate": (f"p1a_migrate_{uuid4().hex[:12]}", token_urlsafe(48), False),
        "invalid": (f"p1a_invalid_{uuid4().hex[:12]}", token_urlsafe(48), True),
        "direct": (f"p1a_direct_{uuid4().hex[:12]}", token_urlsafe(48), True),
    }
    unexpected_role = f"p1a_extra_{uuid4().hex[:12]}"
    directly_owned_table = f"p1a_direct_owned_{uuid4().hex[:12]}"
    owner = await asyncpg.connect(owner_url)
    try:
        for principal, password, inherits in principals.values():
            flag = "INHERIT" if inherits else "NOINHERIT"
            await owner.execute(
                f'CREATE ROLE "{principal}" LOGIN NOSUPERUSER NOCREATEDB '
                f'NOCREATEROLE {flag} PASSWORD {quote(password)!r}'
            )
        for contract, authority_roles in (
            ("web", frozenset({"unihub_web_read", "unihub_business_write"})),
            ("migrate", frozenset({"unihub_migrate"})),
        ):
            principal, password, _ = principals[contract]
            runtime_url = urlunsplit(
                (
                    parsed.scheme,
                    f"{quote(principal)}:{quote(password, safe='')}@{parsed.hostname}:{parsed.port}",
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )
            checks = await provision(
                owner_url, runtime_url, authority_roles=authority_roles
            )
            assert all(checks.values())

        invalid_principal, invalid_password, _ = principals["invalid"]
        invalid_url = urlunsplit(
            (
                parsed.scheme,
                f"{quote(invalid_principal)}:{quote(invalid_password, safe='')}@{parsed.hostname}:{parsed.port}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
        await owner.execute(f'CREATE ROLE "{unexpected_role}" NOLOGIN')
        await owner.execute(f'GRANT "{unexpected_role}" TO "{invalid_principal}"')
        with pytest.raises(RuntimeError, match="exactly its database authority contract"):
            await provision(
                owner_url,
                invalid_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        assert not await owner.fetchval(
            "SELECT pg_has_role($1, 'unihub_web_read', 'member')",
            invalid_principal,
        )
        assert not await owner.fetchval(
            "SELECT pg_has_role($1, 'unihub_business_write', 'member')",
            invalid_principal,
        )

        direct_principal, direct_password, _ = principals["direct"]
        direct_url = urlunsplit(
            (
                parsed.scheme,
                f"{quote(direct_principal)}:{quote(direct_password, safe='')}@{parsed.hostname}:{parsed.port}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
        await owner.execute(f'GRANT SELECT ON TABLE stores TO "{direct_principal}"')
        with pytest.raises(RuntimeError, match="direct grants, default privileges, or ownership"):
            await provision(
                owner_url,
                direct_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        assert not await owner.fetchval(
            "SELECT pg_has_role($1, 'unihub_web_read', 'member')",
            direct_principal,
        )
        await owner.execute(f'REVOKE SELECT ON TABLE stores FROM "{direct_principal}"')

        await owner.execute(f'CREATE TABLE "{directly_owned_table}" (id integer)')
        await owner.execute(
            f'ALTER TABLE "{directly_owned_table}" OWNER TO "{direct_principal}"'
        )
        with pytest.raises(RuntimeError, match="direct grants, default privileges, or ownership"):
            await provision(
                owner_url,
                direct_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        await owner.execute(f'DROP TABLE "{directly_owned_table}"')

        await owner.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT SELECT ON TABLES TO "{direct_principal}"'
        )
        with pytest.raises(RuntimeError, match="direct grants, default privileges, or ownership"):
            await provision(
                owner_url,
                direct_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        await owner.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'REVOKE SELECT ON TABLES FROM "{direct_principal}"'
        )

        web_principal, web_password, _ = principals["web"]
        web_url = urlunsplit(
            (
                parsed.scheme,
                f"{quote(web_principal)}:{quote(web_password, safe='')}@{parsed.hostname}:{parsed.port}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
        await owner.execute(f'ALTER ROLE "{web_principal}" BYPASSRLS')
        with pytest.raises(RuntimeError, match="must not be privileged"):
            await provision(
                owner_url,
                web_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        await owner.execute(f'ALTER ROLE "{web_principal}" NOBYPASSRLS')

        await owner.execute(f'GRANT "{unexpected_role}" TO "{web_principal}"')
        with pytest.raises(RuntimeError, match="exactly its database authority contract"):
            await provision(
                owner_url,
                web_url,
                authority_roles=frozenset(
                    {"unihub_web_read", "unihub_business_write"}
                ),
            )
        await owner.execute(f'REVOKE "{unexpected_role}" FROM "{web_principal}"')

        web_contract = DATABASE_AUTHORITY_CONTRACTS["web"]
        monkeypatch.setitem(
            DATABASE_AUTHORITY_CONTRACTS,
            "web",
            replace(web_contract, principal=web_principal),
        )
        await owner.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT SELECT ON TABLES TO "{web_principal}"'
        )
        web_runtime = await asyncpg.connect(web_url)
        try:
            with pytest.raises(
                RuntimeError,
                match="direct grants, default privileges, or ownership",
            ):
                await verify_database_connection_authority(web_runtime, "web")
        finally:
            await web_runtime.close()
            await owner.execute(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'REVOKE SELECT ON TABLES FROM "{web_principal}"'
            )

        migrate_principal, migrate_password, _ = principals["migrate"]
        migrate_url = urlunsplit(
            (
                parsed.scheme,
                f"{quote(migrate_principal)}:{quote(migrate_password, safe='')}@{parsed.hostname}:{parsed.port}",
                parsed.path,
                parsed.query,
                parsed.fragment,
            )
        )
        migrate = await asyncpg.connect(migrate_url)
        try:
            await _expect_denied(migrate, "CREATE TABLE p1a_provisioner_denied(id integer)")
            async with migrate.transaction():
                await migrate.execute("SET LOCAL ROLE unihub_schema_owner")
                await migrate.execute("CREATE TABLE p1a_provisioner_owner(id integer)")
                await migrate.execute("DROP TABLE p1a_provisioner_owner")
        finally:
            await migrate.close()
    finally:
        await owner.execute(f'DROP TABLE IF EXISTS "{directly_owned_table}"')
        await owner.execute(f'DROP ROLE IF EXISTS "{unexpected_role}"')
        for principal, _, _ in principals.values():
            await owner.execute(f'DROP ROLE IF EXISTS "{principal}"')
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with CREATEROLE",
)
async def test_authenticated_runtime_rejects_all_shared_dependency_acl_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_url = os.environ["DATABASE_URL"]
    parsed = urlsplit(owner_url)
    principal = f"p1a_catalog_{uuid4().hex[:12]}"
    password = token_urlsafe(48)
    fdw_name = f"p1a_fdw_{uuid4().hex[:12]}"
    server_name = f"p1a_server_{uuid4().hex[:12]}"
    table_name = f"p1a_column_{uuid4().hex[:12]}"
    large_object_oid: int | None = None
    runtime_url = urlunsplit(
        (
            parsed.scheme,
            f"{quote(principal)}:{quote(password, safe='')}@{parsed.hostname}:{parsed.port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
    owner = await asyncpg.connect(owner_url)
    runtime: asyncpg.Connection | None = None
    try:
        await owner.execute(
            f'CREATE ROLE "{principal}" LOGIN NOSUPERUSER NOCREATEDB '
            f'NOCREATEROLE INHERIT PASSWORD {quote(password)!r}'
        )
        checks = await provision(
            owner_url,
            runtime_url,
            authority_roles=frozenset(
                {"unihub_web_read", "unihub_business_write"}
            ),
        )
        assert all(checks.values())
        web_contract = DATABASE_AUTHORITY_CONTRACTS["web"]
        monkeypatch.setitem(
            DATABASE_AUTHORITY_CONTRACTS,
            "web",
            replace(web_contract, principal=principal),
        )
        runtime = await asyncpg.connect(runtime_url)
        assert not await database_principal_has_direct_authority(runtime, principal)

        async def assert_rejected(grant_sql: str, revoke_sql: str) -> None:
            await owner.execute(grant_sql)
            try:
                assert await database_principal_has_direct_authority(runtime, principal)
                with pytest.raises(
                    RuntimeError,
                    match="direct grants, default privileges, or ownership",
                ):
                    await verify_database_connection_authority(runtime, "web")
            finally:
                await owner.execute(revoke_sql)
            assert not await database_principal_has_direct_authority(runtime, principal)

        await assert_rejected(
            f'GRANT USAGE ON LANGUAGE plpgsql TO "{principal}"',
            f'REVOKE USAGE ON LANGUAGE plpgsql FROM "{principal}"',
        )
        await assert_rejected(
            f'GRANT CREATE ON TABLESPACE pg_default TO "{principal}"',
            f'REVOKE CREATE ON TABLESPACE pg_default FROM "{principal}"',
        )
        await assert_rejected(
            f'GRANT SET ON PARAMETER work_mem TO "{principal}"',
            f'REVOKE SET ON PARAMETER work_mem FROM "{principal}"',
        )

        await owner.execute(f'CREATE FOREIGN DATA WRAPPER "{fdw_name}" NO HANDLER')
        await assert_rejected(
            f'GRANT USAGE ON FOREIGN DATA WRAPPER "{fdw_name}" TO "{principal}"',
            f'REVOKE USAGE ON FOREIGN DATA WRAPPER "{fdw_name}" FROM "{principal}"',
        )
        await owner.execute(
            f'CREATE SERVER "{server_name}" FOREIGN DATA WRAPPER "{fdw_name}"'
        )
        await assert_rejected(
            f'GRANT USAGE ON FOREIGN SERVER "{server_name}" TO "{principal}"',
            f'REVOKE USAGE ON FOREIGN SERVER "{server_name}" FROM "{principal}"',
        )

        large_object_oid = int(await owner.fetchval("SELECT lo_create(0)"))
        await assert_rejected(
            f'GRANT SELECT ON LARGE OBJECT {large_object_oid} TO "{principal}"',
            f'REVOKE SELECT ON LARGE OBJECT {large_object_oid} FROM "{principal}"',
        )
        await owner.execute(f'CREATE TABLE "{table_name}" (value integer)')
        await assert_rejected(
            f'GRANT SELECT (value) ON TABLE "{table_name}" TO "{principal}"',
            f'REVOKE SELECT (value) ON TABLE "{table_name}" FROM "{principal}"',
        )
    finally:
        if runtime is not None:
            await runtime.close()
        await owner.execute(f'DROP SERVER IF EXISTS "{server_name}"')
        await owner.execute(f'DROP FOREIGN DATA WRAPPER IF EXISTS "{fdw_name}"')
        await owner.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        if large_object_oid is not None:
            await owner.fetchval("SELECT lo_unlink($1)", large_object_oid)
        await owner.execute(f'DROP ROLE IF EXISTS "{principal}"')
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with CREATEROLE",
)
async def test_schema_owner_handoff_does_not_capture_foreign_owned_objects() -> None:
    foreign_role = f"p1a_foreign_{uuid4().hex[:12]}"
    table_name = f"p1a_foreign_{uuid4().hex[:12]}"
    pool = await get_pool()
    async with pool.acquire() as connection:
        try:
            await connection.execute(f'CREATE ROLE "{foreign_role}" NOLOGIN')
            await connection.execute(f'CREATE TABLE public."{table_name}" (id integer)')
            await connection.execute(
                f'ALTER TABLE public."{table_name}" OWNER TO "{foreign_role}"'
            )

            await connection.execute(OWNER_MIGRATION.read_text(encoding="utf-8"))

            assert await connection.fetchval(
                """
                SELECT pg_get_userbyid(class.relowner)
                FROM pg_class AS class
                JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
                WHERE namespace.nspname = 'public' AND class.relname = $1
                """,
                table_name,
            ) == foreign_role
        finally:
            await connection.execute(f'DROP TABLE IF EXISTS public."{table_name}"')
            await connection.execute(f'DROP ROLE IF EXISTS "{foreign_role}"')


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with CREATEROLE/CREATEDB",
)
async def test_p1a_authority_matrix_and_controlled_cas_are_authenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every authority uses a distinct temporary LOGIN with negative DML proof."""
    parsed = urlsplit(os.environ["DATABASE_URL"])
    database = f"p1a_authority_{uuid4().hex}_test"
    maintenance_url = urlunsplit(
        (parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment)
    )
    database_url = urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment)
    )
    maintenance = await asyncpg.connect(maintenance_url)
    existing_roles = {
        row["rolname"]
        for row in await maintenance.fetch(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY($1::text[])",
            [*AUTHORITIES, "unihub_schema_owner"],
        )
    }
    test_principals = {
        authority: (f"p1a_{authority.removeprefix('unihub_')}_{uuid4().hex[:12]}", token_urlsafe(48))
        for authority in AUTHORITIES
    }
    principal_connections: dict[str, asyncpg.Connection] = {}
    try:
        await maintenance.execute(f'CREATE DATABASE "{database}"')
        await run_migrations(database_url)
        connection = await asyncpg.connect(database_url)
        try:
            for authority, (principal, password) in test_principals.items():
                inheritance = "NOINHERIT" if authority == "unihub_migrate" else "INHERIT"
                await connection.execute(
                    f'CREATE ROLE "{principal}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE {inheritance} PASSWORD {quote(password)!r}'
                )
                membership = (
                    "INHERIT FALSE, SET FALSE"
                    if authority == "unihub_migrate"
                    else "INHERIT TRUE, SET FALSE"
                )
                await connection.execute(
                    f'GRANT "{authority}" TO "{principal}" WITH {membership}'
                )
                if authority == "unihub_migrate":
                    await connection.execute(
                        f'GRANT unihub_schema_owner TO "{principal}" '
                        "WITH INHERIT FALSE, SET TRUE"
                    )
                principal_url = urlunsplit(
                    (
                        parsed.scheme,
                        f"{quote(principal)}:{quote(password, safe='')}@{parsed.hostname}:{parsed.port}",
                        f"/{database}",
                        parsed.query,
                        parsed.fragment,
                    )
                )
                principal_connections[authority] = await asyncpg.connect(principal_url)
            for authority, principal_connection in principal_connections.items():
                principal, _ = test_principals[authority]
                assert await principal_connection.fetchval("SELECT session_user") == principal
                assert await principal_connection.fetchval("SELECT current_user") == principal
                assert await principal_connection.fetchval(
                    "SELECT pg_has_role(session_user, $1, 'member')", authority
                )
                assert not await database_principal_has_direct_authority(
                    connection,
                    principal,
                )

            for authority, principal_connection in principal_connections.items():
                has_temporary = bool(
                    await principal_connection.fetchval(
                        "SELECT has_database_privilege(current_user, current_database(), 'TEMPORARY')"
                    )
                )
                assert has_temporary is (authority == "unihub_sales_import")

            web = principal_connections["unihub_web_read"]
            business = principal_connections["unihub_business_write"]
            sales = principal_connections["unihub_sales_import"]
            finance = principal_connections["unihub_finance_import"]
            operations = principal_connections["unihub_operations"]
            migrate = principal_connections["unihub_migrate"]

            # The future Finance credential is not created in production, but
            # its authenticated principal contract is executable in isolation.
            finance_principal, _ = test_principals["unihub_finance_import"]
            finance_contract = DATABASE_AUTHORITY_CONTRACTS["finance_import"]
            monkeypatch.setitem(
                DATABASE_AUTHORITY_CONTRACTS,
                "finance_import",
                replace(finance_contract, principal=finance_principal),
            )
            await verify_database_connection_authority(finance, "finance_import")

            # Every row is an independent authenticated session, not SET ROLE.
            assert await web.fetchval("SELECT COUNT(*) FROM stores") == 0
            await _expect_denied(web, "SELECT * FROM sales_import_stage_rows")

            # business-write may create online work, but cannot read import evidence.
            await business.execute("INSERT INTO tasks (title) VALUES ('P1-A role matrix')")
            await business.execute(
                "INSERT INTO visits_snapshot (asm, month) VALUES ('P1-A', '2197-08')"
            )
            await _expect_denied(business, "SELECT * FROM sales_import_stage_rows")
            await _expect_denied(
                business,
                "UPDATE grile_store_observations SET error_code = error_code WHERE false",
            )

            # Real operations surfaces include reference reads, Grile DML and
            # their owned sequences; they still cannot use import authority.
            assert await operations.fetchval("SELECT COUNT(*) FROM stores") == 0
            await connection.execute(
                "INSERT INTO stores (site_code, locatie, firma, regional, asm, "
                "first_seen_month, last_seen_month) "
                "VALUES ('P1A', 'P1-A', 'Mobiup', 'R', 'A', '2197-08', '2197-08')"
            )
            assert await operations.fetchval(
                "INSERT INTO grile_runs (run_month) VALUES ('2197-09') RETURNING id"
            )
            await operations.execute(
                """
                INSERT INTO agent_targets (import_month, site_code, agent, target_value)
                VALUES ('2197-09', 'P1A', 'Agent', 1)
                ON CONFLICT (import_month, site_code, agent) DO UPDATE
                SET target_value = EXCLUDED.target_value
                """
            )
            await _expect_denied(
                operations,
                "UPDATE grile_store_observations SET error_code = error_code WHERE false",
            )
            await _expect_denied(
                operations, "DELETE FROM grile_runs WHERE run_month = '2197-09'"
            )
            await _expect_denied(operations, "SELECT * FROM sales_import_stage_rows")
            await _expect_denied(operations, "SELECT * FROM salary_records")
            await _expect_denied(operations, "SELECT * FROM historical_monthly_sales")
            await _expect_denied(operations, "SELECT * FROM store_pnl_site_links")

            # Ledger numbering is owned by the definer function, not Finance.
            await _expect_denied(
                finance,
                "SELECT nextval('store_pnl_generation_ledger_id_seq')",
            )

            # Reporting rebuild needs explicit TRUNCATE/MAINTAIN, not table ownership.
            await sales.execute("TRUNCATE premium_glass_item_models")
            await sales.execute("ANALYZE premium_glass_item_models")
            await sales.execute("ANALYZE reporting_agent_day")
            await _expect_denied(
                sales,
                "INSERT INTO grile_runs (run_month, source) VALUES ('2197-10', 'auto')",
            )
            await _expect_denied(
                sales,
                "UPDATE grile_runs SET status = status WHERE run_month = '2197-10'",
            )
            await _expect_denied(
                sales, "UPDATE agent_targets SET target_value = target_value WHERE false"
            )
            await _expect_denied(
                sales,
                "UPDATE reporting_agent_day SET total_sales = total_sales WHERE false",
            )

            token = uuid4()
            owner = uuid4()
            snapshot_id = await connection.fetchval(
                """
                INSERT INTO import_snapshots (
                    import_month, filename, rows_in_file, status, generation_token,
                    owner_id, lease_until
                ) VALUES ('2197-08', 'p1a.xlsx', 1, 'processing', $1, $2, now() + interval '1 hour')
                RETURNING id
                """,
                token,
                owner,
            )

            # sales-import may append stage evidence.  It cannot edit/delete it
            # or move the head directly; the SECURITY DEFINER CAS is required.
            await sales.execute(
                """
                INSERT INTO sales_import_stage_rows (
                    snapshot_id, row_number, import_month, sale_date, site_code,
                    locatie, firma, regional, asm, bon_nr, item_code, item_name,
                    quantity, unit_price, total_value, agent, is_cartela, is_return
                ) VALUES ($1, 1, '2197-08', DATE '2197-08-01', 'P1A',
                    'P1-A', 'Mobiup', 'R', 'A', 'B', 'I', 'Item',
                    1, 1.00, 1.00, 'Agent', false, false)
                """,
                snapshot_id,
            )
            await _expect_denied(
                sales,
                "UPDATE sales_import_stage_rows SET item_name = 'tamper' WHERE snapshot_id = $1",
                snapshot_id,
            )
            await _expect_denied(
                sales,
                "INSERT INTO sales_generation_heads (import_month, snapshot_id, revision) VALUES ('2197-08', $1, 1)",
                snapshot_id,
            )

            digest = await connection.fetchval("SELECT sales_stage_rows_sha256($1)", snapshot_id)
            with pytest.raises(
                asyncpg.PostgresError,
                match="lacks validated stage controls",
            ):
                await sales.fetchrow(
                    "SELECT * FROM advance_sales_generation_head($1, $2, $3, $4, 0)",
                    "2197-08",
                    snapshot_id,
                    token,
                    owner,
                )
            await connection.execute(
                """
                    UPDATE import_snapshots
                    SET manifest = jsonb_build_object(
                            'generation_state', 'validated',
                            'stage_rows_sha256', $2::text,
                            'rows_imported', 1,
                            'store_count', 1,
                            'total_quantity', 1,
                            'total_value', 1.00,
                            'max_sale_date', '2197-08-01',
                            'anomalies', '[]'::jsonb
                    ),
                    manifest_sha256 = repeat('a', 64)
                WHERE id = $1
                """,
                snapshot_id,
                digest,
            )
            head = await sales.fetchrow(
                "SELECT * FROM advance_sales_generation_head($1, $2, $3, $4, 0)",
                "2197-08",
                snapshot_id,
                token,
                owner,
            )
            assert head["previous_snapshot_id"] is None and head["revision"] == 1
            await connection.execute(
                "UPDATE import_snapshots SET status = 'completed' WHERE id = $1", snapshot_id
            )
            assert await sales.fetchval(
                "SELECT record_sales_generation_promotion($1, NULL, $2, 1, 'promote', 'p1a:test', NULL)",
                "2197-08",
                snapshot_id,
            )
            with pytest.raises(asyncpg.PostgresError, match="cannot be recorded as promote|lineage"):
                await sales.fetchval(
                    "SELECT record_sales_generation_promotion($1, NULL, $2, 1, 'rollback', 'p1a:test', NULL)",
                    "2197-08",
                    snapshot_id,
                )
            auto_run_id = await sales.fetchval(
                "SELECT reserve_sales_import_grile_run($1, $2)",
                "2197-08",
                snapshot_id,
            )
            assert isinstance(auto_run_id, int)
            auto_run = await sales.fetchrow(
                "SELECT source, source_snapshot_id, triggered_by_sub FROM grile_runs WHERE id = $1",
                auto_run_id,
            )
            assert dict(auto_run) == {
                "source": "auto",
                "source_snapshot_id": snapshot_id,
                "triggered_by_sub": "system:sales-import",
            }
            await _expect_denied(
                sales,
                """
                INSERT INTO sales_generation_promotions (
                    import_month, to_snapshot_id, head_revision, action, requested_by_sub
                ) VALUES ('2197-08', $1, 1, 'promote', 'tamper')
                """,
                snapshot_id,
            )

            finance_generation = uuid4()
            with pytest.raises(asyncpg.PostgresError, match="must start in building state"):
                await finance.execute(
                    """
                    INSERT INTO store_pnl_generations (
                        id, operation, authority_manifest_sha256, authority_manifest,
                        generation_manifest_sha256, generation_manifest, state, promoted_at
                    ) VALUES ($1, 'promote', repeat('8', 64), '{}'::jsonb,
                        repeat('9', 64), '{}'::jsonb, 'promoted', now())
                    """,
                    uuid4(),
                )
            await connection.execute(
                """
                INSERT INTO store_pnl_generations (
                    id, operation, authority_manifest_sha256, authority_manifest,
                    generation_manifest_sha256, generation_manifest, state
                ) VALUES ($1, 'promote', repeat('a', 64), '{}'::jsonb,
                    repeat('b', 64), '{}'::jsonb, 'building')
                """,
                finance_generation,
            )
            await _expect_denied(
                finance,
                "UPDATE store_pnl_generations SET state = 'promoted', promoted_at = now() WHERE id = $1",
                finance_generation,
            )
            await _expect_denied(
                finance,
                """
                INSERT INTO store_pnl_generation_ledger (
                    generation_id, action, details
                ) VALUES ($1, 'staged', '{}'::jsonb)
                """,
                finance_generation,
            )
            await _expect_denied(
                finance,
                "SELECT append_store_pnl_generation_ledger($1, 'staged', NULL, NULL, $2::jsonb)",
                finance_generation,
                '{"manifest_sha256":"' + ("b" * 64) + '"}',
            )
            await connection.execute(
                """
                INSERT INTO store_pnl_generation_scopes (
                    generation_id, company_name, period, revision_id, parent_revision_id,
                    cutoff, source_path, source_sha256, candidate_rows_sha256,
                    candidate_coverage_sha256, candidate_row_count, candidate_total_amount,
                    preimage_sha256, expected_head_revision
                ) VALUES ($1, 'Mobiup', DATE '2197-08-01', 'r1', 'legacy',
                    DATE '2197-08-31', 'p1a.xls', repeat('a', 64), repeat('b', 64),
                    repeat('c', 64), 1, 1.00, repeat('d', 64), 0)
                """,
                finance_generation,
            )
            await finance.execute(
                """
                INSERT INTO store_pnl_generation_rows (
                    generation_id, row_set, company_name, period, source_site_code,
                    source_location_name, category_code, category_name, amount,
                    source_file, source_sha256
                ) VALUES ($1, 'candidate', 'Mobiup', DATE '2197-08-01', 'P1A',
                    'P1-A', 'v1', 'Venit', 1.00, 'p1a.xls', repeat('a', 64))
                """,
                finance_generation,
            )
            with pytest.raises(asyncpg.PostgresError, match="cannot be sealed from its evidence"):
                await finance.execute(
                    "SELECT stage_store_pnl_generation($1, $2)",
                    finance_generation,
                    "b" * 64,
                )
            await connection.execute(
                "UPDATE store_pnl_generations SET state = 'staged' WHERE id = $1",
                finance_generation,
            )
            await _expect_denied(
                finance,
                """
                INSERT INTO store_pnl_generation_heads (
                    company_name, period, active_generation_id, revision, revision_id
                ) VALUES ('Mobiup', DATE '2197-08-01', $1, 1, 'r1')
                """,
                finance_generation,
            )
            await _expect_denied(
                finance,
                "SELECT advance_store_pnl_generation_head($1, $2, $3, 0, 'legacy', 'r1')",
                "Mobiup",
                date(2197, 8, 1),
                finance_generation,
            )
            await _expect_denied(
                finance,
                "DELETE FROM store_pnl_monthly WHERE company_name = 'Mobiup'",
            )
            await _expect_denied(
                finance,
                "INSERT INTO store_pnl_monthly (company_name, period, source_site_code, "
                "source_location_name, category_code, category_name, amount, data_kind) "
                "VALUES ('Mobiup', DATE '2197-08-01', 'P1A', 'P1-A', 'v1', 'Venit', 1, 'actual')",
            )

            shadow_generation = uuid4()
            with pytest.raises(asyncpg.PostgresError, match="must start unsealed and staged"):
                await operations.execute(
                    """
                    INSERT INTO store_pnl_shadow_generations (
                        id, scope, scope_sha256, input_cutoff, source_sha256, input_sha256,
                        legacy_ruleset_sha256, effective_ruleset_sha256, legacy_model_sha256,
                        effective_model_sha256, legacy_output_sha256, effective_output_sha256,
                        fiscal_delta, input_or_model_delta, state, promoted_at
                    ) VALUES ($1, '[]'::jsonb, repeat('a', 64), DATE '2197-08-01',
                        repeat('b', 64), repeat('c', 64), repeat('d', 64), repeat('e', 64),
                        repeat('f', 64), repeat('0', 64), repeat('1', 64), repeat('2', 64),
                        '{}'::jsonb, '{}'::jsonb, 'promoted', now())
                    """,
                    uuid4(),
                )
            await connection.execute(
                """
                INSERT INTO store_pnl_shadow_generations (
                    id, scope, scope_sha256, input_cutoff, source_sha256, input_sha256,
                    legacy_ruleset_sha256, effective_ruleset_sha256, legacy_model_sha256,
                    effective_model_sha256, legacy_output_sha256, effective_output_sha256,
                    fiscal_delta, input_or_model_delta
                ) VALUES ($1, '[]'::jsonb, repeat('a', 64), DATE '2197-08-01',
                    repeat('b', 64), repeat('c', 64), repeat('d', 64), repeat('e', 64),
                    repeat('f', 64), repeat('0', 64), repeat('1', 64), repeat('2', 64),
                    '{}'::jsonb, '{}'::jsonb)
                """,
                shadow_generation,
            )
            await _expect_denied(
                operations,
                "UPDATE store_pnl_shadow_pointer SET revision = revision + 1 WHERE id = 1",
            )
            await operations.execute("SELECT seal_store_pnl_shadow_generation($1)", shadow_generation)
            # Owner-only fault injection simulates an out-of-band tamper after
            # seal.  Promote must rehash, not trust the seal metadata blindly.
            await connection.execute(
                "ALTER TABLE store_pnl_shadow_rows DISABLE TRIGGER trg_store_pnl_shadow_rows_immutable"
            )
            await connection.execute(
                """
                INSERT INTO store_pnl_shadow_rows (
                    generation_id, variant, company_name, period, site_code,
                    source_site_code, source_location_name, category_code,
                    category_name, amount
                ) VALUES ($1, 'legacy_v2', 'Mobiup', DATE '2197-08-01', 'P1A',
                    'P1A', 'P1-A', 'v1', 'Venit', 1.00)
                """,
                shadow_generation,
            )
            await connection.execute(
                "ALTER TABLE store_pnl_shadow_rows ENABLE TRIGGER trg_store_pnl_shadow_rows_immutable"
            )
            with pytest.raises(asyncpg.PostgresError, match="sealed digest"):
                await operations.fetchval(
                    "SELECT promote_store_pnl_shadow_generation($1, 0)", shadow_generation
                )

            shadow_success = uuid4()
            await connection.execute(
                """
                INSERT INTO store_pnl_shadow_generations (
                    id, scope, scope_sha256, input_cutoff, source_sha256, input_sha256,
                    legacy_ruleset_sha256, effective_ruleset_sha256, legacy_model_sha256,
                    effective_model_sha256, legacy_output_sha256, effective_output_sha256,
                    fiscal_delta, input_or_model_delta
                ) VALUES ($1, '[]'::jsonb, repeat('3', 64), DATE '2197-08-01',
                    repeat('4', 64), repeat('5', 64), repeat('6', 64), repeat('7', 64),
                    repeat('8', 64), repeat('9', 64), repeat('a', 64), repeat('b', 64),
                    '{}'::jsonb, '{}'::jsonb)
                """,
                shadow_success,
            )
            await operations.execute("SELECT seal_store_pnl_shadow_generation($1)", shadow_success)
            assert await operations.fetchval(
                "SELECT promote_store_pnl_shadow_generation($1, 0)", shadow_success
            ) == 1

            await _expect_denied(
                migrate, "ALTER TABLE stores ADD COLUMN p1a_owner_proof integer"
            )
            await _expect_denied(web, "SET ROLE unihub_schema_owner")
            async with migrate.transaction():
                await migrate.execute("SET LOCAL ROLE unihub_schema_owner")
                await migrate.execute("ALTER TABLE stores ADD COLUMN p1a_owner_proof integer")
                await migrate.execute("ALTER TABLE stores DROP COLUMN p1a_owner_proof")
                await migrate.execute(
                    "CREATE FUNCTION p1a_migrate_default_acl_proof() RETURNS integer "
                    "LANGUAGE SQL AS 'SELECT 1'"
                )
            await _expect_denied(web, "SELECT p1a_migrate_default_acl_proof()")
            async with migrate.transaction():
                await migrate.execute("SET LOCAL ROLE unihub_schema_owner")
                await migrate.execute("DROP FUNCTION p1a_migrate_default_acl_proof()")
        finally:
            for principal_connection in principal_connections.values():
                await principal_connection.close()
            await connection.close()
    finally:
        await maintenance.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        for principal, _ in test_principals.values():
            await maintenance.execute(f'DROP ROLE IF EXISTS "{principal}"')
        for authority in AUTHORITIES:
            if authority not in existing_roles:
                await maintenance.execute(f'DROP ROLE IF EXISTS "{authority}"')
        if "unihub_schema_owner" not in existing_roles:
            await maintenance.execute("DROP ROLE IF EXISTS unihub_schema_owner")
        await maintenance.close()
