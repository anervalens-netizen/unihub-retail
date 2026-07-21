from __future__ import annotations

from typing import Any

import pytest

from repositories.exports import ExportsRepository
from db.connection import close_db_pool, get_pool


class _Acquire:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "_Connection":
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    async def fetch(self, sql: str, *params: Any) -> list[Any]:
        self.sql = sql
        self.params = params
        return []


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_agent_scope_does_not_mix_unattributed_historical_store_totals() -> None:
    connection = _Connection()
    repo = ExportsRepository(_Pool(connection))  # type: ignore[arg-type]

    await repo.fetch_report_rows(
        dataset="stores",
        months=["2026-06"],
        filters={"agent": ["Agent 1"]},
        include_closed_stores=False,
        include_campaign_metrics=False,
    )

    assert "historical_monthly_sales hms" not in connection.sql
    assert connection.params[-1] is False
    assert "::BOOLEAN" in connection.sql


@pytest.mark.asyncio
async def test_export_queries_execute_with_campaign_gate_on_postgres() -> None:
    pool = await get_pool()
    repo = ExportsRepository(pool)
    try:
        assert await repo.fetch_report_rows(
            dataset="stores",
            months=["2099-01"],
            filters={},
            include_closed_stores=False,
            include_campaign_metrics=False,
        ) == []
        assert await repo.fetch_report_rows(
            dataset="stores",
            months=["2099-01"],
            filters={},
            include_closed_stores=False,
            include_campaign_metrics=True,
        ) == []
        assert await repo.fetch_daily_evolution_rows(
            months=["2099-01"],
            filters={},
            include_closed_stores=False,
            include_campaign_metrics=False,
        ) == []
        assert await repo.fetch_daily_comparison_rows(
            level="general",
            months=["2099-01"],
            filters={},
            include_closed_stores=False,
            include_campaign_metrics=False,
        ) == []
    finally:
        await close_db_pool()
