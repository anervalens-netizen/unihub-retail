from __future__ import annotations

import json
from typing import Any

import asyncpg

from repositories.crm import CrmRepository
from services.forecast import get_forecast_factor


async def _query_visits_by_store_postgres(
    conn: asyncpg.Connection,
    year_month: str,
) -> dict[str, dict[str, Any]]:
    records = await conn.fetch(
        """
        SELECT
            magazin AS site_code,
            COUNT(*)::INT AS nr_vizite,
            ROUND(AVG(completion_pct)::NUMERIC, 1)::FLOAT AS avg_completion
        FROM fieldops_visits
        WHERE to_char(data_raport, 'YYYY-MM') = $1
          AND magazin IS NOT NULL AND magazin <> ''
        GROUP BY magazin
        """,
        year_month,
    )
    return {record["site_code"]: dict(record) for record in records}


class CrmService:
    def __init__(self, repo: CrmRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def calculate_scores_for_month(self, month: str) -> list[dict[str, Any]]:
        y, m = map(int, month.split("-"))
        prev_month = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"

        async with self.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)
            visit_map = await _query_visits_by_store_postgres(conn, month)

        rows = await self.repo.get_kpi_data_for_month(month, prev_month)

        scores = []
        for row in rows:
            total = float(row["total_value"] or 0)
            target = float(row["target_value"] or 0)
            prev = float(row["prev_value"] or 0)
            pct_bon2acc = float(row["pct_bon2acc"] or 0)
            pct_focus = float(row["pct_focus"] or 0)
            avg_bon2acc = float(row["avg_bon2acc"] or 0)
            avg_focus = float(row["avg_focus"] or 0)
            forecast = total * forecast_factor

            target_pct = (forecast / target * 100) if target > 0 else 0
            c1 = min(target_pct / 100 * 40, 40)

            if prev > 0:
                trend = (forecast - prev) / prev * 100
                c2 = max(0.0, min(30.0, (trend + 20) / 40 * 30))
            else:
                c2 = 15.0

            bon2acc_score = min(pct_bon2acc / avg_bon2acc * 5, 10.0) if avg_bon2acc > 0 else 5.0
            focus_score = min(pct_focus / avg_focus * 5, 10.0) if avg_focus > 0 else 5.0
            c3 = round(bon2acc_score + focus_score, 1)

            vdata = visit_map.get(row["site_code"], {})
            nr_vizite = int(vdata.get("nr_vizite", 0) or 0)
            avg_completion = float(vdata.get("avg_completion", 0) or 0)
            freq_score = min(nr_vizite * 5, 10)
            c4 = round(freq_score * (avg_completion / 100), 1)

            score = round(c1 + c2 + c3 + c4)
            scores.append({
                "site_code": row["site_code"],
                "score": score,
                "breakdown": {
                    "target_pct": round(c1, 1),
                    "trend_pct": round(c2, 1),
                    "kpi_pct": c3,
                    "kpi_bon2acc_score": round(bon2acc_score, 1),
                    "kpi_focus_score": round(focus_score, 1),
                    "visits_pct": c4,
                    "target_attainment": round(target_pct, 1),
                    "forecast_factor": round(forecast_factor, 4),
                    "kpi_bon2acc": round(pct_bon2acc, 1),
                    "kpi_focus": round(pct_focus, 1),
                    "kpi_bon2acc_avg": round(avg_bon2acc, 1),
                    "kpi_focus_avg": round(avg_focus, 1),
                    "nr_vizite": nr_vizite,
                    "avg_completion": round(avg_completion, 1),
                },
            })

        return scores

    async def recalculate_scores(self, month: str) -> int:
        scores = await self.calculate_scores_for_month(month)
        await self.repo.upsert_scores(month, scores)
        return len(scores)

    async def get_alerts(self, month: str) -> list[dict[str, Any]]:
        y, m_int = map(int, month.split("-"))
        prev_month = f"{y}-{m_int - 1:02d}" if m_int > 1 else f"{y - 1}-12"

        async with self.pool.acquire() as conn:
            forecast_factor = await get_forecast_factor(conn, month)

        rows = await self.repo.get_alerts_data(month, prev_month)

        alerts = []
        for row in rows:
            reasons = []
            score = row["score"]
            current_val = float(row["current_val"] or 0)
            prev_val = float(row["prev_val"] or 0)
            forecast_val = current_val * forecast_factor

            if score >= 0 and score < 40:
                reasons.append(f"Scor scăzut ({score}/100)")

            if prev_val > 0:
                trend = (forecast_val - prev_val) / prev_val * 100
                if trend < -20:
                    reasons.append(f"Scădere previzionată {abs(round(trend))}% față de luna anterioară")

            if reasons:
                alerts.append({
                    "site_code": row["site_code"],
                    "score": score,
                    "reasons": reasons,
                    "regional": row["regional"],
                    "asm": row["asm"],
                    "locatie": row["locatie"],
                })

        return sorted(alerts, key=lambda x: x["score"])

    async def get_scores(self, month: str) -> list[dict[str, Any]]:
        rows = await self.repo.get_scores(month)
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("breakdown"), str):
                d["breakdown"] = json.loads(d["breakdown"])
            result.append(d)
        return result
