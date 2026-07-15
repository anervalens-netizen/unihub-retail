from __future__ import annotations

import os
from pathlib import Path

import pytest

from db.connection import get_pool
from scripts.provision_runtime_database_role import (
    SALARY_LINK_COLUMNS,
    SALARY_RECORD_COLUMNS,
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
    assert "REVOKE ALL ON SCHEMA salary_private" in source
    assert "schema_create_denied" in source
    assert "ALTER DEFAULT PRIVILEGES IN SCHEMA public" in source


def test_import_activity_migration_grants_established_runtime_role() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "db/migrations/026_import_master_data_safety.sql"
    ).read_text(encoding="utf-8")
    assert "ON TABLE store_activity_events TO unihub_runtime" in source
    assert "ON SEQUENCE store_activity_events_id_seq TO unihub_runtime" in source


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
