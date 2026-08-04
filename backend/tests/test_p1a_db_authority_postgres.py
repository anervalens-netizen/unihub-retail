"""P1-A isolated PostgreSQL authority matrix and immutable-evidence proof."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from secrets import token_urlsafe
from urllib.parse import quote, urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from db.migration_runner import run_migrations


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db/migrations/040_db_authority_append_only.sql"
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
        "advance_store_pnl_generation_head",
        "promote_store_pnl_shadow_generation",
        "rollback_store_pnl_shadow_pointer",
    ):
        assert f"FUNCTION public.{function}" in sql
    assert sql.count("SECURITY DEFINER") >= 6
    assert "sales staging rows are append-only; retention is a later controlled lifecycle" in sql
    assert "sales promotion ledger is append-only" in sql
    assert "store_pnl shadow evidence is append-only" in sql


async def _expect_denied(connection: asyncpg.Connection, sql: str, *args: object) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await connection.execute(sql, *args)


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with CREATEROLE/CREATEDB",
)
async def test_p1a_authority_matrix_and_controlled_cas_are_authenticated() -> None:
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
            "SELECT rolname FROM pg_roles WHERE rolname = ANY($1::text[])", list(AUTHORITIES)
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
            await connection.execute(MIGRATION.read_text(encoding="utf-8"))
            for authority, (principal, password) in test_principals.items():
                await connection.execute(
                    f'CREATE ROLE "{principal}" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT PASSWORD {quote(password)!r}'
                )
                await connection.execute(f'GRANT "{authority}" TO "{principal}"')
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

            web = principal_connections["unihub_web_read"]
            business = principal_connections["unihub_business_write"]
            sales = principal_connections["unihub_sales_import"]
            finance = principal_connections["unihub_finance_import"]
            operations = principal_connections["unihub_operations"]
            migrate = principal_connections["unihub_migrate"]

            # Every row is an independent authenticated session, not SET ROLE.
            assert await web.fetchval("SELECT COUNT(*) FROM stores") == 0
            await _expect_denied(web, "SELECT * FROM sales_import_stage_rows")

            # business-write may create online work, but cannot read import evidence.
            await business.execute("INSERT INTO tasks (title) VALUES ('P1-A role matrix')")
            await _expect_denied(business, "SELECT * FROM sales_import_stage_rows")

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
            await connection.execute(
                """
                UPDATE import_snapshots
                SET manifest = jsonb_build_object(
                        'generation_state', 'validated', 'stage_rows_sha256', $2
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
            assert await finance.fetchval(
                "SELECT advance_store_pnl_generation_head($1, $2, $3, 0, 'legacy', 'r1')",
                "Mobiup",
                date(2197, 8, 1),
                finance_generation,
            ) == 1

            shadow_generation = uuid4()
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

            await migrate.execute("CREATE TABLE p1a_migrate_role_proof (id integer)")
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
        await maintenance.close()
