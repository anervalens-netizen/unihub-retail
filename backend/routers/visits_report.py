from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import get_current_user
from models import VisitReportResponse, VisitReportRow
from routers.shared import build_scope_filter, normalize_filter

router = APIRouter(prefix="/api/visits-report", tags=["visits-report"])


@router.get("", response_model=VisitReportResponse)
async def get_visits_report(
    month: str = Query(...),
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> VisitReportResponse:
    clauses: list[str] = ["to_char(v.data_raport, 'YYYY-MM') = $1"]
    params: list[Any] = [month]

    if normalize_filter(firma):
        params.append(firma)
        clauses.append(f"v.firma = ${len(params)}")
    if normalize_filter(rm):
        params.append(rm)
        clauses.append(f"v.regional = ${len(params)}")
    if normalize_filter(asm):
        params.append(asm)
        clauses.append(f"v.asm = ${len(params)}")
    if normalize_filter(magazin):
        params.append(magazin)
        clauses.append(f"(v.site_code = ${len(params)} OR v.magazin = ${len(params)})")

    scope_sql, scope_params = build_scope_filter(user, base_alias="v", param_start=len(params) + 1)
    if scope_sql:
        clauses.append(scope_sql)
        params.extend(scope_params)

    where = " AND ".join(clauses)

    pool = await get_pool()
    async with pool.acquire() as conn:
        summary = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*)                              AS total_vizite,
                COUNT(DISTINCT COALESCE(v.site_code, v.magazin)) AS magazine_unice,
                ROUND(AVG(v.completion_pct), 1)       AS avg_completion
            FROM visits v
            WHERE {where}
            """,
            *params,
        )

        rows = await conn.fetch(
            f"""
            SELECT
                COALESCE(v.site_code, v.magazin, '')  AS magazin,
                v.asm,
                v.regional,
                v.firma,
                COUNT(*)                              AS nr_vizite,
                ROUND(AVG(v.completion_pct), 1)       AS avg_completion,
                ROUND(100.0 * SUM(CASE WHEN v.curatenie  THEN 1 ELSE 0 END) / COUNT(*), 1) AS curatenie_pct,
                ROUND(100.0 * SUM(CASE WHEN v.imagine    THEN 1 ELSE 0 END) / COUNT(*), 1) AS imagine_pct,
                ROUND(100.0 * SUM(CASE WHEN v.uniforma   THEN 1 ELSE 0 END) / COUNT(*), 1) AS uniforma_pct,
                ROUND(100.0 * SUM(CASE WHEN v.afise      THEN 1 ELSE 0 END) / COUNT(*), 1) AS afise_pct,
                ROUND(100.0 * SUM(CASE WHEN v.produse_promo THEN 1 ELSE 0 END) / COUNT(*), 1) AS produse_promo_pct,
                MAX(v.data_raport::TEXT)              AS last_visit
            FROM visits v
            WHERE {where}
            GROUP BY COALESCE(v.site_code, v.magazin, ''), v.asm, v.regional, v.firma
            ORDER BY nr_vizite DESC, magazin ASC
            """,
            *params,
        )

    total = summary["total_vizite"] if summary else 0
    mag_unice = summary["magazine_unice"] if summary else 0
    avg_c = float(summary["avg_completion"]) if summary and summary["avg_completion"] else 0.0

    report_rows = [
        VisitReportRow(
            magazin=r["magazin"],
            asm=r["asm"],
            regional=r["regional"],
            firma=r["firma"],
            nr_vizite=r["nr_vizite"],
            avg_completion=float(r["avg_completion"]) if r["avg_completion"] else 0.0,
            curatenie_pct=float(r["curatenie_pct"]) if r["curatenie_pct"] else 0.0,
            imagine_pct=float(r["imagine_pct"]) if r["imagine_pct"] else 0.0,
            uniforma_pct=float(r["uniforma_pct"]) if r["uniforma_pct"] else 0.0,
            afise_pct=float(r["afise_pct"]) if r["afise_pct"] else 0.0,
            produse_promo_pct=float(r["produse_promo_pct"]) if r["produse_promo_pct"] else 0.0,
            last_visit=r["last_visit"],
        )
        for r in rows
    ]

    return VisitReportResponse(
        month=month,
        total_vizite=total,
        magazine_unice=mag_unice,
        avg_completion=avg_c,
        rows=report_rows,
    )
