from __future__ import annotations

import asyncio
import inspect
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from config import ConfigError, load_runtime_config

from repositories.dashboard import DashboardRepository
from routers.dashboard import (
    get_dashboard_all_batch,
    get_dashboard_history_details_batch,
    get_performance_detail,
    get_summary,
)
from schemas.dashboard import (
    DashboardAllBatchRequest,
    DashboardAllQuery,
    DashboardAllResponse,
    DashboardSummary,
)
from services.dashboard_filters import canonical_dashboard_site_codes
from services.dashboard_service import DashboardService, _gather_cancel_on_error
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
async def test_client_cancellation_propagates_without_becoming_a_gateway_timeout() -> None:
    async def cancelled_by_client() -> None:
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await RequestDeadline(1).run(cancelled_by_client())


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
        deadline=RequestDeadline(5),
        svc=service,
    )

    call = service.get_summary.await_args
    assert call.args[4] == "def,ABC"
    assert isinstance(call.kwargs["deadline"], RequestDeadline)


@pytest.mark.asyncio
async def test_performance_detail_store_key_uses_the_same_canonical_boundary() -> None:
    service = MagicMock()
    service.get_performance_detail = AsyncMock(return_value=MagicMock())

    await get_performance_detail(
        month="2026-05",
        level="store",
        key=" S1,S1, S2 ",
        deadline=RequestDeadline(5),
        svc=service,
    )

    assert service.get_performance_detail.await_args.args[2] == "S1,S2"


@pytest.mark.asyncio
async def test_dashboard_boundary_maps_typed_deadline_expiry_to_504() -> None:
    service = MagicMock()
    service.get_summary = AsyncMock(side_effect=RequestDeadlineExceeded())

    with pytest.raises(HTTPException) as exc:
        await get_summary(month="2026-05", deadline=RequestDeadline(5), svc=service)

    assert exc.value.status_code == 504


def test_dashboard_batch_boundary_canonicalizes_store_selection_once() -> None:
    query = DashboardAllQuery(month="2026-05", site_code=" z9, A1,z9 ")

    assert query.site_code == "z9,A1"


@pytest.mark.asyncio
async def test_both_dashboard_batch_routes_receive_the_same_canonical_site_scope() -> None:
    service = MagicMock()
    service.get_dashboard_all_batch = AsyncMock(return_value=MagicMock())
    service.get_dashboard_history_details_batch = AsyncMock(return_value=MagicMock())
    request = DashboardAllBatchRequest(
        queries=[DashboardAllQuery(month="2026-05", site_code=" S1,S1, S2 ")]
    )
    deadline = RequestDeadline(5)

    await get_dashboard_all_batch(request, deadline=deadline, svc=service)
    await get_dashboard_history_details_batch(request, deadline=deadline, svc=service)

    assert service.get_dashboard_all_batch.await_args.args[0][0].site_code == "S1,S2"
    assert service.get_dashboard_history_details_batch.await_args.args[0][0].site_code == "S1,S2"


def test_dashboard_site_scope_keeps_case_order_and_drops_sentinels() -> None:
    assert canonical_dashboard_site_codes(" S1,S1, S2 ") == "S1,S2"
    assert canonical_dashboard_site_codes("s1,S1") == "s1,S1"
    assert canonical_dashboard_site_codes(" Toate, , Toti ") is None


def test_request_deadline_reads_the_validated_web_runtime_value() -> None:
    deadline = RequestDeadline.from_runtime_config(
        SimpleNamespace(dashboard_request_deadline_ms=2500)
    )

    assert 2.4 < deadline.remaining_seconds() <= 2.5


def test_web_runtime_config_validates_dashboard_deadline_and_connection_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RETAIL_WORKER_ROLE", raising=False)
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "4")
    monkeypatch.setenv("DASHBOARD_REQUEST_DEADLINE_MS", "2400")
    monkeypatch.setenv("DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY", "2")

    runtime_config = load_runtime_config("web")

    assert runtime_config.dashboard_request_deadline_ms == 2400
    assert runtime_config.dashboard_global_component_concurrency == 2

    monkeypatch.setenv("DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY", "3")
    with pytest.raises(ConfigError, match="DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY"):
        load_runtime_config("web")

    monkeypatch.setenv("DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY", "2")
    monkeypatch.setenv("DASHBOARD_REQUEST_DEADLINE_MS", "3001")
    with pytest.raises(ConfigError, match="DASHBOARD_REQUEST_DEADLINE_MS"):
        load_runtime_config("web")


@pytest.mark.asyncio
async def test_already_expired_deadline_closes_unstarted_coroutine() -> None:
    started = False

    async def operation() -> None:
        nonlocal started
        started = True

    coroutine = operation()
    deadline = RequestDeadline(1)
    deadline._expires_at = 0

    with pytest.raises(RequestDeadlineExceeded):
        await deadline.run(coroutine)

    assert started is False
    assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED


class _BlockingAcquire:
    def __init__(self) -> None:
        self.cancelled = False
        self.started = asyncio.Event()

    async def __aenter__(self) -> _Connection:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("blocking acquire resumed unexpectedly")

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _BlockingPool:
    def __init__(self, acquire: _BlockingAcquire) -> None:
        self._acquire = acquire

    def acquire(self) -> _BlockingAcquire:
        return self._acquire


@pytest.mark.asyncio
async def test_deadline_bounds_pool_acquire_and_reaps_the_waiter() -> None:
    acquire = _BlockingAcquire()
    deadline = RequestDeadline(0.05)

    with pytest.raises(RequestDeadlineExceeded):
        async with deadline.bind_pool(_BlockingPool(acquire)).acquire():
            pytest.fail("acquire must not succeed")

    assert acquire.cancelled is True


@pytest.mark.asyncio
async def test_child_failure_cancels_and_reaps_every_dashboard_task() -> None:
    cancelled = asyncio.Event()

    async def fail() -> None:
        raise RuntimeError("boom")

    async def wait_forever() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(RuntimeError, match="boom"):
        await _gather_cancel_on_error(fail(), wait_forever(), task_name="dashboard:test")

    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_batch_of_twelve_uses_one_outer_deadline_and_leaves_no_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DashboardService(MagicMock(), MagicMock())
    started = 0
    cancelled = 0

    async def slow_load(*_args: object, **_kwargs: object) -> DashboardAllResponse:
        nonlocal started, cancelled
        started += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled += 1
            raise
        raise AssertionError("slow dashboard loader resumed unexpectedly")

    monkeypatch.setattr(service, "get_dashboard_all", slow_load)
    queries = [DashboardAllQuery(month=f"2026-{month:02d}") for month in range(1, 13)]
    deadline = RequestDeadline(0.05)

    with pytest.raises(RequestDeadlineExceeded):
        await deadline.run(service.get_dashboard_all_batch(queries, deadline=deadline))

    assert 1 <= started <= 2
    assert cancelled == started


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)
async def test_pg_sleep_uses_request_budget_and_connection_stays_usable() -> None:
    from db.connection import get_pool

    pool = await get_pool()
    deadline = RequestDeadline(0.20)
    with pytest.raises(RequestDeadlineExceeded):
        async with deadline.bind_pool(pool).acquire() as conn:
            await conn.fetchval("SELECT pg_sleep(1)")

    async with pool.acquire() as conn:
        assert await conn.fetchval("SELECT 1") == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)
async def test_pool_starvation_uses_request_budget_then_recovers() -> None:
    import asyncpg

    pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=1,
        max_size=1,
    )
    try:
        async with pool.acquire() as held:
            deadline = RequestDeadline(0.20)
            with pytest.raises(RequestDeadlineExceeded):
                async with deadline.bind_pool(pool).acquire():
                    pytest.fail("starved pool acquire must not succeed")
            assert not held.is_closed()

        async with pool.acquire() as conn:
            assert await conn.fetchval("SELECT 1") == 1
    finally:
        await pool.close()
