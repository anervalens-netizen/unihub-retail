from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import scripts.match_agent_codes_to_salary_names as matcher
from db.connection import get_pool
from scripts.match_agent_codes_to_salary_names import (
    DEFAULT_OUTPUT,
    REPO_ROOT,
    _open_private_csv,
)


class _Connection:
    def __init__(self) -> None:
        self.executemany = AsyncMock()


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


def test_default_output_is_outside_reports_and_under_ignored_outputs() -> None:
    expected = REPO_ROOT / "backend" / "outputs" / "agent_code_name_matches.csv"
    assert DEFAULT_OUTPUT == expected
    assert "reports" not in DEFAULT_OUTPUT.relative_to(REPO_ROOT).parts
    assert DEFAULT_OUTPUT.relative_to(REPO_ROOT).parts[:2] == ("backend", "outputs")


def test_private_csv_writer_enforces_owner_only_permissions(tmp_path: Path) -> None:
    output = tmp_path / "report.csv"
    with _open_private_csv(output) as handle:
        handle.write("header\n")
    assert output.read_text(encoding="utf-8") == "header\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.anyio
async def test_apply_db_persists_person_id_and_clears_it_for_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    monkeypatch.setattr(matcher, "init_db_pool", AsyncMock(return_value=_Pool(connection)))
    monkeypatch.setattr(matcher, "close_db_pool", AsyncMock())
    base = {
        "confidence": "high",
        "match_source": "auto",
        "note": "synthetic",
    }

    await matcher._upsert_agent_salary_links(
        [
            {
                **base,
                "status": "matched",
                "agent_code": "AGENT1",
                "site_code": "SITE1",
                "matched_name": "Agent Test",
                "person_id": "sp1_" + "a" * 64,
            },
            {
                **base,
                "status": "unknown",
                "agent_code": "AGENT2",
                "site_code": "SITE2",
                "matched_name": "",
                "person_id": "sp1_" + "b" * 64,
            },
        ],
        effective_from_month="2026-08",
    )

    assert connection.executemany.await_args is not None
    sql, payload = connection.executemany.await_args.args
    assert "note, person_id" in sql
    assert "person_id = EXCLUDED.person_id" in sql
    assert "agent_salary_links.match_source <> 'manual'" in sql
    assert payload[0][-3] == "2026-08"
    assert payload[0][-1] == "sp1_" + "a" * 64
    assert payload[1][-1] is None


@pytest.mark.anyio
async def test_apply_db_rejects_confirmed_link_without_person_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _Connection()
    monkeypatch.setattr(matcher, "init_db_pool", AsyncMock(return_value=_Pool(connection)))
    monkeypatch.setattr(matcher, "close_db_pool", AsyncMock())

    with pytest.raises(ValueError, match="missing person_id"):
        await matcher._upsert_agent_salary_links(
            [{
                "status": "matched",
                "agent_code": "AGENT1",
                "site_code": "SITE1",
                "matched_name": "Agent Test",
                "person_id": None,
                "confidence": "high",
                "match_source": "auto",
                "note": "synthetic",
            }]
        )

    connection.executemany.assert_not_awaited()


@pytest.mark.anyio
async def test_apply_db_rejects_invalid_effective_month() -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        await matcher._upsert_agent_salary_links(
            [],
            effective_from_month="2026-13",
        )


@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)
@pytest.mark.anyio
async def test_apply_db_round_trips_person_id_in_isolated_database() -> None:
    site_code = "H01MATCH"
    person_id = "sp1_" + "c" * 64

    async def cleanup() -> None:
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                "DELETE FROM agent_salary_links WHERE site_code = $1",
                site_code,
            )
            await connection.execute("DELETE FROM stores WHERE site_code = $1", site_code)
            await connection.execute(
                "DELETE FROM salary_private.people WHERE person_id = $1",
                person_id,
            )

    await cleanup()
    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    first_seen_month, last_seen_month
                ) VALUES ($1, 'Matcher Test', 'Test', 'Test', 'Test', '2099-01', '2099-01')
                """,
                site_code,
            )
            await connection.execute(
                """
                INSERT INTO salary_private.people (
                    person_id, cnp, normalized_name, identity_source
                ) VALUES ($1, NULL, 'agent test', 'name')
                """,
                person_id,
            )

        await matcher._upsert_agent_salary_links(
            [{
                "status": "matched",
                "agent_code": "AGENT1",
                "site_code": site_code,
                "matched_name": "Agent Test",
                "person_id": person_id,
                "confidence": "high",
                "match_source": "auto",
                "note": "synthetic",
            }]
        )

        pool = await get_pool()
        async with pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT person_id, match_status, salary_cnp
                FROM agent_salary_links
                WHERE agent_code = 'AGENT1' AND site_code = $1
                """,
                site_code,
            )
        assert row is not None
        assert row["person_id"] == person_id
        assert row["match_status"] == "confirmed"
        assert row["salary_cnp"] is None
    finally:
        await cleanup()
