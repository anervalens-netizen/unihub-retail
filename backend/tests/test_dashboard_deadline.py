from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from repositories.dashboard import DashboardRepository
from routers.dashboard import get_summary
from schemas.dashboard import DashboardAllQuery, DashboardSummary
from services.request_deadline import RequestDeadline, RequestDeadlineExceeded


class _Connection:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    async def fetch(self, *_args: object, timeout: float) -> list[object]:
        self.timeouts.append(timeout)
        return []

    async def fetchrow(self, *_args: object, timeout: float) -> None:
        self.timeouts.append(timeout)
        return None

    async def fetchval(self, *_args: object, timeout: float) -> None:
        self.timeouts.append(timeout)
        return None

    async def execute(self, *_args: object, timeout: float) -> str:
        self.timeouts.append(timeout)
        return "SELECT 1"


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _Pool:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_deadline_pool_passes_a_positive_remaining_budget_to_each_db_operation() -> None:
    raw_connection = _Connection()
    deadline = RequestDeadline(5)

    async with deadline.bind_pool(_Pool(raw_connection)).acquire() as connection:
        await connection.fetch("SELECT 1")
        await connection.fetchrow("SELECT 1")
        await connection.fetchval("SELECT 1")
        await connection.execute("SELECT 1")

    assert len(raw_connection.timeouts) == 4
    assert all(0 < timeout <= 5 for timeout in raw_connection.timeouts)


@pytest.mark.asyncio
async def test_deadline_stops_before_a_new_database_operation_after_expiry() -> None:
    raw_connection = _Connection()
    deadline = RequestDeadline(1)
    deadline._expires_at = 0  # deliberate expired request before connection acquisition

    with pytest.raises(RequestDeadlineExceeded):
        async with deadline.bind_pool(_Pool(raw_connection)).acquire() as connection:
            await connection.fetch("SELECT 1")

    assert raw_connection.timeouts == []


@pytest.mark.asyncio
async def test_request_timeout_cancels_before_follow_up_work() -> None:
    reached_follow_up = False
    never = asyncio.Event()

    async def operation() -> None:
        nonlocal reached_follow_up
        await never.wait()
        reached_follow_up = True

    with pytest.raises(RequestDeadlineExceeded):
        await RequestDeadline(0.01).run(operation())

    assert reached_follow_up is False


@pytest.mark.asyncio
async def test_repository_uses_deadline_bound_pool_for_dashboard_query() -> None:
    raw_connection = _Connection()
    repository = DashboardRepository(_Pool(raw_connection))
    deadline = RequestDeadline(5)

    rows = await repository.fetch_daily_sales(
        ["true"],
        [],
        pool=deadline.bind_pool(_Pool(raw_connection)),
    )

    assert rows == []
    assert len(raw_connection.timeouts) == 1
    assert raw_connection.timeouts[0] > 0


@pytest.mark.asyncio
async def test_dashboard_boundary_canonicalizes_site_codes_before_service_call() -> None:
    service = MagicMock()
    service.get_summary = AsyncMock(return_value=MagicMock(spec=DashboardSummary))

    await get_summary(
        month="2026-05",
        site_code=" def, ABC,def ",
        svc=service,
    )

    call = service.get_summary.await_args
    assert call.args[4] == "ABC,DEF"
    assert isinstance(call.kwargs["deadline"], RequestDeadline)


@pytest.mark.asyncio
async def test_dashboard_boundary_maps_typed_deadline_expiry_to_504() -> None:
    service = MagicMock()
    service.get_summary = AsyncMock(side_effect=RequestDeadlineExceeded())

    with pytest.raises(HTTPException) as exc:
        await get_summary(month="2026-05", svc=service)

    assert exc.value.status_code == 504


def test_dashboard_batch_boundary_canonicalizes_store_selection_once() -> None:
    query = DashboardAllQuery(month="2026-05", site_code=" z9, A1,z9 ")

    assert query.site_code == "A1,Z9"
