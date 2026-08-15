"""Grile Google-check orchestration and persisted refresh lifecycle."""
from __future__ import annotations
import asyncio
from hashlib import sha256
import json
import logging
import time
from datetime import date, datetime
from typing import Any, Mapping

import asyncpg

from business_clock import business_today
from grile.adapters.google_process import (
    GrileGoogleProcessError,
    GrileGoogleSnapshot,
    fetch_grile_snapshot,
)
from grile.domain.completion import COMPLETION_ALGORITHM_VERSION
from repositories.grile import GrileRepository
from services.grile_metrics import GrileStoreRefreshTimings, observe_grile_store_refresh_operation
from services.grile_overview import (
    _aggregate,
    _completed_days_for_month,
    _error_row,
    _f,
    _group_managers,
    _normalize_completion_window,
    _run_to_dict,
    build_overview,
)
from services.grile_sheets import GrileStructureError, analyze_grila

DEFAULT_TOLERANCE = 1.0
DEFAULT_CONCURRENCY = 3  # sub quota Google read (60/min/user); 429 rare la acest nivel
GRILE_RUN_HEARTBEAT_SECONDS = 30.0
GRILE_STORE_REFRESH_HEARTBEAT_SECONDS = 15.0
logger = logging.getLogger(__name__)


def _parse_mod_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def compute_status(
    site_code: str,
    *,
    grila_target: float | None,
    grila_sales: float | None,
    completion_pct: float | None,
    last_edit: datetime | None,
    db_target: float | None,
    db_sales_mtd: float | None,
    db_max_sale_date: date | None,
    tolerance: float,
) -> dict[str, Any]:
    """Calculeaza fill/target/sales status comparand grila cu DB."""
    grila_filled = bool((grila_target or 0) or (grila_sales or 0))
    fill_status = "COMPLETAT" if grila_filled else "NECOMPLETAT"

    if not grila_filled:
        target_status = sales_status = "NECOMPLETAT"
    else:
        # Target — nu se schimba zilnic; OK daca e in toleranta
        if db_target is None or grila_target is None:
            target_status = "DIFERENTA"
        elif abs(grila_target - db_target) <= tolerance:
            target_status = "OK"
        else:
            target_status = "DIFERENTA"

        # Vanzari — OK / IN_URMA (completat dar in urma importului) / DIFERENTA
        if db_sales_mtd is None or grila_sales is None:
            sales_status = "DIFERENTA"
        elif abs(grila_sales - db_sales_mtd) <= tolerance:
            sales_status = "OK"
        elif (
            grila_sales < db_sales_mtd
            and last_edit is not None
            and db_max_sale_date is not None
            and last_edit.date() < db_max_sale_date
        ):
            sales_status = "IN_URMA"
        else:
            sales_status = "DIFERENTA"

    classification = (
        "ok" if (target_status == "OK" and sales_status == "OK") else "problem"
    )
    return {
        "site_code": site_code,
        "completion_pct": completion_pct,
        "last_edit": last_edit,
        "grila_target": grila_target,
        "grila_sales": grila_sales,
        "db_target": db_target,
        "db_sales_mtd": db_sales_mtd,
        "db_max_sale_date": db_max_sale_date,
        "fill_status": fill_status,
        "target_status": target_status,
        "sales_status": sales_status,
        "tolerance": tolerance,
        "error_code": None,
        "error_message": None,
        "raw_summary": None,
        "_class": classification,
    }


def _content_sha256(value_ranges: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        value_ranges,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _status_from_google(
    *,
    run_month: str,
    site_code: str,
    expected: dict[str, Any],
    value_ranges: list[dict[str, Any]],
    modified_time: str | None,
    tolerance: float,
    template_version: str,
) -> dict[str, Any]:
    reading = analyze_grila(
        value_ranges,
        run_month=run_month,
        template_version=template_version,
    )
    row = compute_status(
        site_code,
        grila_target=reading.grila_target,
        grila_sales=reading.grila_sales,
        completion_pct=reading.completion_pct,
        last_edit=_parse_mod_time(modified_time),
        db_target=_num(expected.get("db_target")),
        db_sales_mtd=_num(expected.get("db_sales_mtd")),
        db_max_sale_date=expected.get("db_max_sale_date"),
        tolerance=tolerance,
    )
    row["raw_summary"] = {
        "missing_days": reading.missing_days,
        "days_elapsed": reading.days_elapsed,
    }
    row["completion_algorithm_version"] = reading.completion_algorithm_version
    row["completion_as_of"] = reading.completion_as_of
    row["content_sha256"] = _content_sha256(value_ranges)
    return row


async def _await_provider_or_lease(
    provider_operation: Any,
    *,
    lease_lost: asyncio.Event,
    task_name: str,
) -> tuple[list[dict[str, Any]], str | None]:
    provider_task = asyncio.create_task(provider_operation, name=task_name)
    lease_task = asyncio.create_task(lease_lost.wait(), name=f"{task_name}:lease")
    try:
        done, _ = await asyncio.wait(
            {provider_task, lease_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if lease_task in done and lease_lost.is_set():
            provider_task.cancel()
            await asyncio.gather(provider_task, return_exceptions=True)
            raise RuntimeError("Grile operation lost its DB lease")
        lease_task.cancel()
        await asyncio.gather(lease_task, return_exceptions=True)
        snapshot = await provider_task
        return snapshot.value_ranges, snapshot.modified_time
    except BaseException:
        if not provider_task.done():
            provider_task.cancel()
        if not lease_task.done():
            lease_task.cancel()
        await asyncio.gather(provider_task, lease_task, return_exceptions=True)
        raise


async def run_grile_check(
    pool: asyncpg.Pool,
    *,
    month: str,
    source: str = "manual",
    source_snapshot_id: int | None = None,
    triggered_by_sub: str | None = None,
    run_id: int | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> int:
    """Ruleaza verificarea pentru toate magazinele cu sheet activ. Returneaza run_id."""
    repo = GrileRepository(pool)
    sheets = await repo.get_active_sheets(month)
    expected = await repo.get_expected_by_site(month)
    if run_id is None:
        run_id = await repo.reserve_run(
            run_month=month,
            source=source,
            source_snapshot_id=source_snapshot_id,
            triggered_by_sub=triggered_by_sub,
        )
        if run_id is None:
            active = await repo.get_running_run(month)
            if active is None:
                raise RuntimeError("Nu s-a putut rezerva verificarea grilelor")
            return int(active["id"])
    generations = await repo.claim_run(
        run_id,
        progress_total=len(sheets),
        site_codes=[str(sheet["site_code"]) for sheet in sheets],
    )
    if generations is None:
        return run_id
    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _grile_run_heartbeat_loop(
            repo,
            run_id=run_id,
            stop=heartbeat_stop,
            lease_lost=lease_lost,
        ),
        name=f"grile-run-heartbeat:{run_id}",
    )
    try:
        return await _run_claimed_grile_check(
            repo,
            run_id=run_id,
            run_month=month,
            sheets=sheets,
            expected=expected,
            generations=generations,
            triggered_by_sub=triggered_by_sub,
            tolerance=tolerance,
            concurrency=concurrency,
            lease_lost=lease_lost,
        )
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


async def _grile_run_heartbeat_loop(
    repo: GrileRepository,
    *,
    run_id: int,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
    interval: float = GRILE_RUN_HEARTBEAT_SECONDS,
) -> None:
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                continue
            except TimeoutError:
                pass
            try:
                retained = await repo.heartbeat_run(run_id)
            except Exception:  # noqa: BLE001 - next tick may recover a transient DB failure
                logger.exception("Grile run heartbeat failed run_id=%s", run_id)
                continue
            if not retained:
                lease_lost.set()
                return
    except asyncio.CancelledError:
        return


async def _run_claimed_grile_check(
    repo: GrileRepository,
    *,
    run_id: int,
    run_month: str,
    sheets: list[asyncpg.Record],
    expected: dict[str, dict[str, Any]],
    generations: dict[str, int],
    triggered_by_sub: str | None,
    tolerance: float,
    concurrency: int,
    lease_lost: asyncio.Event,
) -> int:
    started = time.monotonic()
    if concurrency < 1:
        raise ValueError("Grile concurrency must be positive")

    provider_slots = asyncio.Semaphore(concurrency)
    progress = 0
    progress_lock = asyncio.Lock()

    async def process(sheet: asyncpg.Record) -> str:
        nonlocal progress
        site = str(sheet["site_code"])
        sid = str(sheet["sheet_id"])
        template_version = str(sheet["template_version"])
        exp = expected.get(site, {})
        if lease_lost.is_set():
            raise RuntimeError("Grile run lost its DB lease")
        try:
            async with provider_slots:
                value_ranges, modified_time = await _await_provider_or_lease(
                    fetch_grile_snapshot(
                        sheet_id=sid,
                        template_version=template_version,
                    ),
                    lease_lost=lease_lost,
                    task_name=f"grile-google:{run_id}:{site}",
                )
            row = _status_from_google(
                run_month=run_month,
                site_code=site,
                expected=exp,
                value_ranges=value_ranges,
                modified_time=modified_time,
                tolerance=tolerance,
                template_version=template_version,
            )
            classification = str(row["_class"])
        except GrileStructureError as exc:
            row = _error_row(
                site,
                exp,
                tolerance,
                "structural_invalid",
                str(exc)[:500],
            )
            classification = "error"
        except GrileGoogleProcessError as exc:
            row = _error_row(site, exp, tolerance, exc.code, exc.message[:500])
            classification = "error"
        except Exception as exc:  # noqa: BLE001 - one provider failure is retained per store
            row = _error_row(site, exp, tolerance, "google_error", str(exc)[:500])
            classification = "error"

        if lease_lost.is_set():
            raise RuntimeError("Grile run stopped before observation persistence")
        await repo.record_full_observation(
            run_id,
            row,
            generation=generations[site],
            checked_by_sub=triggered_by_sub,
        )
        async with progress_lock:
            progress += 1
            if not await repo.set_run_progress(run_id, progress):
                lease_lost.set()
                raise RuntimeError("Grile run lost its DB lease")
        return classification

    tasks = [
        asyncio.create_task(
            process(sheet),
            name=f"grile-store:{run_id}:{sheet['site_code']}",
        )
        for sheet in sheets
    ]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    if lease_lost.is_set():
        raise RuntimeError("Grile run lost its DB lease")
    ok = sum(1 for result in results if result == "ok")
    error = sum(1 for result in results if result == "error")
    problem = len(results) - ok - error
    completed = await repo.finalize_run(
        run_id,
        status="completed",
        ok_count=ok,
        problem_count=problem,
        error_count=error,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    if not completed:
        raise RuntimeError("Grile run lost its DB lease before completion")
    return run_id


@observe_grile_store_refresh_operation
async def run_grile_store_refresh(
    pool: asyncpg.Pool,
    *,
    refresh_id: int,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    timings = GrileStoreRefreshTimings()
    try:
        return await _run_grile_store_refresh(
            pool,
            refresh_id=refresh_id,
            tolerance=tolerance,
            timings=timings,
        )
    finally:
        timings.finish()


async def _store_refresh_heartbeat_loop(
    repo: GrileRepository,
    *,
    refresh_id: int,
    stop: asyncio.Event,
    lease_lost: asyncio.Event,
    interval: float = GRILE_STORE_REFRESH_HEARTBEAT_SECONDS,
) -> None:
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                continue
            except TimeoutError:
                pass
            try:
                retained = await repo.heartbeat_store_refresh(refresh_id)
            except Exception:  # noqa: BLE001 - a later tick can recover a transient DB fault
                logger.exception(
                    "Grile store refresh heartbeat failed refresh_id=%s",
                    refresh_id,
                )
                continue
            if not retained:
                lease_lost.set()
                return
    except asyncio.CancelledError:
        return


async def _claim_store_refresh(
    repo: GrileRepository,
    refresh_id: int,
    timings: GrileStoreRefreshTimings,
) -> tuple[Mapping[str, Any] | None, dict[str, Any] | None]:
    with timings.db():
        refresh = await repo.claim_store_refresh(refresh_id)
    if refresh is None:
        operation = await repo.get_store_refresh(refresh_id)
        return None, {
            "operation_id": refresh_id,
            "status": str(operation["status"]) if operation is not None else "not_found",
        }
    created_at = refresh.get("created_at")
    started_at = refresh.get("started_at")
    if isinstance(created_at, datetime) and isinstance(started_at, datetime):
        timings.queue_wait((started_at - created_at).total_seconds())
    return refresh, None


async def _run_grile_store_refresh(
    pool: asyncpg.Pool,
    *,
    refresh_id: int,
    tolerance: float = DEFAULT_TOLERANCE,
    timings: GrileStoreRefreshTimings,
) -> dict[str, Any]:
    """Consume one persisted refresh with a lease and hard-cancellable provider I/O."""
    repo = GrileRepository(pool)
    refresh, terminal_result = await _claim_store_refresh(repo, refresh_id, timings)
    if terminal_result is not None:
        return terminal_result
    assert refresh is not None

    month = str(refresh["run_month"])
    site_code = str(refresh["site_code"])
    heartbeat_stop = asyncio.Event()
    lease_lost = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _store_refresh_heartbeat_loop(
            repo,
            refresh_id=refresh_id,
            stop=heartbeat_stop,
            lease_lost=lease_lost,
        ),
        name=f"grile-store-refresh-heartbeat:{refresh_id}",
    )
    operation_status = "completed"
    error_code: str | None = None
    error_message: str | None = None
    projection_applied: bool | None = None
    try:
        with timings.db():
            sheet = await repo.get_active_sheet(site_code, month)
            expected = (await repo.get_expected_by_site(month)).get(site_code, {})
        if sheet is None:
            operation_status = "failed"
            error_code = "structural_invalid"
            error_message = "Grila activa nu exista pentru magazin."
            row = _error_row(site_code, expected, tolerance, error_code, error_message)
        else:
            provider_started = time.perf_counter()
            try:
                value_ranges, modified_time = await _await_provider_or_lease(
                    fetch_grile_snapshot(
                        sheet_id=str(sheet["sheet_id"]),
                        template_version=str(sheet["template_version"]),
                    ),
                    lease_lost=lease_lost,
                    task_name=f"grile-store-refresh-google:{refresh_id}",
                )
                row = _status_from_google(
                    run_month=month,
                    site_code=site_code,
                    expected=expected,
                    value_ranges=value_ranges,
                    modified_time=modified_time,
                    tolerance=tolerance,
                    template_version=str(sheet["template_version"]),
                )
            except GrileStructureError as exc:
                operation_status = "failed"
                error_code = "structural_invalid"
                error_message = str(exc)[:500]
                row = _error_row(site_code, expected, tolerance, error_code, error_message)
            except GrileGoogleProcessError as exc:
                operation_status = "failed"
                error_code = exc.code
                error_message = exc.message[:500]
                row = _error_row(site_code, expected, tolerance, error_code, error_message)
            except Exception as exc:  # noqa: BLE001 - provider detail is retained in a finite contract
                operation_status = "failed"
                error_code = "google_error"
                error_message = str(exc)[:500]
                row = _error_row(site_code, expected, tolerance, error_code, error_message)
            finally:
                timings.provider(time.perf_counter() - provider_started)

        if lease_lost.is_set():
            raise RuntimeError("Grile store refresh lost its DB lease")
        with timings.db():
            projection_applied = await repo.complete_store_refresh(
                refresh_id,
                row,
                status=operation_status,
                error_code=error_code,
                error_message=error_message,
            )
        return {
            "operation_id": refresh_id,
            "site_code": site_code,
            "status": operation_status,
            "projection_applied": projection_applied,
            "error_code": error_code,
        }
    except asyncio.CancelledError:
        await repo.finish_store_refresh(
            refresh_id,
            status="cancelled",
            projection_applied=projection_applied,
            error_code="worker_cancelled",
            error_message="Grile store refresh was cancelled",
        )
        raise
    except Exception as exc:
        await repo.finish_store_refresh(
            refresh_id,
            status="failed",
            projection_applied=projection_applied,
            error_code="worker_failed",
            error_message=str(exc)[:500],
        )
        raise
    finally:
        heartbeat_stop.set()
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


# ---------- overview (citeste doar din DB) ----------

async def resolve_month(pool: asyncpg.Pool, month: str | None) -> str:
    """Daca month e None, foloseste ultima luna cu vanzari importate."""
    if month:
        return month
    repo = GrileRepository(pool)
    return await repo.get_latest_data_month() or business_today().strftime("%Y-%m")


async def get_overview(pool: asyncpg.Pool, month: str) -> dict[str, Any]:
    return await build_overview(GrileRepository(pool), month)
