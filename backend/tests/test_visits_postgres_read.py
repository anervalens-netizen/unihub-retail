from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

import repositories.visits_report_postgres as postgres_repository_module
import services.visits_report as visits_service_module
from repositories.visits_report_postgres import VisitsReportPostgresRepository
from services.visits_report import VisitsReportService


class _Acquire:
    def __init__(self, connection: AsyncMock) -> None:
        self.connection = connection

    async def __aenter__(self) -> AsyncMock:
        return self.connection

    async def __aexit__(self, *args) -> None:
        return None


@pytest.mark.asyncio
async def test_service_reads_only_fieldops_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    result = {"total": 1, "magazine_unice": 1, "avg_completion": 50.0, "rows": []}
    postgres_repo = MagicMock()
    postgres_repo.query_report = AsyncMock(return_value=result)
    service = VisitsReportService(postgres_repo)
    monkeypatch.setattr(
        service,
        "_resolve_store_scope",
        AsyncMock(return_value=({}, None)),
    )

    response = await service.get_visits_report("2026-07", None, None, None, None)

    assert response.total_vizite == 1
    postgres_repo.query_report.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_primary_does_not_require_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    postgres_repo = MagicMock()
    postgres_repo.query_tree = AsyncMock(return_value=[])
    service = VisitsReportService(postgres_repo)
    monkeypatch.setattr(
        service,
        "_resolve_store_scope",
        AsyncMock(return_value=({}, None)),
    )
    response = await service.get_visits_tree(None, None, None, None)

    assert response.team_leaders == []


@pytest.mark.asyncio
async def test_visit_store_scope_preserves_commas_and_dominates_hierarchy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = AsyncMock()
    connection.fetch.return_value = []
    pool = MagicMock()
    pool.acquire.return_value = _Acquire(connection)
    monkeypatch.setattr(
        visits_service_module,
        "get_pool",
        AsyncMock(return_value=pool),
    )
    service = VisitsReportService(MagicMock())

    await service._resolve_store_scope(
        {
            "firma": "Wrong company",
            "rm": "Wrong manager",
            "asm": "Wrong ASM",
            "magazin": ["B, Nord", "C"],
        }
    )

    sql, values = connection.fetch.await_args.args
    assert "firma = ANY" not in sql
    assert "regional = ANY" not in sql
    assert "asm = ANY" not in sql
    assert "site_code = ANY($1::text[])" in sql
    assert values == ["B, Nord", "C"]


@pytest.mark.asyncio
async def test_postgres_repository_applies_month_and_store_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = AsyncMock()
    connection.fetch.return_value = [
        {
            "magazin": "S1",
            "asm": "A1",
            "regional": "R1",
            "firma": "F1",
            "completion_pct": 50,
            "curatenie": True,
            "imagine": False,
            "uniforma": False,
            "afise": False,
            "produse_promo": False,
            "data_raport": None,
        }
    ]
    pool = MagicMock()
    pool.acquire.return_value = _Acquire(connection)
    monkeypatch.setattr(
        postgres_repository_module,
        "get_pool",
        AsyncMock(return_value=pool),
    )
    repository = VisitsReportPostgresRepository()

    result = await repository.query_report(
        "2026-07",
        store_metadata={},
        site_codes=["S1", "S2"],
    )

    assert result["total"] == 1
    sql, month_start, month_end, codes = connection.fetch.await_args.args
    assert "FROM fieldops_visits" in sql
    assert "to_char" not in sql
    assert "data_raport >= $1" in sql
    assert "magazin = ANY($3::text[])" in sql
    assert month_start == date(2026, 7, 1)
    assert month_end == date(2026, 8, 1)
    assert codes == ["S1", "S2"]
