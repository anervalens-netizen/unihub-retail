"""Serviciu Grile — verificare K5/L5 (Google Sheets) vs target/vanzari DB.

run_grile_check ruleaza in worker (arq), face munca lenta Google in thread
(clientul Google e sincron), persista rezultatele in DB. get_overview citeste
doar din DB (rapid), grupat ASM(regional) -> Team Leader -> Firma -> Magazin.
"""

from __future__ import annotations

import asyncio
import calendar
from hashlib import sha256
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Mapping

import asyncpg

from business_clock import business_today
from repositories.grile import GrileRepository
from services.grile_metrics import GrileStoreRefreshTimings
from services.grile_sheets import (
    GrileStructureError,
    analyze_grila,
    build_services,
    close_services,
    fetch_grila,
    fetch_mod_time,
    get_credentials,
)

DEFAULT_TOLERANCE = 1.0
DEFAULT_CONCURRENCY = 3  # sub quota Google read (60/min/user); 429 rare la acest nivel
GRILE_RUN_HEARTBEAT_SECONDS = 30.0
_TRANSIENT = {429, 500, 502, 503, 504}
logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in _TRANSIENT


def _retry_sync(
    fn,
    *,
    attempts: int = 6,
    base_delay: float = 3.0,
    stop_event: threading.Event | None = None,
):
    last: Exception | None = None
    for attempt in range(attempts):
        if stop_event is not None and stop_event.is_set():
            raise RuntimeError("Grile Google work cancelled")
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — re-raise dupa retry
            last = exc
            if attempt < attempts - 1 and _is_transient(exc):
                delay = base_delay * (2**attempt)
                if stop_event is not None:
                    if stop_event.wait(delay):
                        raise RuntimeError("Grile Google work cancelled") from exc
                else:
                    time.sleep(delay)
                continue
            raise
    assert last is not None  # pragma: no cover
    raise last


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
    site_code: str,
    expected: dict[str, Any],
    value_ranges: list[dict[str, Any]],
    modified_time: str | None,
    tolerance: float,
    template_version: str,
) -> dict[str, Any]:
    reading = analyze_grila(value_ranges, template_version=template_version)
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
    row["content_sha256"] = _content_sha256(value_ranges)
    return row


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
    sheets: list[asyncpg.Record],
    expected: dict[str, dict[str, Any]],
    generations: dict[str, int],
    triggered_by_sub: str | None,
    tolerance: float,
    concurrency: int,
    lease_lost: asyncio.Event,
) -> int:
    started = time.monotonic()
    try:
        await asyncio.to_thread(get_credentials)
    except Exception as exc:  # noqa: BLE001 — lipsa SA / creds
        await repo.finalize_run(
            run_id,
            status="failed",
            ok_count=0,
            problem_count=0,
            error_count=len(sheets),
            duration_ms=int((time.monotonic() - started) * 1000),
            error_message=str(exc)[:500],
        )
        return run_id

    google_stop = threading.Event()

    def _fetch_one(sid: str, template_version: str) -> tuple[list, str | None]:
        sheets_svc, drive_svc = build_services()
        try:
            value_ranges = _retry_sync(
                lambda: fetch_grila(sheets_svc, sid, template_version),
                stop_event=google_stop,
            )
            mod_raw = _retry_sync(
                lambda: fetch_mod_time(drive_svc, sid),
                stop_event=google_stop,
            )
            return value_ranges, mod_raw
        finally:
            close_services(sheets_svc, drive_svc)

    executor = ThreadPoolExecutor(max_workers=concurrency)
    loop = asyncio.get_running_loop()
    progress = 0
    progress_lock = asyncio.Lock()

    async def process(sheet: asyncpg.Record) -> str:
        nonlocal progress
        site = str(sheet["site_code"])
        sid = str(sheet["sheet_id"])
        exp = expected.get(site, {})
        if lease_lost.is_set():
            raise RuntimeError("Grile run lost its DB lease")
        try:
            value_ranges, mod_raw = await loop.run_in_executor(
                executor,
                _fetch_one,
                sid,
                str(sheet["template_version"]),
            )
            row = _status_from_google(
                site_code=site,
                expected=exp,
                value_ranges=value_ranges,
                modified_time=mod_raw,
                tolerance=tolerance,
                template_version=str(sheet["template_version"]),
            )
            cls = row["_class"]
        except GrileStructureError as exc:
            row = _error_row(site, exp, tolerance, "STRUCTURAL_INVALID", str(exc)[:500])
            cls = "error"
        except Exception as exc:  # noqa: BLE001 — eroare Google per magazin
            row = _error_row(site, exp, tolerance, "GOOGLE_ERROR", str(exc)[:500])
            cls = "error"
        if lease_lost.is_set() or google_stop.is_set():
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
        return cls

    tasks = [
        asyncio.create_task(process(sheet), name=f"grile-store:{run_id}:{sheet['site_code']}")
        for sheet in sheets
    ]
    try:
        results = await asyncio.gather(*tasks)
    except BaseException:
        google_stop.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        google_stop.set()
        executor.shutdown(wait=False, cancel_futures=True)

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


async def run_grile_store_refresh(
    pool: asyncpg.Pool,
    *,
    refresh_id: int,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Consume one reserved refresh and always publish its phase metrics."""
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


async def _run_grile_store_refresh(
    pool: asyncpg.Pool,
    *,
    refresh_id: int,
    tolerance: float = DEFAULT_TOLERANCE,
    timings: GrileStoreRefreshTimings,
) -> dict[str, Any]:
    """Consume only a pre-reserved refresh from the operations worker."""
    repo = GrileRepository(pool)
    with timings.db():
        refresh = await repo.claim_store_refresh(refresh_id)
    if refresh is None:
        return {"operation_id": refresh_id, "status": "not_claimed"}

    created_at = refresh.get("created_at")
    started_at = refresh.get("started_at")
    if isinstance(created_at, datetime) and isinstance(started_at, datetime):
        timings.queue_wait((started_at - created_at).total_seconds())

    month = str(refresh["run_month"])
    site_code = str(refresh["site_code"])
    with timings.db():
        sheet = await repo.get_active_sheet(site_code, month)
        expected = (await repo.get_expected_by_site(month)).get(site_code, {})
    operation_status = "completed"
    error_message: str | None = None

    if sheet is None:
        operation_status = "failed"
        error_message = "Grila activa nu exista pentru magazin."
        row = _error_row(site_code, expected, tolerance, "STRUCTURAL_INVALID", error_message)
    else:
        def fetch_one() -> tuple[list[dict[str, Any]], str | None]:
            sheets_service, drive_service = build_services()
            try:
                values = _retry_sync(
                    lambda: fetch_grila(sheets_service, sheet["sheet_id"], sheet["template_version"])
                )
                modified = _retry_sync(lambda: fetch_mod_time(drive_service, sheet["sheet_id"]))
                return values, modified
            finally:
                close_services(sheets_service, drive_service)

        provider_started = time.perf_counter()
        try:
            await asyncio.to_thread(get_credentials)
            value_ranges, modified_time = await asyncio.to_thread(fetch_one)
            row = _status_from_google(
                site_code=site_code,
                expected=expected,
                value_ranges=value_ranges,
                modified_time=modified_time,
                tolerance=tolerance,
                template_version=sheet["template_version"],
            )
        except GrileStructureError as exc:
            operation_status = "failed"
            error_message = str(exc)[:500]
            row = _error_row(site_code, expected, tolerance, "STRUCTURAL_INVALID", error_message)
        except Exception as exc:  # noqa: BLE001 - keep last success and error separately
            operation_status = "failed"
            error_message = str(exc)[:500]
            row = _error_row(site_code, expected, tolerance, "GOOGLE_ERROR", error_message)
        finally:
            timings.provider(time.perf_counter() - provider_started)

    with timings.db():
        projection_applied = await repo.record_store_refresh_observation(refresh_id, row)
        await repo.finish_store_refresh(refresh_id, status=operation_status, error_message=error_message)
    return {
        "operation_id": refresh_id,
        "site_code": site_code,
        "status": operation_status,
        "projection_applied": projection_applied,
    }


def _error_row(
    site_code: str,
    expected: dict[str, Any],
    tolerance: float,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "site_code": site_code,
        "db_target": _num(expected.get("db_target")),
        "db_sales_mtd": _num(expected.get("db_sales_mtd")),
        "db_max_sale_date": expected.get("db_max_sale_date"),
        "fill_status": None,
        "target_status": None,
        "sales_status": None,
        "tolerance": tolerance,
        "error_code": error_code,
        "error_message": error_message,
        "content_sha256": None,
    }


# ---------- overview (citeste doar din DB) ----------

async def resolve_month(pool: asyncpg.Pool, month: str | None) -> str:
    """Daca month e None, foloseste ultima luna cu vanzari importate."""
    if month:
        return month
    repo = GrileRepository(pool)
    return await repo.get_latest_data_month() or business_today().strftime("%Y-%m")


async def get_overview(pool: asyncpg.Pool, month: str) -> dict[str, Any]:
    repo = GrileRepository(pool)
    await repo.reconcile_stale_runs(run_month=month)
    total_sheets = await repo.count_active_sheets(month)
    latest = await repo.get_latest_run(month)
    hierarchy = await repo.get_hierarchy()
    sheet_map = await repo.get_sheet_map(month)
    run_info: dict[str, Any] | None = _run_to_dict(latest) if latest is not None else None
    stores: list[dict[str, Any]] = []

    # Store refreshes are useful even before the first full run, so the current
    # projection—not the latest run—determines what the read model can show.
    for st in await repo.get_current_statuses(month):
        if st["site_code"] not in sheet_map:
            continue
        h = hierarchy.get(st["site_code"], {})
        grila_target = _f(st["grila_target"])
        grila_sales = _f(st["grila_sales"])
        db_target = _f(st["db_target"])
        db_sales = _f(st["db_sales_mtd"])
        raw = st["raw_summary"]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raw = None
        completion_pct = _f(st["completion_pct"])
        missing_days = (raw or {}).get("missing_days") if isinstance(raw, dict) else None
        days_elapsed = (raw or {}).get("days_elapsed") if isinstance(raw, dict) else None
        completion_pct, missing_days, days_elapsed = _normalize_completion_window(
            month=month,
            completion_pct=completion_pct,
            missing_days=missing_days,
            days_elapsed=days_elapsed,
        )
        last_success = st.get("last_success_checked_at")
        last_error = st.get("last_error_checked_at")
        stores.append({
            "site_code": st["site_code"],
            "sheet_id": sheet_map.get(st["site_code"]),
            "locatie": h.get("locatie", st["site_code"]),
            "firma": h.get("firma", ""),
            "regional": h.get("regional", "Neatribuit"),
            "asm": h.get("asm", ""),
            "team_leader_name": h.get("team_leader_name"),
            "completion_pct": completion_pct,
            "last_edit": st["last_edit"].isoformat() if st["last_edit"] else None,
            "checked_at": st["checked_at"].isoformat() if st["checked_at"] else None,
            "last_success_checked_at": last_success.isoformat() if last_success else None,
            "last_error_checked_at": last_error.isoformat() if last_error else None,
            "last_error_code": st.get("last_error_code"),
            "last_error_message": st.get("last_error_message"),
            "stale_age_seconds": _stale_age_seconds(last_success),
            "grila_target": grila_target,
            "grila_sales": grila_sales,
            "db_target": db_target,
            "db_sales_mtd": db_sales,
            "target_diff": (grila_target - db_target) if (grila_target is not None and db_target is not None) else None,
            "sales_diff": (grila_sales - db_sales) if (grila_sales is not None and db_sales is not None) else None,
            "db_max_sale_date": st["db_max_sale_date"].isoformat() if st["db_max_sale_date"] else None,
            "fill_status": st["fill_status"],
            "target_status": st["target_status"],
            "sales_status": st["sales_status"],
            "missing_days": missing_days,
            "days_elapsed": days_elapsed,
            # The display state remains the last successful observation; errors
            # are exposed above as independent metadata and do not erase it.
            "error_code": st["error_code"],
            "error_message": st["error_message"],
        })

    error_count = sum(1 for store in stores if store["error_code"])
    ok_count = sum(
        1 for store in stores
        if not store["error_code"]
        and store["target_status"] == "OK"
        and store["sales_status"] == "OK"
    )
    if run_info is not None:
        run_info.update({
            "progress_current": len(stores),
            "progress_total": total_sheets,
            "ok_count": ok_count,
            "problem_count": len(stores) - ok_count - error_count,
            "error_count": error_count,
        })
    return {
        "month": month,
        "total_sheets": total_sheets,
        "run": run_info,
        "managers": _group_managers(stores),
    }


def _stale_age_seconds(last_success: datetime | None) -> int | None:
    if last_success is None:
        return None
    return max(0, int((datetime.now(tz=last_success.tzinfo) - last_success).total_seconds()))


def _group_managers(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grupare ASM(regional) -> Team Leader -> Firma -> Magazin."""
    managers: dict[str, dict[str, Any]] = {}
    for s in stores:
        mgr = s["regional"] or "Neatribuit"
        m = managers.setdefault(mgr, {"name": mgr, "team_leaders": {}, "stores": []})
        m["stores"].append(s)
        tl = m["team_leaders"].setdefault(
            s["team_leader_name"], {"name": s["team_leader_name"], "firms": {}}
        )
        firm = tl["firms"].setdefault(s["firma"] or "—", {"name": s["firma"] or "—", "stores": []})
        firm["stores"].append(s)

    def _tl_sort_key(tl: dict[str, Any]) -> tuple[bool, str]:
        # TL-urile cu nume primele (alfabetic), grupul fara TL ultimul
        return (tl["name"] is None, (tl["name"] or "").lower())

    result = []
    for m in sorted(managers.values(), key=lambda x: -len(x["stores"])):
        tls = [
            {"name": tl["name"], "firms": list(tl["firms"].values())}
            for tl in sorted(m["team_leaders"].values(), key=_tl_sort_key)
        ]
        agg = _aggregate(m["stores"])
        result.append({"name": m["name"], "store_count": len(m["stores"]), "team_leaders": tls, **agg})
    return result


def _aggregate(stores: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ok": sum(1 for s in stores if s["target_status"] == "OK" and s["sales_status"] == "OK"),
        "problems": sum(
            1 for s in stores
            if not (s["target_status"] == "OK" and s["sales_status"] == "OK")
        ),
        "avg_completion": (
            round(sum(s["completion_pct"] or 0 for s in stores) / len(stores), 1)
            if stores else None
        ),
    }


def _normalize_completion_window(
    *,
    month: str,
    completion_pct: float | None,
    missing_days: Any,
    days_elapsed: Any,
    today: date | None = None,
) -> tuple[float | None, list[int] | None, int | None]:
    """Exclude ziua curenta si la afisarea runurilor deja salvate."""
    if not isinstance(days_elapsed, int) or not isinstance(missing_days, list):
        return completion_pct, missing_days if isinstance(missing_days, list) else None, days_elapsed

    max_elapsed = _completed_days_for_month(month, today=today)
    if max_elapsed is None:
        return completion_pct, missing_days, days_elapsed

    normalized_elapsed = min(days_elapsed, max_elapsed)
    normalized_missing = [
        int(day)
        for day in missing_days
        if isinstance(day, int) and 1 <= day <= normalized_elapsed
    ]
    if normalized_elapsed == days_elapsed and normalized_missing == missing_days:
        return completion_pct, missing_days, days_elapsed
    if normalized_elapsed <= 0:
        return None, [], 0

    covered = normalized_elapsed - len(normalized_missing)
    normalized_pct = round(max(covered, 0) / normalized_elapsed * 100, 1)
    return normalized_pct, normalized_missing, normalized_elapsed


def _completed_days_for_month(month: str, *, today: date | None = None) -> int | None:
    try:
        year, month_num = (int(part) for part in month.split("-"))
    except (ValueError, TypeError):
        return None

    today = today or business_today()
    if (year, month_num) == (today.year, today.month):
        return max(today.day - 1, 0)
    if (year, month_num) > (today.year, today.month):
        return 0
    return calendar.monthrange(year, month_num)[1]


def _run_to_dict(r: Mapping[str, Any]) -> dict[str, Any]:
    status = str(r["status"])
    heartbeat_at = r.get("heartbeat_at")
    return {
        "id": r["id"],
        "run_month": r["run_month"],
        "source": r["source"],
        "source_snapshot_id": r["source_snapshot_id"],
        "status": status,
        "active": status in {"queued", "running"},
        "progress_current": r["progress_current"],
        "progress_total": r["progress_total"],
        "ok_count": r["ok_count"],
        "problem_count": r["problem_count"],
        "error_count": r["error_count"],
        "duration_ms": r["duration_ms"],
        "error_message": r["error_message"],
        "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        "heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else None,
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


def _f(value: Any) -> float | None:
    return None if value is None else float(value)
