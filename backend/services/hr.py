from __future__ import annotations

import datetime

from fastapi import HTTPException

from repositories.hr import HrRepository
from services.asm_salary import compute_asm_salary
from services.forecast import get_forecast_factor


class HrService:
    def __init__(self, repo: HrRepository):
        self.repo = repo

    async def create_leave_request(self, data: dict) -> dict:
        row = await self.repo.create_leave_request(data)
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

    async def list_leave_requests(self, status: str | None, agent_name: str | None) -> list[dict]:
        rows = await self.repo.list_leave_requests(status, agent_name)
        return [dict(r) for r in rows]

    async def get_agent_performance(self, agent_name: str) -> list[dict]:
        rows = await self.repo.get_agent_performance(agent_name)
        return [dict(r) for r in rows]

    async def get_asm_performance(self, month: str, regional: str | None) -> list[dict]:
        pg_rows = await self.repo.get_asm_performance_rows(month, regional)
        snapshot_rows = await self.repo.get_visits_snapshot(month)
        sqlite_map = {r["asm"]: dict(r) for r in snapshot_rows}

        async with self.repo.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)
        is_partial = forecast_factor > 1.001

        result = []
        for pg in pg_rows:
            asm = pg["asm"]
            sq = sqlite_map.get(asm, {})
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

    async def get_asm_performance_history(self, asm_name: str, months: int = 6) -> list[dict]:
        pg_rows = await self.repo.get_asm_history_rows(asm_name, months)
        snapshot_hist = await self.repo.get_visits_snapshot_history(asm_name, months)
        sqlite_map = {r["month"]: dict(r) for r in snapshot_hist}

        current_month = await self.repo.get_current_month_meta()
        if current_month and not current_month["is_final"] and current_month["last_sale_day"]:
            last_day = int(current_month["last_sale_day"])
            days_in_month = int(current_month["days_in_month"] or last_day)
            forecast_factor = days_in_month / last_day if last_day > 0 else 1.0
        else:
            forecast_factor = 1.0
        this_month = datetime.date.today().strftime("%Y-%m")

        result = []
        for pg in pg_rows:
            m = pg["import_month"]
            sq = sqlite_map.get(m, {})
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
                "target_value": float(r["target_value"] or 0),
                "total_sales": float(r["total_sales"] or 0),
                "focus_quantity": float(r["focus_quantity"] or 0),
                "total_quantity": float(r["total_quantity"] or 0),
            }
            for r in records
        ]
        async with self.repo.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)
        breakdown = compute_asm_salary(stores, forecast_factor)
        return {"asm": asm_name, "month": month, **breakdown}
