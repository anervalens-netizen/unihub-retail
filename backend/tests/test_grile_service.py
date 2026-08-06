from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import date, datetime, timezone
from typing import Any, cast

from repositories.grile import GrileRepository
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

        async def reconcile_stale_runs(self, *, run_month: str):
            assert run_month == "2026-07"
            return []

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
    assert result["run"]["active"] is False
    visible = {
        store["site_code"]
        for manager in result["managers"]
        for team_leader in manager["team_leaders"]
        for firm in team_leader["firms"]
        for store in firm["stores"]
    }
    assert visible == {"ACTIVE_OK", "ACTIVE_PROBLEM"}


def test_store_refresh_worker_persists_through_fenced_operation(monkeypatch) -> None:
    values: list[dict[str, Any]] = [
        {"values": [[100]]},
        {"values": [[50]]},
        {"values": []},
        {"values": []},
        {"values": []},
    ]
    persisted: list[dict] = []
    finished: list[dict] = []
    closed: list[object] = []
    phases: list[tuple[str, float | None]] = []

    class Timings:
        def db(self):
            phases.append(("db", None))
            return nullcontext()

        def queue_wait(self, seconds: float) -> None:
            phases.append(("queue_wait", seconds))

        def provider(self, seconds: float) -> None:
            phases.append(("provider", seconds))

        def finish(self) -> None:
            phases.append(("finish", None))

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
                "created_at": datetime(2026, 7, 1, 12, tzinfo=timezone.utc),
                "started_at": datetime(2026, 7, 1, 12, 0, 2, tzinfo=timezone.utc),
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

    monkeypatch.setattr(grile, "GrileStoreRefreshTimings", Timings)
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
    assert [phase for phase, _seconds in phases] == [
        "db", "queue_wait", "db", "provider", "db", "finish",
    ]
    assert phases[1] == ("queue_wait", 2.0)
    assert phases[3][1] is not None
    assert phases[3][1] >= 0


def test_grile_run_heartbeat_is_periodic_while_job_is_alive() -> None:
    heartbeats = 0

    class Repository:
        async def heartbeat_run(self, run_id: int) -> bool:
            nonlocal heartbeats
            assert run_id == 23
            heartbeats += 1
            return True

    async def scenario() -> None:
        stop = asyncio.Event()
        lost = asyncio.Event()
        task = asyncio.create_task(
            grile._grile_run_heartbeat_loop(
                cast(GrileRepository, Repository()),
                run_id=23,
                stop=stop,
                lease_lost=lost,
                interval=0.001,
            )
        )
        while heartbeats < 2:
            await asyncio.sleep(0)
        stop.set()
        await task
        assert not lost.is_set()

    asyncio.run(scenario())
    assert heartbeats >= 2


def test_claimed_grile_run_completes_and_persistence_failure_is_drained(monkeypatch) -> None:
    values: list[dict[str, Any]] = [
        {"values": [[100]]},
        {"values": [[50]]},
        {"values": []},
        {"values": []},
        {"values": []},
    ]
    closed: list[object] = []
    monkeypatch.setattr(grile, "get_credentials", lambda: object())
    monkeypatch.setattr(grile, "build_services", lambda: (object(), object()))
    monkeypatch.setattr(grile, "close_services", lambda *services: closed.extend(services))
    monkeypatch.setattr(grile, "fetch_grila", lambda *_args: values)
    monkeypatch.setattr(grile, "fetch_mod_time", lambda *_args: None)

    async def scenario() -> None:
        class Repository:
            def __init__(self, *, fail_persistence: bool) -> None:
                self.fail_persistence = fail_persistence
                self.finalized: list[dict[str, Any]] = []
                self.persisting = 0

            async def record_full_observation(self, *_args, **_kwargs) -> bool:
                self.persisting += 1
                try:
                    await asyncio.sleep(0)
                    if self.fail_persistence:
                        raise RuntimeError("synthetic persistence failure")
                    return True
                finally:
                    self.persisting -= 1

            async def set_run_progress(self, *_args) -> bool:
                return True

            async def finalize_run(self, _run_id: int, **kwargs) -> bool:
                self.finalized.append(kwargs)
                return True

        sheets = [
            {"site_code": "S1", "sheet_id": "sheet-1", "template_version": "v2"},
            {"site_code": "S2", "sheet_id": "sheet-2", "template_version": "v2"},
        ]
        expected = {
            site: {"db_target": 100, "db_sales_mtd": 50}
            for site in ("S1", "S2")
        }
        healthy = Repository(fail_persistence=False)
        assert await grile._run_claimed_grile_check(
            cast(GrileRepository, healthy),
            run_id=31,
            sheets=sheets,
            expected=expected,
            generations={"S1": 1, "S2": 1},
            triggered_by_sub="subject",
            tolerance=1,
            concurrency=2,
            lease_lost=asyncio.Event(),
        ) == 31
        assert healthy.finalized[0]["status"] == "completed"

        failing = Repository(fail_persistence=True)
        try:
            await grile._run_claimed_grile_check(
                cast(GrileRepository, failing),
                run_id=32,
                sheets=sheets,
                expected=expected,
                generations={"S1": 1, "S2": 1},
                triggered_by_sub="subject",
                tolerance=1,
                concurrency=2,
                lease_lost=asyncio.Event(),
            )
        except RuntimeError as exc:
            assert "persistence failure" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("persistence failure was not propagated")
        assert failing.persisting == 0
        assert failing.finalized == []

    asyncio.run(scenario())
    assert len(closed) >= 6
    assert len(closed) % 2 == 0
