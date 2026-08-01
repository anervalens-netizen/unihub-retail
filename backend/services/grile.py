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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Mapping

import asyncpg

from repositories.grile import GrileRepository
from services.grile_sheets import (
    analyze_grila,
    build_services,
    fetch_grila,
    fetch_mod_time,
    get_credentials,
)

DEFAULT_TOLERANCE = 1.0
DEFAULT_CONCURRENCY = 3  # sub quota Google read (60/min/user); 429 rare la acest nivel
_TRANSIENT = {429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in _TRANSIENT


def _retry_sync(fn, *, attempts: int = 6, base_delay: float = 3.0):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — re-raise dupa retry
            last = exc
            if attempt < attempts - 1 and _is_transient(exc):
                time.sleep(base_delay * (2**attempt))
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
) -> dict[str, Any]:
    reading = analyze_grila(value_ranges)
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
    if not await repo.start_run(run_id, len(sheets)):
        return run_id
    started = time.monotonic()

    # Fail-fast daca lipsesc credentialele (SA file), inainte de a porni thread-urile.
    try:
        await asyncio.to_thread(get_credentials)
    except Exception as exc:  # noqa: BLE001 — lipsa SA / creds
        await repo.finalize_run(
            run_id, status="failed", ok_count=0, problem_count=0,
            error_count=len(sheets), duration_ms=int((time.monotonic() - started) * 1000),
            error_message=str(exc)[:500],
        )
        return run_id

    # googleapiclient/httplib2 NU e thread-safe: fiecare thread isi
    # construieste propriile servicii (thread-local), pe un executor dedicat
    # dimensionat la `concurrency`. Astfel max `concurrency` clienti, fiecare
    # folosit de un singur thread.
    _local = threading.local()

    def _services() -> tuple[Any, Any]:
        if not hasattr(_local, "svc"):
            _local.svc = build_services()
        return _local.svc

    def _fetch_one(sid: str, template_version: str) -> tuple[list, str | None]:
        sheets_svc, drive_svc = _services()
        value_ranges = _retry_sync(
            lambda: fetch_grila(sheets_svc, sid, template_version)
        )
        mod_raw = _retry_sync(lambda: fetch_mod_time(drive_svc, sid))
        return value_ranges, mod_raw

    executor = ThreadPoolExecutor(max_workers=concurrency)
    loop = asyncio.get_running_loop()
    progress = {"done": 0}
    progress_lock = asyncio.Lock()

    async def process(sheet: asyncpg.Record) -> str:
        site = sheet["site_code"]
        sid = sheet["sheet_id"]
        exp = expected.get(site, {})
        try:
            value_ranges, mod_raw = await loop.run_in_executor(
                executor,
                _fetch_one,
                sid,
                sheet["template_version"],
            )
            row = _status_from_google(
                site_code=site,
                expected=exp,
                value_ranges=value_ranges,
                modified_time=mod_raw,
                tolerance=tolerance,
            )
            cls = row["_class"]
        except Exception as exc:  # noqa: BLE001 — eroare per magazin, nu opreste runul
            row = {
                "site_code": site,
                "db_target": _num(exp.get("db_target")),
                "db_sales_mtd": _num(exp.get("db_sales_mtd")),
                "db_max_sale_date": exp.get("db_max_sale_date"),
                "fill_status": None,
                "target_status": None,
                "sales_status": None,
                "tolerance": tolerance,
                "error_code": "GOOGLE_ERROR",
                "error_message": str(exc)[:500],
            }
            cls = "error"
        await repo.upsert_store_status(run_id, row, checked_by_sub=triggered_by_sub)
        async with progress_lock:
            progress["done"] += 1
            if progress["done"] % 5 == 0 or progress["done"] == len(sheets):
                await repo.set_run_progress(run_id, progress["done"])
        return cls

    try:
        results = await asyncio.gather(*[process(s) for s in sheets], return_exceptions=False)
    finally:
        executor.shutdown(wait=True)

    ok = sum(1 for r in results if r == "ok")
    err = sum(1 for r in results if r == "error")
    problem = len(results) - ok - err
    await repo.finalize_run(
        run_id, status="completed", ok_count=ok, problem_count=problem,
        error_count=err, duration_ms=int((time.monotonic() - started) * 1000),
    )
    return run_id


async def refresh_grile_store(
    pool: asyncpg.Pool,
    *,
    month: str,
    site_code: str,
    requested_by_sub: str,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Read and persist one active grid without mutating full-run audit rows."""
    repo = GrileRepository(pool)
    sheet = await repo.get_active_sheet(site_code, month)
    if sheet is None:
        raise LookupError("Grila activa nu exista pentru magazin.")
    expected = (await repo.get_expected_by_site(month)).get(site_code, {})
    previous = await repo.get_current_status(month, site_code)

    def fetch_one() -> tuple[list[dict[str, Any]], str | None]:
        sheets_service, drive_service = build_services()
        values = _retry_sync(
            lambda: fetch_grila(
                sheets_service,
                sheet["sheet_id"],
                sheet["template_version"],
            )
        )
        modified = _retry_sync(lambda: fetch_mod_time(drive_service, sheet["sheet_id"]))
        return values, modified

    try:
        await asyncio.to_thread(get_credentials)
        value_ranges, modified_time = await asyncio.to_thread(fetch_one)
        row = _status_from_google(
            site_code=site_code,
            expected=expected,
            value_ranges=value_ranges,
            modified_time=modified_time,
            tolerance=tolerance,
        )
    except Exception as exc:  # noqa: BLE001 - persisted as a per-store Google error
        row = {
            "site_code": site_code,
            "db_target": _num(expected.get("db_target")),
            "db_sales_mtd": _num(expected.get("db_sales_mtd")),
            "db_max_sale_date": expected.get("db_max_sale_date"),
            "fill_status": None,
            "target_status": None,
            "sales_status": None,
            "tolerance": tolerance,
            "error_code": "GOOGLE_ERROR",
            "error_message": str(exc)[:500],
            "content_sha256": None,
        }

    previous_hash = previous["content_sha256"] if previous is not None else None
    await repo.upsert_current_status(
        month=month,
        row=row,
        checked_by_sub=requested_by_sub,
    )
    current_hash = row.get("content_sha256")
    return {
        "site_code": site_code,
        "changed": previous is None or previous_hash != current_hash,
        "status": "error" if row.get("error_code") else "ok",
    }


# ---------- overview (citeste doar din DB) ----------

async def resolve_month(pool: asyncpg.Pool, month: str | None) -> str:
    """Daca month e None, foloseste ultima luna cu vanzari importate."""
    if month:
        return month
    repo = GrileRepository(pool)
    return await repo.get_latest_data_month() or datetime.now().strftime("%Y-%m")


async def get_overview(pool: asyncpg.Pool, month: str) -> dict[str, Any]:
    repo = GrileRepository(pool)
    total_sheets = await repo.count_active_sheets(month)
    latest = await repo.get_latest_run(month)
    hierarchy = await repo.get_hierarchy()
    sheet_map = await repo.get_sheet_map(month)

    run_info: dict[str, Any] | None = None
    stores: list[dict[str, Any]] = []
    if latest is not None:
        run_info = _run_to_dict(latest)
        statuses = await repo.get_current_statuses(month)
        for st in statuses:
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
                "grila_target": grila_target,
                "grila_sales": grila_sales,
                "db_target": db_target,
                "db_sales_mtd": db_sales,
                # diff = grila - DB (Raport), ca in aplicatia veche (ex: +960)
                "target_diff": (grila_target - db_target) if (grila_target is not None and db_target is not None) else None,
                "sales_diff": (grila_sales - db_sales) if (grila_sales is not None and db_sales is not None) else None,
                "db_max_sale_date": st["db_max_sale_date"].isoformat() if st["db_max_sale_date"] else None,
                "fill_status": st["fill_status"],
                "target_status": st["target_status"],
                "sales_status": st["sales_status"],
                "missing_days": missing_days,
                "days_elapsed": days_elapsed,
                "error_code": st["error_code"],
                "error_message": st["error_message"],
            })

        # Overview-ul este despre cohorta Grile activa acum. Rularile istorice
        # raman nemodificate in DB, dar magazinele inchise nu trebuie sa reapara
        # in sumar doar fiindca au participat la o verificare mai veche.
        error_count = sum(1 for store in stores if store["error_code"])
        ok_count = sum(
            1
            for store in stores
            if not store["error_code"]
            and store["target_status"] == "OK"
            and store["sales_status"] == "OK"
        )
        run_info.update(
            {
                "progress_current": len(stores),
                "progress_total": total_sheets,
                "ok_count": ok_count,
                "problem_count": len(stores) - ok_count - error_count,
                "error_count": error_count,
            }
        )

    return {
        "month": month,
        "total_sheets": total_sheets,
        "run": run_info,
        "managers": _group_managers(stores),
    }


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

    today = today or datetime.now().date()
    if (year, month_num) == (today.year, today.month):
        return max(today.day - 1, 0)
    if (year, month_num) > (today.year, today.month):
        return 0
    return calendar.monthrange(year, month_num)[1]


def _run_to_dict(r: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "run_month": r["run_month"],
        "source": r["source"],
        "source_snapshot_id": r["source_snapshot_id"],
        "status": r["status"],
        "progress_current": r["progress_current"],
        "progress_total": r["progress_total"],
        "ok_count": r["ok_count"],
        "problem_count": r["problem_count"],
        "error_count": r["error_count"],
        "duration_ms": r["duration_ms"],
        "error_message": r["error_message"],
        "started_at": r["started_at"].isoformat() if r["started_at"] else None,
        "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    }


def _f(value: Any) -> float | None:
    return None if value is None else float(value)
