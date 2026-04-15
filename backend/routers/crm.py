from __future__ import annotations

import asyncio
import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import require_role
from services.forecast import get_forecast_factor

VISITS_DB_PATH = "/opt/Mobiup/unihub/data/visits/visits.db"


def _query_visits_by_store(year_month: str) -> dict[str, dict]:
    """
    Returnează {site_code: {nr_vizite, avg_completion}} pentru luna dată.
    Execuție sincronă — apelată din run_in_executor.
    """
    con = sqlite3.connect(VISITS_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(
        """
        SELECT
            magazin AS site_code,
            COUNT(*) AS nr_vizite,
            ROUND(AVG(completion_pct), 1) AS avg_completion
        FROM visits
        WHERE substr(data_raport, 1, 7) = ?
          AND magazin IS NOT NULL AND magazin != ''
        GROUP BY magazin
        """,
        (year_month,),
    )
    result = {r["site_code"]: dict(r) for r in cur.fetchall()}
    con.close()
    return result

router = APIRouter(prefix="/api/crm", tags=["crm"])

ALLOWED_ROLES = require_role("admin", "management")


async def calculate_scores_for_month(conn: Any, month: str) -> list[dict]:
    """
    Calculează scorul 0-100 per magazin pentru luna dată.
    Formula:
      - % target atins — previziune (max 40 pct)
      - trend previziune luna curentă vs realizat luna anterioară (max 30 pct)
      - KPI calitate: Bon2+ și Focus vs mediile lunii (max 20 pct)
      - vizite ASM: frecvență × calitate (max 10 pct)
    """
    y, m = map(int, month.split("-"))
    prev_month = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"

    forecast_factor = await get_forecast_factor(conn, month)

    loop = asyncio.get_running_loop()
    visit_map = await loop.run_in_executor(None, _query_visits_by_store, month)

    rows = await conn.fetch(
        """
        WITH current AS (
            SELECT
                ram.site_code,
                SUM(ram.total_sales) AS total_value,
                ROUND(SUM(ram.receipt_2plus_count) * 100.0 / NULLIF(SUM(ram.receipt_count), 0), 2) AS pct_bon2acc,
                ROUND(SUM(ram.focus_quantity) * 100.0 / NULLIF(SUM(ram.total_quantity), 0), 2) AS pct_focus,
                COALESCE(
                    (SELECT SUM(st.target_value)
                     FROM store_targets st
                     WHERE st.site_code = ram.site_code
                       AND st.import_month = $1),
                    0
                ) AS target_value
            FROM reporting_agent_month ram
            WHERE ram.import_month = $1
            GROUP BY ram.site_code
        ),
        prev AS (
            SELECT
                site_code,
                SUM(total_sales) AS total_value
            FROM reporting_agent_month
            WHERE import_month = $2
            GROUP BY site_code
        ),
        kpi_avgs AS (
            SELECT
                ROUND(SUM(receipt_2plus_count) * 100.0 / NULLIF(SUM(receipt_count), 0), 2) AS avg_bon2acc,
                ROUND(SUM(focus_quantity) * 100.0 / NULLIF(SUM(total_quantity), 0), 2) AS avg_focus
            FROM reporting_agent_month
            WHERE import_month = $1
        )
        SELECT
            c.site_code,
            c.total_value,
            c.pct_bon2acc,
            c.pct_focus,
            c.target_value,
            COALESCE(p.total_value, 0) AS prev_value,
            k.avg_bon2acc,
            k.avg_focus
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        CROSS JOIN kpi_avgs k
        """,
        month,
        prev_month,
    )

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

        # Componentă 1: % target (max 40) — bazat pe previziune
        target_pct = (forecast / target * 100) if target > 0 else 0
        c1 = min(target_pct / 100 * 40, 40)

        # Componentă 2: trend previziune vs realizat luna anterioară (max 30)
        if prev > 0:
            trend = (forecast - prev) / prev * 100
            c2 = max(0.0, min(30.0, (trend + 20) / 40 * 30))
        else:
            c2 = 15.0

        # Componentă 3: KPI calitate (max 20) — Bon2+ și Focus vs mediile lunii
        # Scaling midpoint: media = 5/10, dublu față de medie = 10/10
        bon2acc_score = min(pct_bon2acc / avg_bon2acc * 5, 10.0) if avg_bon2acc > 0 else 5.0
        focus_score = min(pct_focus / avg_focus * 5, 10.0) if avg_focus > 0 else 5.0
        c3 = round(bon2acc_score + focus_score, 1)

        # Componentă 4: vizite ASM (max 10)
        # Formula: min(nr_vizite × 5, 10) × (avg_completion / 100)
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


async def upsert_scores(conn: Any, month: str, scores: list[dict]) -> None:
    async with conn.transaction():
        for s in scores:
            await conn.execute(
                """
                INSERT INTO store_scores (site_code, score_month, score, breakdown)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (site_code, score_month)
                DO UPDATE SET score = EXCLUDED.score, breakdown = EXCLUDED.breakdown,
                              calculated_at = now()
                """,
                s["site_code"],
                month,
                s["score"],
                json.dumps(s["breakdown"]),
            )


async def get_store_alerts(conn: Any, month: str) -> list[dict]:
    """Magazine cu risc: scor < 40 sau scădere previziune > 20% față de luna anterioară."""
    y, m_int = map(int, month.split("-"))
    prev_month = f"{y}-{m_int - 1:02d}" if m_int > 1 else f"{y - 1}-12"

    forecast_factor = await get_forecast_factor(conn, month)

    rows = await conn.fetch(
        """
        WITH current AS (
            SELECT site_code, SUM(total_sales) AS val
            FROM reporting_agent_month WHERE import_month = $1
            GROUP BY site_code
        ),
        prev AS (
            SELECT site_code, SUM(total_sales) AS val
            FROM reporting_agent_month WHERE import_month = $2
            GROUP BY site_code
        ),
        scores AS (
            SELECT site_code, score
            FROM store_scores
            WHERE score_month = $1
        )
        SELECT
            c.site_code,
            COALESCE(s.score, -1) AS score,
            c.val AS current_val,
            COALESCE(p.val, 0) AS prev_val,
            COALESCE(st.regional, 'Necunoscut') AS regional,
            COALESCE(st.asm, 'Necunoscut') AS asm,
            COALESCE(st.locatie, c.site_code) AS locatie
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        LEFT JOIN scores s ON s.site_code = c.site_code
        LEFT JOIN stores st ON st.site_code = c.site_code
        """,
        month,
        prev_month,
    )

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


@router.get("/scores")
async def get_scores(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ss.site_code, ss.score, ss.breakdown, ss.calculated_at::text,
                   COALESCE(s.regional, 'Necunoscut') AS regional,
                   COALESCE(s.asm, 'Necunoscut') AS asm,
                   COALESCE(s.locatie, ss.site_code) AS locatie
            FROM store_scores ss
            LEFT JOIN stores s ON s.site_code = ss.site_code
            WHERE ss.score_month = $1
            ORDER BY s.regional NULLS LAST, s.asm NULLS LAST, ss.score ASC
            """,
            month,
        )
        result = []
        for r in rows:
            d = dict(r)
            if isinstance(d.get("breakdown"), str):
                d["breakdown"] = json.loads(d["breakdown"])
            result.append(d)
        return result


@router.post("/scores/recalculate")
async def recalculate_scores(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        scores = await calculate_scores_for_month(conn, month)
        await upsert_scores(conn, month, scores)
        return {"recalculated": len(scores), "month": month}


@router.get("/alerts")
async def get_alerts(
    month: str = Query(...),
    user: dict = Depends(ALLOWED_ROLES),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await get_store_alerts(conn, month)
