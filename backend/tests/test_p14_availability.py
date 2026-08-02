from __future__ import annotations

import asyncio
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
from config import ConfigError, load_runtime_config


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
