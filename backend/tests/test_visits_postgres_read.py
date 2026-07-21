from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import repositories.visits_report_postgres as postgres_repository_module
import services.visits_report as visits_service_module
from repositories.visits_report_postgres import VisitsReportPostgresRepository
from services.visits_report import VisitsReportService
from services.visits_shadow import compare_visit_result


class _Acquire:
    def __init__(self, connection: AsyncMock) -> None:
        self.connection = connection

    async def __aenter__(self) -> AsyncMock:
        return self.connection

    async def __aexit__(self, *args) -> None:
        return None


def _sqlite_repo(tmp_path: Path) -> MagicMock:
    repo = MagicMock()
    repo.images_dir = tmp_path
    repo.db_exists.return_value = True
    return repo


@pytest.mark.asyncio
async def test_sqlite_primary_is_returned_while_postgres_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = {"total": 1, "magazine_unice": 1, "avg_completion": 50.0, "rows": []}
    sqlite_repo = _sqlite_repo(tmp_path)
    sqlite_repo.query_sqlite.return_value = result
    postgres_repo = MagicMock()
    postgres_repo.query_report = AsyncMock(return_value=result)
    service = VisitsReportService(sqlite_repo, postgres_repo)
    monkeypatch.setattr(
        service,
        "_resolve_store_scope",
        AsyncMock(return_value=({}, None)),
    )
    monkeypatch.setattr(visits_service_module, "get_visits_read_source", lambda: "sqlite")
    monkeypatch.setattr(
        visits_service_module,
        "visits_shadow_compare_enabled",
        lambda: True,
    )

    response = await service.get_visits_report("2026-07", None, None, None, None)

    assert response.total_vizite == 1
    sqlite_repo.query_sqlite.assert_called_once()
    postgres_repo.query_report.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_primary_does_not_require_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_repo = _sqlite_repo(tmp_path)
    sqlite_repo.db_exists.return_value = False
    postgres_repo = MagicMock()
    postgres_repo.query_tree = AsyncMock(return_value=[])
    service = VisitsReportService(sqlite_repo, postgres_repo)
    monkeypatch.setattr(
        service,
        "_resolve_store_scope",
        AsyncMock(return_value=({}, None)),
    )
    monkeypatch.setattr(visits_service_module, "get_visits_read_source", lambda: "postgres")
    monkeypatch.setattr(
        visits_service_module,
        "visits_shadow_compare_enabled",
        lambda: False,
    )

    response = await service.get_visits_tree(None, None, None, None)

    assert response.team_leaders == []
    sqlite_repo.query_tree.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_failure_never_breaks_sqlite_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sqlite_repo = _sqlite_repo(tmp_path)
    sqlite_repo.query_tree.return_value = []
    postgres_repo = MagicMock()
    postgres_repo.query_tree = AsyncMock(side_effect=RuntimeError("pg unavailable"))
    service = VisitsReportService(sqlite_repo, postgres_repo)
    monkeypatch.setattr(
        service,
        "_resolve_store_scope",
        AsyncMock(return_value=({}, None)),
    )
    monkeypatch.setattr(visits_service_module, "get_visits_read_source", lambda: "sqlite")
    monkeypatch.setattr(
        visits_service_module,
        "visits_shadow_compare_enabled",
        lambda: True,
    )

    response = await service.get_visits_tree(None, None, None, None)

    assert response.team_leaders == []


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


def test_shadow_mismatch_log_does_not_contain_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="services.visits_shadow"):
        matched = compare_visit_result(
            "detail",
            {"id": "sensitive-id", "firma": "Sensitive Company"},
            {"id": "sensitive-id", "firma": "Different"},
        )

    assert matched is False
    assert "operation=detail" in caplog.text
    assert "sensitive-id" not in caplog.text
    assert "Sensitive Company" not in caplog.text
