from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException

from business_clock import business_today
from repositories.hr import HrRepository
from services.asm_salary import asm_salary_rule_set_for_month, compute_asm_salary
from services.forecast import get_forecast_factor


def _coerce_leave_date(value: Any, *, field_name: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"{field_name} invalid") from exc
    raise HTTPException(status_code=422, detail=f"{field_name} invalid")


class HrService:
    def __init__(self, repo: HrRepository):
        self.repo = repo

    async def create_leave_request(self, data: dict) -> dict:
        normalized = dict(data)
        normalized["start_date"] = _coerce_leave_date(
            normalized.get("start_date"), field_name="start_date"
        )
        normalized["end_date"] = _coerce_leave_date(
            normalized.get("end_date"), field_name="end_date"
        )
        if normalized["start_date"] > normalized["end_date"]:
            raise HTTPException(
                status_code=422,
                detail="start_date must be on or before end_date",
            )
        row = await self.repo.create_leave_request(normalized)
        if not row:
            raise HTTPException(status_code=500, detail="Eroare la crearea cererii")
        return dict(row)

    async def update_leave_status(self, request_id: int, status: str) -> dict:
        if status not in ("approved", "rejected"):
            raise HTTPException(status_code=400, detail="Status invalid. Folosește 'approved' sau 'rejected'.")
        row = await self.repo.update_leave_status(request_id, status)
        if row is None:
            raise HTTPException(status_code=404, detail="Cerere negăsită")
        return dict(row)

    async def list_leave_requests(
        self,
        status: str | None,
        agent_name: str | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        rows, total = await self.repo.list_leave_requests(
            status,
            agent_name,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [
                {key: value for key, value in dict(row).items() if key != "total_count"}
                for row in rows
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    async def get_agent_performance(self, agent_name: str) -> list[dict]:
        rows = await self.repo.get_agent_performance(agent_name)
        return [dict(r) for r in rows]

    async def get_asm_performance(self, month: str, regional: str | None) -> list[dict]:
        pg_rows = await self.repo.get_asm_performance_rows(month, regional)
        snapshot_rows = await self.repo.get_visits_snapshot(month)
        visits_map = {r["asm"]: dict(r) for r in snapshot_rows}

        async with self.repo.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)
        is_partial = forecast_factor > 1.001

        result = []
        for pg in pg_rows:
            asm = pg["asm"]
            sq = visits_map.get(asm, {})
            total_sales = float(pg["total_sales"] or 0)
            total_target = float(pg["total_target"] or 0)
            forecast_sales = total_sales * forecast_factor
            result.append({
                "asm": asm,
                "regional": pg["regional"],
                "total_sales": total_sales,
                "total_target": total_target,
                "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
                "forecast_sales": forecast_sales,
                "forecast_target_pct": round(forecast_sales / total_target * 100, 1) if total_target > 0 else None,
                "is_forecast": is_partial,
                "active_stores": pg["active_stores"],
                "active_agents": pg["active_agents"],
                "pct_bon2acc": float(pg["pct_bon2acc"] or 0),
                "pct_focus": float(pg["pct_focus"] or 0),
                "total_visits": sq.get("total_visits", 0),
                "avg_completion": sq.get("avg_completion"),
                "avg_duration": sq.get("avg_duration"),
                "distinct_stores_visited": sq.get("distinct_stores", 0),
                "checklist_score": sq.get("checklist_score"),
                "approved_pct": sq.get("approved_pct"),
            })
        return result

    async def get_manager_overview(self, month: str) -> list[dict]:
        """Construiește overview-ul managerial fără evaluarea duplicată de vânzări."""
        manager_rows = await self.repo.get_manager_overview_rows(month)
        store_rows = await self.repo.get_manager_store_overview_rows(month)
        snapshot_rows = await self.repo.get_visits_snapshot(month)

        stores_by_manager: dict[str, list[dict]] = {}
        for row in store_rows:
            manager = str(row["asm"])
            active_agents = int(row["active_agents"] or 0)
            previous_active_agents = int(row["previous_active_agents"] or 0)
            stores_by_manager.setdefault(manager, []).append({
                "site_code": row["site_code"],
                "locatie": row["locatie"],
                "firma": row["firma"],
                "active_agents": active_agents,
                "previous_active_agents": previous_active_agents,
                "agent_delta": active_agents - previous_active_agents,
            })

        visits_by_manager = {str(row["asm"]): dict(row) for row in snapshot_rows}
        result: list[dict] = []
        for row in manager_rows:
            manager = str(row["asm"])
            active_stores = int(row["active_stores"] or 0)
            active_agents = int(row["active_agents"] or 0)
            previous_active_agents = int(row["previous_active_agents"] or 0)
            visits = visits_by_manager.get(manager)
            visited_stores = int(visits.get("distinct_stores") or 0) if visits else 0
            result.append({
                "manager": manager,
                "regional": row["regional"],
                "month": month,
                "reporting_available": bool(row["reporting_available"]),
                "active_stores": active_stores,
                "active_agents": active_agents,
                "previous_active_agents": previous_active_agents,
                "agent_delta": active_agents - previous_active_agents,
                "agents_added": int(row["agents_added"] or 0),
                "agents_left": int(row["agents_left"] or 0),
                "stores_without_agents": int(row["stores_without_agents"] or 0),
                "agents_per_store": round(active_agents / active_stores, 1) if active_stores else 0,
                "visits_available": visits is not None,
                "total_visits": int(visits.get("total_visits") or 0) if visits else 0,
                "visited_stores": visited_stores,
                "visit_coverage_pct": round(visited_stores / active_stores * 100, 1) if visits and active_stores else None,
                "avg_visit_completion": float(visits["avg_completion"]) if visits and visits.get("avg_completion") is not None else None,
                "checklist_score": float(visits["checklist_score"]) if visits and visits.get("checklist_score") is not None else None,
                "approved_pct": float(visits["approved_pct"]) if visits and visits.get("approved_pct") is not None else None,
                "stores": stores_by_manager.get(manager, []),
            })
        return result

    async def get_asm_performance_history(self, asm_name: str, months: int = 6) -> list[dict]:
        pg_rows = await self.repo.get_asm_history_rows(asm_name, months)
        snapshot_hist = await self.repo.get_visits_snapshot_history(asm_name, months)
        visits_map = {r["month"]: dict(r) for r in snapshot_hist}

        this_month = business_today().strftime("%Y-%m")
        async with self.repo.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, this_month)

        result = []
        for pg in pg_rows:
            m = pg["import_month"]
            sq = visits_map.get(m, {})
            total_sales = float(pg["total_sales"] or 0)
            total_target = float(pg["total_target"] or 0)
            is_current = m == this_month and forecast_factor > 1.001
            forecast_sales = total_sales * forecast_factor if is_current else total_sales
            forecast_target_pct = round(forecast_sales / total_target * 100, 1) if total_target > 0 else None
            result.append({
                "month": m,
                "total_sales": total_sales,
                "total_target": total_target,
                "target_pct": round(total_sales / total_target * 100, 1) if total_target > 0 else None,
                "forecast_sales": forecast_sales,
                "forecast_target_pct": forecast_target_pct,
                "is_forecast": is_current,
                "active_stores": pg["active_stores"],
                "total_visits": sq.get("total_visits", 0),
                "avg_completion": sq.get("avg_completion"),
                "avg_duration": sq.get("avg_duration"),
            })
        return result

    async def get_asm_salary(self, asm_name: str, month: str) -> dict:
        """Defalcarea salariului ASM după grila de comisionare.

        Combină datele pe magazin (repo) cu factorul de prognoză la final de
        lună și deleagă calculul pur către `services.asm_salary`. Pentru luna
        curentă parțială comisioanele se bazează pe procentul prognozat; pentru
        lunile încheiate pe valorile actuale.
        """
        records = await self.repo.get_asm_store_breakdown(asm_name, month)
        stores = [
            {
                "site_code": r["site_code"],
                "locatie": r["locatie"],
                "firma": r["firma"],
                "target_value": r["target_value"] or 0,
                "total_sales": r["total_sales"] or 0,
                "focus_quantity": r["focus_quantity"] or 0,
                "total_quantity": r["total_quantity"] or 0,
            }
            for r in records
        ]
        async with self.repo.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)
        breakdown = compute_asm_salary(
            stores,
            forecast_factor,
            rules=asm_salary_rule_set_for_month(month),
        )
        return {"asm": asm_name, "month": month, **breakdown}
