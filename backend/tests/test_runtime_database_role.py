from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import asyncpg
import pytest

from db.connection import get_migrations_dir, get_pool, get_schema_path
from db.migration_runner import BASELINE_REPLAY_MIGRATIONS, load_migration_manifest
from scripts.provision_runtime_database_role import (
    SALARY_LINK_COLUMNS,
    SALARY_RECORD_COLUMNS,
    AUTHORITY_ROLES,
    _runtime_credentials,
)


def test_runtime_url_requires_separate_strong_credentials() -> None:
    role, password, database = _runtime_credentials(
        "postgresql://unihub_runtime:abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456@127.0.0.1:5432/unihub"
    )
    assert (role, database) == ("unihub_runtime", "unihub")
    assert len(password) >= 48
    for invalid in (
        "postgresql://Owner-Bad:abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456@db/unihub",
        "postgresql://runtime:short@db/unihub",
        "postgresql://runtime:abcdefghijklmnopqrstuvwxyz_ABCDEFGHIJKLMNOPQRSTUVWXYZ_123456@db/",
    ):
        with pytest.raises(RuntimeError, match="credentials are invalid"):
            _runtime_credentials(invalid)


def test_runtime_salary_grants_exclude_private_columns() -> None:
    assert "cnp" not in SALARY_RECORD_COLUMNS
    assert "salary_cnp" not in SALARY_LINK_COLUMNS
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts/provision_runtime_database_role.py"
    ).read_text(encoding="utf-8")
    assert "private_schema_denied" in source
    assert "schema_create_denied" in source
    assert "ALTER DEFAULT PRIVILEGES" not in source
    assert "ON ALL TABLES IN SCHEMA public" not in source
    assert "CREATE ROLE" not in source
    assert "ALTER ROLE" not in source
    assert "SET ROLE" not in source
    assert "AUTHORITY_ROLES" in source


def test_import_activity_migration_grants_established_runtime_role() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "db/migrations/026_import_master_data_safety.sql"
    ).read_text(encoding="utf-8")
    assert "ON TABLE store_activity_events TO unihub_runtime" in source
    assert "ON SEQUENCE store_activity_events_id_seq TO unihub_runtime" in source


def test_grile_sync_audit_migration_grants_established_runtime_role() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "db/migrations/027_grile_target_sync_audit.sql"
    ).read_text(encoding="utf-8")
    assert "ON TABLE grile_agent_target_sync_runs TO unihub_runtime" in source
    assert (
        "ON SEQUENCE grile_agent_target_sync_runs_id_seq TO unihub_runtime"
        in source
    )


def test_grile_monthly_manifest_migration_grants_established_runtime_role() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "db/migrations/028_grile_monthly_fail_closed.sql"
    ).read_text(encoding="utf-8")
    assert "ON TABLE grile_monthly_manifests TO unihub_runtime" in source
    assert (
        "ON SEQUENCE grile_monthly_manifests_id_seq TO unihub_runtime"
        in source
    )


@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)
async def test_salary_identity_contract_constraints_are_installed() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        constraints = await connection.fetch(
                """
                SELECT constraint_name
                FROM information_schema.table_constraints
                WHERE table_schema IN ('public', 'salary_private')
                  AND table_name IN ('salary_records', 'agent_salary_links')
                """
            )
    names = {row["constraint_name"] for row in constraints}
    assert {
        "salary_records_person_id_format",
        "salary_records_person_id_fkey",
        "agent_salary_links_person_id_format",
        "agent_salary_links_person_id_fkey",
        "agent_salary_links_identity_state",
    } <= names


@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)
def test_provisioner_declares_only_no_login_authority_contracts() -> None:
    assert AUTHORITY_ROLES == {
        "unihub_web_read",
        "unihub_business_write",
        "unihub_sales_import",
        "unihub_finance_import",
        "unihub_operations",
        "unihub_migrate",
    }


@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)
async def test_upgrade_037_to_039_revokes_preexisting_runtime_sequence_acl() -> None:
    parsed = urlsplit(os.environ["DATABASE_URL"])
    database = f"p0b_acl_{uuid4().hex}_test"
    maintenance_url = urlunsplit(
        (parsed.scheme, parsed.netloc, "/postgres", parsed.query, parsed.fragment)
    )
    upgrade_url = urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{database}", parsed.query, parsed.fragment)
    )
    maintenance = await asyncpg.connect(maintenance_url)
    role_created = False
    try:
        await maintenance.execute(f'CREATE DATABASE "{database}"')
        role_exists = await maintenance.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='unihub_runtime')"
        )
        if not role_exists:
            await maintenance.execute(
                "CREATE ROLE unihub_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT"
            )
            role_created = True

        upgrade = await asyncpg.connect(upgrade_url)
        try:
            manifest = load_migration_manifest()
            migrations_dir = get_migrations_dir()
            await upgrade.execute(get_schema_path().read_text(encoding="utf-8"))
            replay = [
                name
                for name in manifest.checksums
                if name in BASELINE_REPLAY_MIGRATIONS
                or (manifest.incorporated_through < name <= "037_sales_generation_stage_integrity.sql")
            ]
            for name in replay:
                await upgrade.execute((migrations_dir / name).read_text(encoding="utf-8"))

            await upgrade.execute(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                "TO unihub_runtime"
            )
            await upgrade.execute(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public "
                "TO unihub_runtime"
            )
            await upgrade.execute(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO unihub_runtime"
            )
            for name in (
                "038_retire_replace_month_snapshot.sql",
                "039_store_pnl_authoritative_generations.sql",
            ):
                await upgrade.execute((migrations_dir / name).read_text(encoding="utf-8"))

            assert await upgrade.fetchval(
                "SELECT to_regprocedure('public.replace_month_snapshot(text)') IS NULL"
            )
            assert not await upgrade.fetchval(
                "SELECT has_table_privilege('unihub_runtime', 'store_pnl_monthly', 'INSERT')"
            )
            for table in PNL_AUTHORITY_TABLES:
                assert not await upgrade.fetchval(
                    "SELECT has_table_privilege('unihub_runtime', $1, 'SELECT')",
                    table,
                )
            for sequence in PNL_AUTHORITY_SEQUENCES:
                for privilege in ("USAGE", "SELECT", "UPDATE"):
                    assert not await upgrade.fetchval(
                        "SELECT has_sequence_privilege('unihub_runtime', $1, $2)",
                        sequence,
                        privilege,
                    )
        finally:
            await upgrade.close()
    finally:
        await maintenance.execute(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
        if role_created:
            await maintenance.execute("DROP ROLE IF EXISTS unihub_runtime")
        await maintenance.close()
