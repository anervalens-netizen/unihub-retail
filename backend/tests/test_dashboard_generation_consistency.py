from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from routers.dashboard import _run_dashboard
from services.dashboard import orchestration
from services.dashboard.errors import DashboardGenerationUnstable
from services.request_deadline import RequestDeadline


class _EpochConnection:
    def __init__(self, values: list[int]) -> None:
        self._values = iter(values)
        self.queries: list[str] = []

    async def fetchval(self, query: str) -> int:
        self.queries.append(query.strip())
        return next(self._values)


class _Acquire:
    def __init__(self, connection: _EpochConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _EpochConnection:
        return self.connection

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _Pool:
    def __init__(self, connection: _EpochConnection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


class _Service:
    dashboard_global_component_concurrency = 1

    def __init__(self, epochs: list[int]) -> None:
        self.connection = _EpochConnection(epochs)
        self.pool = _Pool(self.connection)

    def _pool_for(self, _deadline: RequestDeadline | None) -> _Pool:
        return self.pool


async def _load(service: _Service) -> object:
    return await orchestration.load_dashboard_all(
        service,  # type: ignore[arg-type]
        "2026-05",
        None,
        None,
        None,
        None,
        None,
    )


@pytest.mark.asyncio
async def test_dashboard_generation_guard_returns_first_stable_attempt() -> None:
    service = _Service([4, 4])
    response = object()
    run = AsyncMock(return_value=response)

    with patch.object(orchestration.DashboardAllLoader, "run", run):
        result = await _load(service)

    assert result is response
    assert run.await_count == 1
    assert service.connection.queries == [
        "SELECT public.current_sales_generation_epoch()",
        "SELECT public.current_sales_generation_epoch()",
    ]


@pytest.mark.asyncio
async def test_dashboard_generation_guard_retries_once_after_drift() -> None:
    service = _Service([4, 5, 5, 5])
    first = object()
    second = object()
    run = AsyncMock(side_effect=[first, second])

    with patch.object(orchestration.DashboardAllLoader, "run", run):
        result = await _load(service)

    assert result is second
    assert run.await_count == 2


@pytest.mark.asyncio
async def test_dashboard_generation_guard_fails_closed_after_second_drift() -> None:
    service = _Service([4, 5, 5, 6])
    run = AsyncMock(side_effect=[object(), object()])

    with patch.object(orchestration.DashboardAllLoader, "run", run):
        with pytest.raises(DashboardGenerationUnstable):
            await _load(service)

    assert run.await_count == 2


@pytest.mark.asyncio
async def test_dashboard_boundary_maps_unstable_generation_to_503() -> None:
    async def unstable(_deadline: RequestDeadline) -> None:
        raise DashboardGenerationUnstable()

    with pytest.raises(HTTPException) as exc:
        await _run_dashboard(RequestDeadline(5), unstable)

    assert exc.value.status_code == 503


def test_dashboard_generation_epoch_migration_keeps_ledger_private() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "db"
        / "migrations"
        / "076_v3_dashboard_generation_epoch.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.split()).lower()

    assert "security definer" in normalized
    assert "set search_path = pg_catalog, public" in normalized
    assert "select count(*)::bigint from public.sales_generation_promotions" in normalized
    assert "revoke all on function public.current_sales_generation_epoch() from public" in normalized
    assert "grant execute on function public.current_sales_generation_epoch() to unihub_web_read" in normalized
    assert "grant select" not in normalized
