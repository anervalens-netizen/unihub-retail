from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

import config
import db.connection
import observability.worker_metrics
import services.importer
import services.jobs
import services.export_operations
import services.erp_reconciliation
import services.campaign_reporting
import services.contest_reporting
import services.grile_reconciliation_supervisor as grile_supervisor
import services.imports
import services.grile_pilot_v2_sync
import services.grile_pilot_v2_runtime
import repositories.grile
import worker


@pytest.mark.asyncio
async def test_worker_metrics_start_before_runtime_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_server = MagicMock()
    start_metrics = MagicMock(return_value=metrics_server)

    async def assert_metrics_started(ctx: dict, *, worker_role: str) -> None:
        assert worker_role == "operations"
        assert ctx["worker_metrics_server"] is metrics_server

    monkeypatch.setenv("RETAIL_WORKER_ROLE", "operations")
    monkeypatch.setattr(
        observability.worker_metrics,
        "start_worker_metrics",
        start_metrics,
    )
    monkeypatch.setattr(worker, "_startup_runtime", assert_metrics_started)
    ctx: dict = {}

    await worker.startup(ctx)

    start_metrics.assert_called_once_with("operations")


@pytest.mark.asyncio
async def test_failed_worker_startup_closes_early_metrics_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics_server = MagicMock()
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "operations")
    monkeypatch.setattr(
        observability.worker_metrics,
        "start_worker_metrics",
        MagicMock(return_value=metrics_server),
    )
    monkeypatch.setattr(
        worker,
        "_startup_runtime",
        AsyncMock(side_effect=RuntimeError("startup reconciliation failed")),
    )
    monkeypatch.setattr(db.connection, "close_db_pool", AsyncMock())
    monkeypatch.setattr(services.jobs, "close_arq_pool", AsyncMock())

    with pytest.raises(RuntimeError, match="startup reconciliation failed"):
        await worker.startup({})

    metrics_server.close.assert_called_once_with()


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
    assert settings["queue_name"] == services.jobs.OPERATIONS_QUEUE_NAME
    assert worker.import_sales_background not in settings["functions"]
    assert worker.promote_sales_background not in settings["functions"]
    assert len(settings["functions"]) == 1
    assert settings["functions"][0].coroutine is worker.refresh_visits_snapshot_background
    assert settings["functions"][0].max_tries == 1
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
    monkeypatch.setattr(
        worker, "verify_sales_import_artifact", MagicMock(return_value=10)
    )
    monkeypatch.setattr(
        worker,
        "read_sales_import_spool_file",
        MagicMock(return_value=b"erp source"),
    )
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
async def test_erp_worker_converts_http_error_to_pickle_safe_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker, "verify_sales_import_artifact", MagicMock(return_value=10))
    monkeypatch.setattr(worker, "read_sales_import_spool_file", MagicMock(return_value=b"erp source"))
    monkeypatch.setattr(worker, "remove_sales_import_spool_file", MagicMock())
    monkeypatch.setattr(
        services.erp_reconciliation.ErpReconciliationService,
        "process",
        AsyncMock(side_effect=HTTPException(status_code=400, detail="raport invalid")),
    )

    with pytest.raises(RuntimeError, match="raport invalid"):
        await worker.reconcile_erp_background(
            {"db_pool": MagicMock()},
            "/private/spool/erp.upload",
            "b" * 64,
            10,
            "erp.xls",
            "2026-08",
        )


@pytest.mark.asyncio
async def test_operations_worker_only_starts_visits_refresh(
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
    monkeypatch.setattr(
        repositories.grile,
        "GrileRepository",
        lambda received_pool: SimpleNamespace(
            reconcile_stale_runs=run_reconcile,
            reconcile_store_refreshes=refresh_reconcile,
        )
        if received_pool is pool
        else None,
    )
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "operations")

    ctx: dict = {}
    await worker.startup(ctx)

    reconcile.assert_not_awaited()
    monthly_reconcile.assert_not_awaited()
    visits_refresh.assert_awaited_once_with(pool)
    export_cleanup.assert_not_awaited()
    orphan_sweep.assert_not_awaited()
    run_reconcile.assert_not_awaited()
    refresh_reconcile.assert_not_awaited()
    assert ctx["db_pool"] is pool
    ctx["visits_snapshot_refresh_task"].cancel()
    await asyncio.gather(ctx["visits_snapshot_refresh_task"], return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("worker_role", ["grile"])
async def test_grile_worker_reconciles_only_expired_leases(
    monkeypatch: pytest.MonkeyPatch,
    worker_role: str,
) -> None:
    pool = MagicMock()
    stale_runs = AsyncMock(return_value=[])
    stale_refreshes = AsyncMock(return_value=[])
    monkeypatch.setattr(db.connection, "init_db_pool", AsyncMock())
    monkeypatch.setattr(db.connection, "get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(
        repositories.grile,
        "GrileRepository",
        lambda received_pool: SimpleNamespace(
            reconcile_stale_runs=stale_runs,
            reconcile_store_refreshes=stale_refreshes,
        )
        if received_pool is pool
        else None,
    )
    adapter = MagicMock()
    adapter.start = AsyncMock()
    monkeypatch.setattr(
        "services.grile_monthly_google.GoogleSyncAdapter",
        lambda: adapter,
    )
    monthly_reconcile = AsyncMock()
    monkeypatch.setattr(
        "services.grile_monthly.reconcile_monthly_operations",
        monthly_reconcile,
    )
    pilot_sync = AsyncMock(return_value={"synced": [], "skipped": []})
    monkeypatch.setattr(
        services.grile_pilot_v2_runtime,
        "sync_grile_pilot_v2_once",
        pilot_sync,
    )
    ctx: dict = {}

    await worker._startup_runtime(ctx, worker_role=worker_role)

    stale_runs.assert_awaited_once_with()
    stale_refreshes.assert_awaited_once_with()
    monthly_reconcile.assert_awaited_once_with(pool, adapter)
    adapter.start.assert_awaited_once_with()
    tasks = [
        ctx["grile_monthly_reconcile_task"],
        ctx["grile_run_reconcile_task"],
        ctx["grile_pilot_v2_sync_task"],
    ]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_grile_monthly_reconciler_recovers_after_one_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    attempts = 0

    async def reconcile(_pool: object, _adapter: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient provider failure")
        stop.set()

    async def no_wait(awaitable, *, timeout: float) -> None:
        del timeout
        awaitable.close()
        raise TimeoutError

    success = MagicMock()
    failure = MagicMock()
    monkeypatch.setattr("services.grile_monthly.reconcile_monthly_operations", reconcile)
    monkeypatch.setattr(grile_supervisor.asyncio, "wait_for", no_wait)
    monkeypatch.setattr(
        "observability.worker_metrics.observe_grile_reconciliation_success",
        success,
    )
    monkeypatch.setattr(
        "observability.worker_metrics.observe_grile_reconciliation_failure",
        failure,
    )

    await grile_supervisor.run_monthly_reconciliation_loop({
        "grile_monthly_reconcile_stop": stop,
        "db_pool": object(),
        "grile_monthly_google": object(),
    })

    assert attempts == 2
    failure.assert_called_once()
    success.assert_called_once()


@pytest.mark.asyncio
async def test_grile_v2_sync_once_uses_shared_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = AsyncMock(return_value={"synced": ["SITE"], "skipped": []})
    monkeypatch.setattr(
        services.grile_pilot_v2_sync,
        "sync_pilot_v2_sheets",
        sync,
    )
    pool = object()
    adapter = object()
    ctx = {"db_pool": pool, "grile_monthly_google": adapter}

    result = await services.grile_pilot_v2_runtime.sync_grile_pilot_v2_once(
        ctx,
        trigger="test",
    )

    assert result == {"synced": ["SITE"], "skipped": []}
    assert isinstance(ctx["grile_pilot_v2_sync_lock"], asyncio.Lock)
    sync.assert_awaited_once_with(pool, adapter)


@pytest.mark.asyncio
async def test_grile_v2_startup_recovery_retains_last_good_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()

    async def fail_once(_ctx: dict, *, trigger: str) -> None:
        assert trigger == "startup-recovery"
        stop.set()
        raise RuntimeError("Google unavailable")

    monkeypatch.setattr(
        services.grile_pilot_v2_runtime,
        "sync_grile_pilot_v2_once",
        fail_once,
    )

    await services.grile_pilot_v2_runtime.run_grile_pilot_v2_sync_loop(
        {"grile_pilot_v2_sync_stop": stop}
    )

    assert stop.is_set()


@pytest.mark.asyncio
async def test_grile_v2_background_validates_month_and_request_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sync = AsyncMock(return_value={"synced": ["SITE"]})
    bind = MagicMock(return_value="token")
    reset = MagicMock()
    monkeypatch.setattr(
        services.grile_pilot_v2_runtime,
        "sync_grile_pilot_v2_once",
        sync,
    )
    monkeypatch.setattr(services.grile_pilot_v2_runtime, "bind_request_id", bind)
    monkeypatch.setattr(services.grile_pilot_v2_runtime, "reset_request_id", reset)

    result = await worker.grile_pilot_v2_sync_background(
        {},
        "2026-08",
        "manual",
        "request-id",
    )

    assert result == {"synced": ["SITE"]}
    sync.assert_awaited_once_with({}, trigger="manual")
    bind.assert_called_once_with("request-id")
    reset.assert_called_once_with("token")
    with pytest.raises(ValueError, match="August 2026"):
        await worker.grile_pilot_v2_sync_background({}, "2026-09", "manual")


@pytest.mark.asyncio
async def test_campaign_publication_triggers_grile_v2_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    promotion = services.campaign_reporting.CampaignReportingPublication(
        period="2026-08",
        generation_id=7,
        revision=11,
        row_count=2,
        status="official",
        input_sha256="a" * 64,
    )
    contest = services.contest_reporting.ContestReportingPublication(
        period="2026-08",
        generation_id=8,
        revision=5,
        row_count=1,
        status="official",
        input_sha256="b" * 64,
    )
    publish_promotion = AsyncMock(return_value=promotion)
    publish_contest = AsyncMock(return_value=contest)
    monkeypatch.setattr(
        services.campaign_reporting,
        "CampaignReportingPublisher",
        lambda _pool: SimpleNamespace(publish_month=publish_promotion),
    )
    monkeypatch.setattr(
        services.contest_reporting,
        "ContestReportingPublisher",
        lambda _pool: SimpleNamespace(publish_month=publish_contest),
    )
    trigger = AsyncMock()
    monkeypatch.setattr(
        services.grile_pilot_v2_runtime,
        "trigger_grile_pilot_v2_sync",
        trigger,
    )
    pool = object()

    result = await worker.publish_campaign_reporting_background(
        {"db_pool": pool},
        "2026-08",
        "system:test",
        "sales_generation:7",
    )

    assert result["promotion"]["revision"] == 11
    assert result["contest"]["revision"] == 5
    publish_promotion.assert_awaited_once_with(
        "2026-08",
        requested_by_sub="system:test",
        reason="sales_generation:7",
    )
    publish_contest.assert_awaited_once_with(
        "2026-08",
        requested_by_sub="system:test",
        reason="sales_generation:7",
    )
    trigger.assert_awaited_once_with(
        "2026-08",
        trigger="campaign_reporting:11",
    )


@pytest.mark.asyncio
async def test_invariant_task_exit_requests_worker_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def complete() -> None:
        return None

    task = asyncio.create_task(complete())
    await task
    terminate = MagicMock()
    monkeypatch.setattr(grile_supervisor.os, "kill", terminate)

    grile_supervisor.terminate_on_invariant_task_exit(
        task,
        stop=asyncio.Event(),
        name="critical-loop",
    )

    terminate.assert_called_once_with(
        grile_supervisor.os.getpid(),
        grile_supervisor.signal.SIGTERM,
    )


@pytest.mark.asyncio
async def test_export_cleanup_loop_isolates_db_cleanup_and_still_sweeps_orphans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop = asyncio.Event()
    cleanup = AsyncMock(side_effect=RuntimeError("db cleanup failed"))

    async def sweep(_repo: object, *, namespace: str) -> None:
        assert namespace == "salary"
        stop.set()

    orphan_sweep = AsyncMock(side_effect=sweep)
    monkeypatch.setattr(services.export_operations, "cleanup_export_operations", cleanup)
    monkeypatch.setattr(services.export_operations, "sweep_orphan_export_artifacts", orphan_sweep)
    monkeypatch.setattr(worker, "EXPORT_CLEANUP_SECONDS", 0.001)

    await worker._export_cleanup_loop(
        {
            "export_cleanup_stop": stop,
            "db_pool": MagicMock(),
            "export_artifact_namespace": "salary",
        }
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
    stop = asyncio.Event()
    pending = asyncio.create_task(asyncio.Event().wait())

    await worker.shutdown(
        {
            "grile_pilot_v2_sync_stop": stop,
            "grile_pilot_v2_sync_task": pending,
        }
    )

    assert stop.is_set()
    assert pending.cancelled()
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
    assert settings["queue_name"] == services.jobs.OPERATIONS_QUEUE_NAME
    assert settings["functions"][0].coroutine is worker.refresh_visits_snapshot_background


@pytest.mark.parametrize(
    ("role", "queue_name", "coroutine"),
    [
        ("grile", services.jobs.GRILE_QUEUE_NAME, worker.grile_monthly_background),
        ("exports", services.jobs.EXPORT_QUEUE_NAME, worker.build_complex_export_background),
        (
            "salary_exports",
            services.jobs.SALARY_EXPORT_QUEUE_NAME,
            worker.build_salary_export_background,
        ),
    ],
)
def test_specialized_workers_use_dedicated_queues(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    queue_name: str,
    coroutine: object,
) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)
    monkeypatch.setenv("RETAIL_WORKER_ROLE", role)

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["queue_name"] == queue_name
    assert any(
        entry is coroutine or getattr(entry, "coroutine", None) is coroutine
        for entry in settings["functions"]
    )
    if role in {"exports", "salary_exports"}:
        assert any(
            getattr(entry, "coroutine", None)
            is worker.remove_export_artifact_background
            for entry in settings["functions"]
        )
    worker_instance.run.assert_called_once_with()


def test_retired_legacy_worker_role_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETAIL_WORKER_ROLE", "legacy")

    with pytest.raises(
        config.ConfigError,
        match="operations, imports, grile, exports sau salary_exports",
    ):
        worker.main()


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
