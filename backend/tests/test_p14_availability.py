from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from arq.jobs import JobStatus as ArqJobStatus
from fastapi import HTTPException

import main
import services.jobs as jobs
from business_clock import (
    BUSINESS_TIMEZONE,
    BUSINESS_TIMEZONE_NAME,
    SystemBusinessClock,
    business_now,
)
from config import ConfigError, grile_provider_stale_after_seconds, load_runtime_config


def test_runtime_config_is_typed_for_web_worker_and_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RETAIL_WORKER_ROLE", raising=False)

    web = load_runtime_config("web")
    worker = load_runtime_config("worker")
    importer = load_runtime_config("import")

    assert (web.role, worker.role, importer.role) == ("web", "worker", "import")
    assert importer.worker_role == "imports"
    assert web.db_pool_min_size <= web.db_pool_max_size
    assert web.arq_completion_wait_seconds >= web.arq_job_timeout_seconds


def test_business_clock_rejects_naive_datetime() -> None:
    class NaiveClock:
        def now(self) -> datetime:
            return datetime(2026, 10, 25, 3, 30)

    with pytest.raises(ValueError, match="timezone-aware"):
        business_now(NaiveClock())

@pytest.mark.parametrize(
    ("utc_value", "expected_local"),
    [
        (datetime(2025, 12, 31, 22, 0, tzinfo=timezone.utc), (2026, 1, 1, 0)),
        (datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc), (2026, 3, 29, 2)),
        (datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc), (2026, 3, 29, 4)),
        (datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc), (2026, 10, 25, 3)),
        (datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc), (2026, 10, 25, 3)),
    ],
)
def test_business_clock_handles_midnight_year_and_dst(
    utc_value: datetime,
    expected_local: tuple[int, int, int, int],
) -> None:
    class FixedClock:
        def now(self) -> datetime:
            return utc_value.astimezone(BUSINESS_TIMEZONE)

    local = business_now(FixedClock())
    assert (local.year, local.month, local.day, local.hour) == expected_local
    if utc_value.month == 10:
        assert local.fold == (0 if utc_value.hour == 0 else 1)


@pytest.mark.asyncio
async def test_grile_terminal_db_status_wins_when_arq_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.grile as grile_router

    terminal = {
        "id": 77,
        "status": "completed",
        "result": {"manifest": "sha"},
        "error_message": None,
    }
    get_operation = AsyncMock(return_value=terminal)
    get_status = AsyncMock(side_effect=AssertionError("ARQ must not be read"))
    monkeypatch.setattr(
        grile_router,
        "get_grile_monthly_operation_by_job_id",
        get_operation,
    )
    monkeypatch.setattr(grile_router, "get_job_status", get_status)

    result = await grile_router.grile_monthly_job(
        "grile-monthly:77",
        claims=MagicMock(),
    )

    assert result == {
        "job_id": "grile-monthly:77",
        "status": "complete",
        "result": {"manifest": "sha"},
        "error": None,
    }
    get_operation.assert_awaited_once_with("grile-monthly:77")
    get_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_grile_unknown_status_exposes_operation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.grile as grile_router

    monkeypatch.setattr(
        grile_router,
        "get_grile_monthly_operation_by_job_id",
        AsyncMock(
            return_value={
                "id": 78,
                "status": "running",
                "result": None,
                "error_message": None,
            }
        ),
    )
    monkeypatch.setattr(
        grile_router,
        "get_job_status",
        AsyncMock(
            return_value=jobs.JobResult(
                job_id="grile-monthly:78",
                status=jobs.JobStatus.UNKNOWN,
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await grile_router.grile_monthly_job(
            "grile-monthly:78",
            claims=MagicMock(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == {
        "status": "unknown",
        "operation_id": 78,
        "job_id": "grile-monthly:78",
    }


def test_runtime_config_rejects_equal_lock_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "120000")
    monkeypatch.setenv("DB_LOCK_TIMEOUT_MS", "120000")

    with pytest.raises(ConfigError, match="DB_LOCK_TIMEOUT_MS"):
        load_runtime_config("web")


def test_runtime_config_requires_two_web_pool_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "1")

    with pytest.raises(ConfigError, match="DB_POOL_MAX_SIZE"):
        load_runtime_config("web")


def test_runtime_config_enforces_transport_budget_and_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARQ_CONN_RETRIES", "2")
    with pytest.raises(ConfigError, match="bugetul de 3 secunde"):
        load_runtime_config("worker")

    monkeypatch.setenv("ARQ_CONN_RETRIES", "1")
    monkeypatch.setenv("ARQ_KEEP_RESULT_SECONDS", "2399")
    with pytest.raises(ConfigError, match="cel mai lung job ARQ"):
        load_runtime_config("worker")


def test_web_ignores_worker_only_arq_values_but_workers_reject_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RETAIL_WORKER_ROLE", raising=False)
    monkeypatch.setenv("ARQ_JOB_TIMEOUT_SECONDS", "invalid")
    monkeypatch.setenv("ARQ_JOB_COMPLETION_WAIT_SECONDS", "invalid")
    monkeypatch.setenv("ARQ_MAX_JOBS", "invalid")
    monkeypatch.setenv("ARQ_KEEP_RESULT_SECONDS", "invalid")

    web = load_runtime_config("web")
    assert web.role == "web"

    with pytest.raises(ConfigError, match="ARQ_JOB_TIMEOUT_SECONDS"):
        load_runtime_config("worker")
    with pytest.raises(ConfigError, match="ARQ_JOB_TIMEOUT_SECONDS"):
        load_runtime_config("import")


@pytest.mark.asyncio
async def test_lifespan_allows_arq_port_down_and_logs_degraded(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Acquire:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    monkeypatch.setattr(main, "validate_required_env_vars", lambda _role: None)
    monkeypatch.setattr(main, "init_oidc_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_session_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_rate_limit_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_db_pool", AsyncMock())
    monkeypatch.setattr(main, "get_pool", AsyncMock(return_value=Pool()))
    monkeypatch.setattr(main, "attach_db_error_handler", lambda _pool: None)
    monkeypatch.setattr(main, "verify_migrations_current", AsyncMock())
    monkeypatch.setattr(main, "prewarm_pool", AsyncMock())
    monkeypatch.setattr(main, "detach_db_error_handler", AsyncMock())
    monkeypatch.setattr(main, "close_db_pool", AsyncMock())
    monkeypatch.setattr(main, "close_rate_limit_runtime", AsyncMock())
    monkeypatch.setattr(main, "close_session_runtime", AsyncMock())
    monkeypatch.setattr(main, "close_oidc_runtime", AsyncMock())
    monkeypatch.setattr(jobs, "_arq_pool", None)
    monkeypatch.setattr(jobs, "_arq_pool_attempt", None)
    monkeypatch.setattr(jobs, "_arq_last_failure_monotonic", 0.0)
    create_pool = AsyncMock(side_effect=ConnectionError("ARQ port closed"))
    monkeypatch.setattr(jobs, "create_pool", create_pool)

    with caplog.at_level(logging.WARNING, logger="main"):
        async with main.lifespan(main.app):
            pass

    create_pool.assert_awaited_once()
    assert "arq worker pool unavailable; queue endpoints degraded" in caplog.text
    assert "arq worker pool initialized" not in caplog.text
    assert not hasattr(main, "sync_visits_snapshot")
    assert not hasattr(main, "prewarm_special_cards_cache")
    assert not hasattr(main, "update_business_metrics")


@pytest.mark.asyncio
async def test_readyz_stays_available_without_initializing_arq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routers.health as health_router
    import services.health as health_service

    class Connection:
        async def fetchval(self, _query: str) -> int:
            return 1

    class Acquire:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    get_pool = AsyncMock(return_value=Pool())
    session_ready = AsyncMock()
    arq_lookup = AsyncMock(side_effect=AssertionError("readyz must not initialize ARQ"))
    monkeypatch.setattr(health_service, "get_pool", get_pool)
    monkeypatch.setattr(health_service, "verify_session_runtime_ready", session_ready)
    monkeypatch.setattr(jobs, "get_arq_pool", arq_lookup)

    response = await health_router.readiness()

    assert response.status_code == 200
    assert response.body == b'{"status":"ok"}'
    get_pool.assert_awaited_once_with()
    session_ready.assert_awaited_once_with()
    arq_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_arq_pool_is_single_flight_for_concurrent_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = MagicMock()
    queue.close = AsyncMock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def create_pool(_settings: object) -> MagicMock:
        started.set()
        await release.wait()
        return queue

    monkeypatch.setattr(jobs, "_arq_pool", None)
    monkeypatch.setattr(jobs, "_arq_pool_attempt", None)
    monkeypatch.setattr(jobs, "_arq_last_failure_monotonic", 0.0)
    monkeypatch.setattr(jobs, "get_valkey_settings", lambda: object())
    create = AsyncMock(side_effect=create_pool)
    monkeypatch.setattr(jobs, "create_pool", create)

    try:
        callers = [asyncio.create_task(jobs.get_arq_pool()) for _ in range(8)]
        await asyncio.wait_for(started.wait(), timeout=1.0)
        release.set()
        results = await asyncio.gather(*callers)

        assert create.await_count == 1
        assert results == [queue] * 8
    finally:
        await jobs.close_arq_pool()


@pytest.mark.asyncio
async def test_get_arq_pool_recovers_after_cooldown_without_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = MagicMock()
    queue.close = AsyncMock()
    create = AsyncMock(side_effect=[ConnectionError("ARQ port closed"), queue])
    monkeypatch.setattr(jobs, "_arq_pool", None)
    monkeypatch.setattr(jobs, "_arq_pool_attempt", None)
    monkeypatch.setattr(jobs, "_arq_last_failure_monotonic", 0.0)
    monkeypatch.setattr(jobs, "get_valkey_settings", lambda: object())
    monkeypatch.setattr(jobs, "create_pool", create)

    try:
        assert await jobs.get_arq_pool() is None
        assert await jobs.get_arq_pool() is None
        assert create.await_count == 1

        jobs._arq_last_failure_monotonic = time.monotonic() - 10
        assert await jobs.get_arq_pool() is queue
        assert create.await_count == 2
    finally:
        await jobs.close_arq_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_queue_down_fails_monthly_reservation_without_hanging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from db.connection import get_pool

    pool = await get_pool()
    month = "2199-11"
    monkeypatch.setattr(jobs, "get_arq_pool", AsyncMock(return_value=None))

    try:
        with pytest.raises(jobs.JobQueueUnavailableError) as exc_info:
            await asyncio.wait_for(
                jobs.enqueue_grile_monthly(
                    op="archive",
                    month=month,
                    dry_run=True,
                    requested_by_sub="queue-down-test",
                ),
                timeout=1.0,
            )

        assert exc_info.value.status_code == 503
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, status, job_id, error_message
                FROM grile_monthly_operations
                WHERE closing_month = $1
                ORDER BY id DESC
                LIMIT 1
                """,
                month,
            )
        assert row is not None
        assert row["status"] == "failed"
        operation_id = int(row["id"])
        assert row["job_id"] == f"grile-monthly:{operation_id}"
        assert row["error_message"] == jobs.MONTHLY_QUEUE_PUBLISH_FAILED
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_monthly_operations WHERE closing_month = $1",
                month,
            )


def test_grile_provider_stale_threshold_is_typed_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRILE_PROVIDER_STALE_AFTER_SECONDS", "7200")
    assert grile_provider_stale_after_seconds() == 7200

    for invalid in ("299", str(7 * 24 * 60 * 60 + 1), "invalid"):
        monkeypatch.setenv("GRILE_PROVIDER_STALE_AFTER_SECONDS", invalid)
        with pytest.raises(ConfigError, match="GRILE_PROVIDER_STALE_AFTER_SECONDS"):
            load_runtime_config("web")
