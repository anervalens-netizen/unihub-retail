"""Database-only Grile overview projection and compatibility helpers."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Mapping

from business_clock import business_today
from config import grile_provider_stale_after_seconds
from grile.domain.completion import COMPLETION_ALGORITHM_VERSION, completed_days_for_month
from grile.domain.provider_health import build_provider_health

def _error_row(
    site_code: str,
    expected: dict[str, Any],
    tolerance: float,
    error_code: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "site_code": site_code,
        "db_target": _f(expected.get("db_target")),
        "db_sales_mtd": _f(expected.get("db_sales_mtd")),
        "db_max_sale_date": expected.get("db_max_sale_date"),
        "fill_status": None,
        "target_status": None,
        "sales_status": None,
        "tolerance": tolerance,
        "completion_algorithm_version": COMPLETION_ALGORITHM_VERSION,
        "completion_as_of": business_today(),
        "error_code": error_code,
        "error_message": error_message,
        "raw_summary": None,
        "content_sha256": None,
    }


# ---------- overview (citeste doar din DB) ----------

def _missing_store_row(
    *,
    month: str,
    site_code: str,
    sheet_id: str | None,
    hierarchy: Mapping[str, Any],
    expected: Mapping[str, Any],
    stale_after_seconds: int,
) -> dict[str, Any]:
    provider = build_provider_health(
        run_month=month,
        last_success_at=None,
        last_error_at=None,
        last_error_code=None,
        last_error_message=None,
        stale_after_seconds=stale_after_seconds,
    )
    return {
        "site_code": site_code,
        "sheet_id": sheet_id,
        "locatie": hierarchy.get("locatie", site_code),
        "firma": hierarchy.get("firma", ""),
        "regional": hierarchy.get("regional", "Neatribuit"),
        "asm": hierarchy.get("asm", ""),
        "team_leader_name": hierarchy.get("team_leader_name"),
        "completion_pct": None,
        "last_edit": None,
        "checked_at": None,
        "grila_target": None,
        "grila_sales": None,
        "db_target": _f(expected.get("db_target")),
        "db_sales_mtd": _f(expected.get("db_sales_mtd")),
        "target_diff": None,
        "sales_diff": None,
        "db_max_sale_date": expected.get("db_max_sale_date"),
        "fill_status": None,
        "target_status": None,
        "sales_status": None,
        "missing_days": None,
        "days_elapsed": None,
        "completion_algorithm_version": COMPLETION_ALGORITHM_VERSION,
        "completion_as_of": None,
        "completion_window_status": "current",
        "provider_status": provider.as_dict(),
        "error_code": None,
        "error_message": None,
    }


def _decoded_summary(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    return value if isinstance(value, dict) else None


def _current_store_row(
    *,
    month: str,
    site_code: str,
    sheet_id: str | None,
    hierarchy: Mapping[str, Any],
    status: Mapping[str, Any],
    stale_after_seconds: int,
) -> dict[str, Any]:
    grila_target = _f(status["grila_target"])
    grila_sales = _f(status["grila_sales"])
    db_target = _f(status["db_target"])
    db_sales = _f(status["db_sales_mtd"])
    raw = _decoded_summary(status["raw_summary"])
    algorithm_version = int(status.get("completion_algorithm_version") or 1)
    provider = build_provider_health(
        run_month=month,
        last_success_at=status.get("last_success_checked_at"),
        last_error_at=status.get("last_error_checked_at"),
        last_error_code=status.get("last_error_code"),
        last_error_message=status.get("last_error_message"),
        stale_after_seconds=stale_after_seconds,
    )
    provider_error = provider.state == "error"
    return {
        "site_code": site_code,
        "sheet_id": sheet_id,
        "locatie": hierarchy.get("locatie", site_code),
        "firma": hierarchy.get("firma", ""),
        "regional": hierarchy.get("regional", "Neatribuit"),
        "asm": hierarchy.get("asm", ""),
        "team_leader_name": hierarchy.get("team_leader_name"),
        "completion_pct": _f(status["completion_pct"]),
        "last_edit": status["last_edit"],
        "checked_at": status["checked_at"],
        "grila_target": grila_target,
        "grila_sales": grila_sales,
        "db_target": db_target,
        "db_sales_mtd": db_sales,
        "target_diff": (
            grila_target - db_target
            if grila_target is not None and db_target is not None
            else None
        ),
        "sales_diff": (
            grila_sales - db_sales
            if grila_sales is not None and db_sales is not None
            else None
        ),
        "db_max_sale_date": status["db_max_sale_date"],
        "fill_status": status["fill_status"],
        "target_status": status["target_status"],
        "sales_status": status["sales_status"],
        "missing_days": raw.get("missing_days") if raw is not None else None,
        "days_elapsed": raw.get("days_elapsed") if raw is not None else None,
        "completion_algorithm_version": algorithm_version,
        "completion_as_of": status.get("completion_as_of"),
        "completion_window_status": (
            "current"
            if algorithm_version >= COMPLETION_ALGORITHM_VERSION
            else "legacy_incomplete_window"
        ),
        "provider_status": provider.as_dict(),
        "error_code": provider.last_error_code if provider_error else None,
        "error_message": provider.last_error_message if provider_error else None,
    }


async def build_overview(repo: Any, month: str) -> dict[str, Any]:
    provider_stale_seconds = grile_provider_stale_after_seconds()
    await repo.reconcile_stale_runs(run_month=month)
    total_sheets = await repo.count_active_sheets(month)
    latest = await repo.get_latest_run(month)
    hierarchy = await repo.get_hierarchy()
    sheet_map = await repo.get_sheet_map(month)
    expected = await repo.get_expected_by_site(month)
    current_statuses = {
        str(status["site_code"]): status
        for status in await repo.get_current_statuses(month)
    }
    run_info: dict[str, Any] | None = _run_to_dict(latest) if latest is not None else None
    stores: list[dict[str, Any]] = []

    for site_code in sorted(sheet_map):
        status = current_statuses.get(site_code)
        hierarchy_row = hierarchy.get(site_code, {})
        expected_row = expected.get(site_code, {})
        if status is None:
            stores.append(
                _missing_store_row(
                    month=month,
                    site_code=site_code,
                    sheet_id=sheet_map.get(site_code),
                    hierarchy=hierarchy_row,
                    expected=expected_row,
                    stale_after_seconds=provider_stale_seconds,
                )
            )
            continue
        stores.append(
            _current_store_row(
                month=month,
                site_code=site_code,
                sheet_id=sheet_map.get(site_code),
                hierarchy=hierarchy_row,
                status=status,
                stale_after_seconds=provider_stale_seconds,
            )
        )

    summary = _aggregate(stores)
    return {
        "month": month,
        "total_sheets": total_sheets,
        # The run keeps the immutable counters produced by that exact full run.
        # Current store refreshes are represented only in the read-model summary.
        "run": run_info,
        "summary": {
            "business_ok": summary["ok"],
            "business_problems": summary["problems"],
            "business_unknown": summary["business_unknown"],
            "provider_fresh": summary["provider_fresh"],
            "provider_errors": summary["provider_errors"],
            "provider_stale": summary["provider_stale"],
            "provider_unknown": summary["provider_unknown"],
            "legacy_completion_windows": summary["legacy_completion_windows"],
        },
        "managers": _group_managers(stores),
    }


def _group_managers(stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group the read model by regional manager, team leader, company and store."""
    managers: dict[str, dict[str, Any]] = {}
    for store in stores:
        manager_name = store["regional"] or "Neatribuit"
        manager = managers.setdefault(
            manager_name,
            {"name": manager_name, "team_leaders": {}, "stores": []},
        )
        manager["stores"].append(store)
        team_leader = manager["team_leaders"].setdefault(
            store["team_leader_name"],
            {"name": store["team_leader_name"], "firms": {}},
        )
        firm = team_leader["firms"].setdefault(
            store["firma"] or "—",
            {"name": store["firma"] or "—", "stores": []},
        )
        firm["stores"].append(store)

    def team_leader_sort_key(team_leader: dict[str, Any]) -> tuple[bool, str]:
        return (
            team_leader["name"] is None,
            (team_leader["name"] or "").lower(),
        )

    result: list[dict[str, Any]] = []
    for manager in sorted(managers.values(), key=lambda value: -len(value["stores"])):
        team_leaders = [
            {
                "name": team_leader["name"],
                "firms": list(team_leader["firms"].values()),
            }
            for team_leader in sorted(
                manager["team_leaders"].values(),
                key=team_leader_sort_key,
            )
        ]
        result.append(
            {
                "name": manager["name"],
                "store_count": len(manager["stores"]),
                "team_leaders": team_leaders,
                **_aggregate(manager["stores"]),
            }
        )
    return result


def _aggregate(stores: list[dict[str, Any]]) -> dict[str, Any]:
    def provider_state(store: dict[str, Any]) -> str:
        return str(store["provider_status"]["state"])

    def has_business_projection(store: dict[str, Any]) -> bool:
        return store.get("target_status") is not None or store.get("sales_status") is not None

    def is_business_ok(store: dict[str, Any]) -> bool:
        return (
            has_business_projection(store)
            and store.get("target_status") == "OK"
            and store.get("sales_status") == "OK"
        )

    completion_values = [
        float(store["completion_pct"])
        for store in stores
        if store.get("completion_pct") is not None
    ]
    return {
        # Business projection and provider transport are intentionally independent.
        "ok": sum(1 for store in stores if is_business_ok(store)),
        "problems": sum(
            1
            for store in stores
            if has_business_projection(store) and not is_business_ok(store)
        ),
        "business_unknown": sum(
            1 for store in stores if not has_business_projection(store)
        ),
        "provider_fresh": sum(
            1 for store in stores if provider_state(store) == "fresh"
        ),
        "provider_errors": sum(
            1 for store in stores if provider_state(store) == "error"
        ),
        "provider_stale": sum(
            1 for store in stores if provider_state(store) == "stale"
        ),
        "provider_unknown": sum(
            1 for store in stores if provider_state(store) == "unknown"
        ),
        "legacy_completion_windows": sum(
            1
            for store in stores
            if store.get("completion_window_status") == "legacy_incomplete_window"
        ),
        "avg_completion": (
            round(sum(completion_values) / len(completion_values), 1)
            if completion_values
            else None
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
    """Compatibility helper for callers outside the v2 read model."""
    if not isinstance(days_elapsed, int) or not isinstance(missing_days, list):
        return (
            completion_pct,
            missing_days if isinstance(missing_days, list) else None,
            days_elapsed,
        )
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
        return completed_days_for_month(month, as_of=today)
    except ValueError:
        return None


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
