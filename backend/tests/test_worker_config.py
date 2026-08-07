from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import db.connection
import services.importer
import services.jobs
import services.export_operations
import services.erp_reconciliation
import services.imports
import repositories.grile
import worker


def test_worker_uses_bounded_serial_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["max_jobs"] == 1
    assert settings["job_timeout"] == 1800
    assert settings["job_completion_wait"] == 2400
    assert settings["health_check_interval"] == 30
    assert "queue_name" not in settings
    assert worker.import_sales_background not in settings["functions"]
    assert worker.promote_sales_background not in settings["functions"]
    monthly = next(
        entry
        for entry in settings["functions"]
        if getattr(entry, "coroutine", None) is worker.grile_monthly_background
    )
    assert (monthly.timeout_s, monthly.max_tries) == (1800, 1)
    complex_export = next(
        entry
        for entry in settings["functions"]
        if getattr(entry, "coroutine", None) is worker.build_complex_export_background
    )
    assert complex_export.max_tries == 1
    worker_instance.run.assert_called_once_with()


def test_import_worker_uses_dedicated_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "imports")

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["queue_name"] == services.jobs.SALES_IMPORT_QUEUE_NAME
    assert settings["functions"] == [
        worker.import_sales_background,
        worker.import_promo_actuals_background,
        worker.reconcile_erp_background,
        worker.promote_sales_background,
        worker.publish_campaign_reporting_background,
    ]
    assert settings["max_jobs"] == 1
    assert settings["job_timeout"] == 1800
    assert settings["job_completion_wait"] == 1800
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
    cleanup = MagicMock(return_value=0)
    monkeypatch.setattr(worker, "cleanup_stale_sales_import_spool_files", cleanup)
    ctx: dict = {}

    await worker.startup(ctx)

    init_db_pool.assert_awaited_once_with()
    get_pool.assert_awaited_once_with()
    reconcile.assert_awaited_once_with(pool)
    cleanup.assert_called_once_with()
    assert ctx["db_pool"] is pool


@pytest.mark.asyncio
async def test_failed_promo_worker_keeps_spool_and_exact_retry_removes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verify = MagicMock(return_value=12)
    read = MagicMock(return_value=b"promo source")
    remove = MagicMock()
    process = AsyncMock(side_effect=RuntimeError("parse failed"))
    monkeypatch.setattr(worker, "verify_sales_import_artifact", verify)
    monkeypatch.setattr(worker, "read_sales_import_spool_file", read)
    monkeypatch.setattr(worker, "remove_sales_import_spool_file", remove)
    monkeypatch.setattr(services.imports.ImportsService, "process_promo_actuals", process)
    args = (
        {"db_pool": MagicMock()},
        "/private/spool/source.upload",
        "a" * 64,
        12,
        "promo.xlsx",
        "2026-08",
        "2026-08-05",
    )

    with pytest.raises(RuntimeError, match="parse failed"):
        await worker.import_promo_actuals_background(*args)
    remove.assert_not_called()

    process.side_effect = None
    process.return_value = SimpleNamespace(
        model_dump=MagicMock(return_value={"generation_id": "generation-1"})
    )
    result = await worker.import_promo_actuals_background(*args)

    assert result == {"generation_id": "generation-1"}
    assert read.call_args_list[0] == read.call_args_list[1]
    remove.assert_called_once_with("/private/spool/source.upload")


@pytest.mark.asyncio
async def test_failed_erp_worker_keeps_spool_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remove = MagicMock()
    monkeypatch.setattr(worker, "verify_sales_import_artifact", MagicMock(return_value=10))
    monkeypatch.setattr(worker, "read_sales_import_spool_file", MagicMock(return_value=b"erp source"))
    monkeypatch.setattr(worker, "remove_sales_import_spool_file", remove)
    monkeypatch.setattr(
        services.erp_reconciliation.ErpReconciliationService,
        "process",
        AsyncMock(side_effect=RuntimeError("reconciliation failed")),
    )

    with pytest.raises(RuntimeError, match="reconciliation failed"):
        await worker.reconcile_erp_background(
            {"db_pool": MagicMock()},
            "/private/spool/erp.upload",
            "b" * 64,
            10,
            "erp.xlsx",
            "2026-08",
        )

    remove.assert_not_called()


@pytest.mark.asyncio
async def test_operations_worker_does_not_reconcile_imports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = MagicMock()
    reconcile = AsyncMock()
    monkeypatch.setattr(db.connection, "init_db_pool", AsyncMock())
    monkeypatch.setattr(db.connection, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(services.importer, "reconcile_interrupted_imports", reconcile)
    monthly_reconcile = AsyncMock()
    monkeypatch.setattr("services.grile_monthly.reconcile_monthly_operations", monthly_reconcile)
    visits_refresh = AsyncMock(return_value=4)
    monkeypatch.setattr(worker, "_refresh_visits_snapshot_once", visits_refresh)
    export_cleanup = AsyncMock()
    monkeypatch.setattr(services.export_operations, "cleanup_export_operations", export_cleanup)
    orphan_sweep = AsyncMock()
    monkeypatch.setattr(services.export_operations, "sweep_orphan_export_artifacts", orphan_sweep)
    run_reconcile = AsyncMock(return_value=[192])
    refresh_reconcile = AsyncMock(return_value=[193])
    restart_reconcile = AsyncMock(return_value=[191])
    monkeypatch.setattr(
        repositories.grile,
        "GrileRepository",
        lambda received_pool: SimpleNamespace(
            reconcile_stale_runs=run_reconcile,
            reconcile_store_refreshes=refresh_reconcile,
            reconcile_interrupted_running_runs=restart_reconcile,
        )
        if received_pool is pool
        else None,
    )
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "operations")

    ctx: dict = {}
    await worker.startup(ctx)

    reconcile.assert_not_awaited()
    monthly_reconcile.assert_awaited_once_with(pool, ctx["grile_monthly_google"])
    visits_refresh.assert_awaited_once_with(pool)
    export_cleanup.assert_awaited_once()
    orphan_sweep.assert_awaited_once()
    run_reconcile.assert_awaited_once_with()
    refresh_reconcile.assert_awaited_once_with()
    restart_reconcile.assert_awaited_once_with()
    assert ctx["db_pool"] is pool
    ctx["grile_monthly_reconcile_task"].cancel()
    ctx["visits_snapshot_refresh_task"].cancel()
    ctx["export_cleanup_task"].cancel()
    ctx["grile_run_reconcile_task"].cancel()
    await asyncio.gather(ctx["grile_monthly_reconcile_task"], return_exceptions=True)
    await asyncio.gather(ctx["visits_snapshot_refresh_task"], return_exceptions=True)
    await asyncio.gather(ctx["export_cleanup_task"], return_exceptions=True)
    await asyncio.gather(ctx["grile_run_reconcile_task"], return_exceptions=True)
    await ctx["grile_monthly_google"].close()


@pytest.mark.asyncio
async def test_export_cleanup_loop_isolates_db_cleanup_and_still_sweeps_orphans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    cleanup = AsyncMock(side_effect=RuntimeError("db cleanup failed"))

    async def sweep(_repo: object) -> None:
        stop.set()

    orphan_sweep = AsyncMock(side_effect=sweep)
    monkeypatch.setattr(services.export_operations, "cleanup_export_operations", cleanup)
    monkeypatch.setattr(services.export_operations, "sweep_orphan_export_artifacts", orphan_sweep)
    monkeypatch.setattr(worker, "EXPORT_CLEANUP_SECONDS", 0.001)

    await worker._export_cleanup_loop(
        {"export_cleanup_stop": stop, "db_pool": MagicMock()}
    )

    cleanup.assert_awaited_once()
    orphan_sweep.assert_awaited_once()


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


def test_worker_operations_consumes_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)
    monkeypatch.setenv("ARQ_MAX_JOBS", "2")
    monkeypatch.setenv("ARQ_JOB_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("ARQ_JOB_COMPLETION_WAIT_SECONDS", "1200")
    monkeypatch.setenv("ARQ_KEEP_RESULT_SECONDS", "1200")

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["max_jobs"] == 2
    assert settings["job_timeout"] == 900
    assert settings["job_completion_wait"] == 1200
    assert settings["keep_result"] == 1200
    monthly = next(
        entry
        for entry in settings["functions"]
        if getattr(entry, "coroutine", None) is worker.grile_monthly_background
    )
    assert monthly.timeout_s == 900


def test_worker_import_consumes_runtime_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "imports")
    monkeypatch.setenv("ARQ_MAX_JOBS", "2")
    monkeypatch.setenv("ARQ_JOB_TIMEOUT_SECONDS", "900")
    monkeypatch.setenv("ARQ_JOB_COMPLETION_WAIT_SECONDS", "1200")
    monkeypatch.setenv("ARQ_KEEP_RESULT_SECONDS", "1200")

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["queue_name"] == services.jobs.SALES_IMPORT_QUEUE_NAME
    assert settings["max_jobs"] == 2
    assert settings["job_timeout"] == 900
    assert settings["job_completion_wait"] == 1200
    assert settings["keep_result"] == 1200
