from __future__ import annotations

import asyncio
from datetime import date

from services import grile
from services.grile import _completed_days_for_month, _normalize_completion_window


def test_normalize_completion_window_removes_current_day_from_existing_run() -> None:
    completion_pct, missing_days, days_elapsed = _normalize_completion_window(
        month="2026-06",
        completion_pct=66.7,
        missing_days=[3],
        days_elapsed=3,
        today=date(2026, 6, 3),
    )

    assert completion_pct == 100.0
    assert missing_days == []
    assert days_elapsed == 2


def test_normalize_completion_window_keeps_yesterday_missing() -> None:
    completion_pct, missing_days, days_elapsed = _normalize_completion_window(
        month="2026-06",
        completion_pct=33.3,
        missing_days=[2, 3],
        days_elapsed=3,
        today=date(2026, 6, 3),
    )

    assert completion_pct == 50.0
    assert missing_days == [2]
    assert days_elapsed == 2


def test_completed_days_for_current_month_excludes_today() -> None:
    assert _completed_days_for_month("2026-06", today=date(2026, 6, 3)) == 2


def test_completed_days_for_past_month_uses_full_month() -> None:
    assert _completed_days_for_month("2026-05", today=date(2026, 6, 3)) == 31


def test_overview_reprojects_historical_run_to_current_active_grid_scope(monkeypatch) -> None:
    latest = {
        "id": 7,
        "run_month": "2026-07",
        "source": "manual",
        "source_snapshot_id": None,
        "status": "completed",
        "progress_current": 3,
        "progress_total": 3,
        "ok_count": 1,
        "problem_count": 2,
        "error_count": 0,
        "duration_ms": 10,
        "error_message": None,
        "started_at": None,
        "finished_at": None,
        "created_at": None,
    }

    def status(site_code: str, *, ok: bool) -> dict:
        return {
            "site_code": site_code,
            "completion_pct": 100,
            "last_edit": None,
            "grila_target": 10,
            "grila_sales": 10,
            "db_target": 10,
            "db_sales_mtd": 10,
            "db_max_sale_date": None,
            "fill_status": "COMPLETAT",
            "target_status": "OK" if ok else "DIFERENTA",
            "sales_status": "OK",
            "error_code": None,
            "error_message": None,
                "raw_summary": None,
                "checked_at": None,
        }

    class Repository:
        def __init__(self, _pool) -> None:
            pass

        async def count_active_sheets(self, _month: str) -> int:
            return 2

        async def get_latest_run(self, _month: str):
            return latest

        async def get_hierarchy(self):
            return {
                code: {
                    "locatie": code,
                    "firma": "Mobiup",
                    "regional": "Manager",
                    "asm": "ASM",
                    "team_leader_name": None,
                }
                for code in ("ACTIVE_OK", "ACTIVE_PROBLEM", "CLOSED")
            }

        async def get_sheet_map(self, _month: str):
            return {"ACTIVE_OK": "sheet-a", "ACTIVE_PROBLEM": "sheet-b"}

        async def get_current_statuses(self, _month: str):
            return [
                status("ACTIVE_OK", ok=True),
                status("ACTIVE_PROBLEM", ok=False),
                status("CLOSED", ok=False),
            ]

    monkeypatch.setattr(grile, "GrileRepository", Repository)

    result = asyncio.run(grile.get_overview(object(), "2026-07"))

    assert result["total_sheets"] == 2
    assert result["run"]["progress_current"] == 2
    assert result["run"]["progress_total"] == 2
    assert result["run"]["ok_count"] == 1
    assert result["run"]["problem_count"] == 1
    assert result["run"]["error_count"] == 0
    visible = {
        store["site_code"]
        for manager in result["managers"]
        for team_leader in manager["team_leaders"]
        for firm in team_leader["firms"]
        for store in firm["stores"]
    }
    assert visible == {"ACTIVE_OK", "ACTIVE_PROBLEM"}


def test_store_refresh_worker_persists_through_fenced_operation(monkeypatch) -> None:
    values = [
        {"values": [[100]]},
        {"values": [[50]]},
        {"values": []},
        {"values": []},
        {"values": []},
    ]
    persisted: list[dict] = []
    finished: list[dict] = []
    closed: list[object] = []

    class Repository:
        def __init__(self, _pool) -> None:
            pass

        async def claim_store_refresh(self, refresh_id: int):
            assert refresh_id == 19
            return {
                "id": refresh_id,
                "run_month": "2026-07",
                "site_code": "SITE01",
                "generation": 4,
                "requested_by_sub": "subject",
            }

        async def get_active_sheet(self, site_code: str, month: str):
            assert (site_code, month) == ("SITE01", "2026-07")
            return {"site_code": site_code, "sheet_id": "sheet-1", "template_version": "v2"}

        async def get_expected_by_site(self, _month: str):
            return {"SITE01": {"db_target": 100, "db_sales_mtd": 50}}

        async def record_store_refresh_observation(self, refresh_id: int, row: dict):
            assert refresh_id == 19
            persisted.append(row)
            return True

        async def finish_store_refresh(self, refresh_id: int, **kwargs):
            finished.append({"refresh_id": refresh_id, **kwargs})

    monkeypatch.setattr(grile, "GrileRepository", Repository)
    monkeypatch.setattr(grile, "get_credentials", lambda: object())
    monkeypatch.setattr(grile, "build_services", lambda: (object(), object()))
    monkeypatch.setattr(grile, "close_services", lambda *services: closed.extend(services))
    monkeypatch.setattr(grile, "fetch_grila", lambda *_args: values)
    monkeypatch.setattr(grile, "fetch_mod_time", lambda *_args: None)

    result = asyncio.run(grile.run_grile_store_refresh(object(), refresh_id=19))

    assert result == {
        "operation_id": 19,
        "site_code": "SITE01",
        "status": "completed",
        "projection_applied": True,
    }
    assert len(persisted) == 1
    assert persisted[0]["content_sha256"] == grile._content_sha256(values)
    assert finished == [{"refresh_id": 19, "status": "completed", "error_message": None}]
    assert len(closed) == 2
