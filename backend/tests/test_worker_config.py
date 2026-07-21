from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import db.connection
import services.importer
import services.jobs
import worker


def test_worker_uses_bounded_serial_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["max_jobs"] == 1
    assert settings["job_timeout"] == 1800
    assert settings["job_completion_wait"] == 60
    assert settings["health_check_interval"] == 30
    assert "queue_name" not in settings
    worker_instance.run.assert_called_once_with()


def test_import_worker_uses_dedicated_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "imports")

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["queue_name"] == services.jobs.SALES_IMPORT_QUEUE_NAME
    assert settings["functions"] == [worker.import_sales_background]
    assert settings["max_jobs"] == 1
    worker_instance.run.assert_called_once_with()


@pytest.mark.asyncio
async def test_worker_startup_reconciles_interrupted_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = MagicMock()
    init_db_pool = AsyncMock()
    get_pool = AsyncMock(return_value=pool)
    reconcile = AsyncMock(return_value=[11, 12])
    monkeypatch.setattr(db.connection, "init_db_pool", init_db_pool)
    monkeypatch.setattr(db.connection, "get_pool", get_pool)
    monkeypatch.setattr(
        services.importer,
        "reconcile_interrupted_imports",
        reconcile,
    )
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "imports")
    monkeypatch.setattr(worker, "cleanup_stale_sales_import_spool_files", MagicMock(return_value=0))
    ctx: dict = {}

    await worker.startup(ctx)

    init_db_pool.assert_awaited_once_with()
    get_pool.assert_awaited_once_with()
    reconcile.assert_awaited_once_with(pool)
    assert ctx["db_pool"] is pool


@pytest.mark.asyncio
async def test_operations_worker_does_not_reconcile_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = MagicMock()
    reconcile = AsyncMock()
    monkeypatch.setattr(db.connection, "init_db_pool", AsyncMock())
    monkeypatch.setattr(db.connection, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(services.importer, "reconcile_interrupted_imports", reconcile)
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "operations")

    ctx: dict = {}
    await worker.startup(ctx)

    reconcile.assert_not_awaited()
    assert ctx["db_pool"] is pool


@pytest.mark.asyncio
async def test_worker_shutdown_closes_all_pools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_db_pool = AsyncMock()
    close_arq_pool = AsyncMock()
    monkeypatch.setattr(db.connection, "close_db_pool", close_db_pool)
    monkeypatch.setattr(services.jobs, "close_arq_pool", close_arq_pool)

    await worker.shutdown({})

    close_arq_pool.assert_awaited_once_with()
    close_db_pool.assert_awaited_once_with()
