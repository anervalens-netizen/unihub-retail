from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import require_role

router = APIRouter(prefix="/api/crm", tags=["crm"])

ALLOWED_ROLES = require_role("admin", "management")


async def calculate_scores_for_month(conn: Any, month: str) -> list[dict]:
    """
    Calculează scorul 0-100 per magazin pentru luna dată.
    Formula:
      - % target atins (max 40 pct)
      - trend față de luna anterioară (max 30 pct)
      - zile active (max 20 pct)
      - vizite (max 10 pct) — 0 în v1
    """
    y, m = map(int, month.split("-"))
    prev_month = f"{y}-{m - 1:02d}" if m > 1 else f"{y - 1}-12"

    rows = await conn.fetch(
        """
        WITH current AS (
            SELECT
                ram.site_code,
                SUM(ram.total_sales) AS total_value,
                SUM(ram.working_days) AS active_days,
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
        )
        SELECT
            c.site_code,
            c.total_value,
            c.active_days,
            c.target_value,
            COALESCE(p.total_value, 0) AS prev_value
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        """,
        month,
        prev_month,
    )

    scores = []
    for row in rows:
        total = float(row["total_value"] or 0)
        target = float(row["target_value"] or 0)
        prev = float(row["prev_value"] or 0)
        active_days = int(row["active_days"] or 0)

        # Componentă 1: % target (max 40)
        target_pct = (total / target * 100) if target > 0 else 0
        c1 = min(target_pct / 100 * 40, 40)

        # Componentă 2: trend față de luna anterioară (max 30)
        if prev > 0:
            trend = (total - prev) / prev * 100
            c2 = max(0.0, min(30.0, (trend + 20) / 40 * 30))
        else:
            c2 = 15.0

        # Componentă 3: zile active (max 20) — 20 zile = maxim
        c3 = min(active_days / 20 * 20, 20)

        # Componentă 4: vizite — 0 (SQLite, ignorat în v1)
        c4 = 0.0

        score = round(c1 + c2 + c3 + c4)
        scores.append({
            "site_code": row["site_code"],
            "score": score,
            "breakdown": {
                "target_pct": round(c1, 1),
                "trend_pct": round(c2, 1),
                "active_days_pct": round(c3, 1),
                "visits_pct": round(c4, 1),
                "target_attainment": round(target_pct, 1),
            },
        })

    return scores


async def upsert_scores(conn: Any, month: str, scores: list[dict]) -> None:
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
    """Magazine cu risc: scor < 40 sau scădere > 20%."""
    y, m_int = map(int, month.split("-"))
    prev_month = f"{y}-{m_int - 1:02d}" if m_int > 1 else f"{y - 1}-12"

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
            COALESCE(p.val, 0) AS prev_val
        FROM current c
        LEFT JOIN prev p ON p.site_code = c.site_code
        LEFT JOIN scores s ON s.site_code = c.site_code
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

        if score >= 0 and score < 40:
            reasons.append(f"Scor scăzut ({score}/100)")

        if prev_val > 0:
            trend = (current_val - prev_val) / prev_val * 100
            if trend < -20:
                reasons.append(f"Scădere {abs(round(trend))}% față de luna anterioară")

        if reasons:
            alerts.append({
                "site_code": row["site_code"],
                "score": score,
                "reasons": reasons,
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
            "SELECT site_code, score, breakdown, calculated_at::text FROM store_scores WHERE score_month = $1 ORDER BY score",
            month,
        )
        return [dict(r) for r in rows]


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
