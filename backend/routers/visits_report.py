from __future__ import annotations

import asyncio
import mimetypes
import os
import sqlite3
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from db.connection import get_pool
from dependencies import get_current_user
from models import (
    AsmGroup,
    VisitDayGroup,
    VisitDetail,
    VisitMonthGroup,
    VisitReportResponse,
    VisitReportRow,
    VisitSummaryItem,
    VisitTreeResponse,
)
from routers.shared import normalize_filter

VISITS_DB = Path(os.getenv("VISITS_DB_PATH", "/opt/Mobiup/Platforma-Mobiup/db/visit_reports.db"))
IMAGES_DIR = Path(os.getenv("VISITS_IMAGES_DIR", "/opt/Mobiup/Platforma-Mobiup/local-data/visit-reports/images"))

router = APIRouter(prefix="/api/visits-report", tags=["visits-report"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _build_clauses(
    filters: dict[str, str | None],
    tl_stores: list[str] | None,
    month: str | None = None,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = ["status != 'draft'"]
    params: list[Any] = []

    if month:
        clauses.append("strftime('%Y-%m', data_raport) = ?")
        params.append(month)
    if filters.get("firma"):
        clauses.append("firma = ?")
        params.append(filters["firma"])
    if filters.get("rm"):
        clauses.append("regional = ?")
        params.append(filters["rm"])
    if filters.get("asm"):
        clauses.append("asm = ?")
        params.append(filters["asm"])
    if filters.get("magazin"):
        clauses.append("magazin = ?")
        params.append(filters["magazin"])
    if tl_stores is not None:
        if not tl_stores:
            clauses.append("1=0")
        else:
            placeholders = ",".join("?" * len(tl_stores))
            clauses.append(f"magazin IN ({placeholders})")
            params.extend(tl_stores)

    return clauses, params


def _photo_filenames(visit_id: str) -> list[str]:
    folder = IMAGES_DIR / visit_id
    if not folder.exists():
        return []
    return sorted(p.name for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})


# ── summary endpoint (existing) ───────────────────────────────────────────────

def _query_sqlite(month: str, filters: dict[str, str | None], tl_stores: list[str] | None) -> dict:
    if not VISITS_DB.exists():
        return {"total": 0, "magazine_unice": 0, "avg_completion": 0.0, "rows": []}

    clauses, params = _build_clauses(filters, tl_stores, month=month)
    where = " AND ".join(clauses)

    con = sqlite3.connect(f"file:{VISITS_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        summary = cur.execute(
            f"""
            SELECT COUNT(*) AS total_vizite,
                   COUNT(DISTINCT magazin) AS magazine_unice,
                   ROUND(AVG(completion_pct), 1) AS avg_completion
            FROM visits WHERE {where}
            """,
            params,
        ).fetchone()

        rows = cur.execute(
            f"""
            SELECT magazin, asm, regional, firma,
                   COUNT(*) AS nr_vizite,
                   ROUND(AVG(completion_pct), 1) AS avg_completion,
                   ROUND(100.0 * SUM(curatenie)     / COUNT(*), 1) AS curatenie_pct,
                   ROUND(100.0 * SUM(imagine)       / COUNT(*), 1) AS imagine_pct,
                   ROUND(100.0 * SUM(uniforma)      / COUNT(*), 1) AS uniforma_pct,
                   ROUND(100.0 * SUM(afise)         / COUNT(*), 1) AS afise_pct,
                   ROUND(100.0 * SUM(produse_promo) / COUNT(*), 1) AS produse_promo_pct,
                   MAX(data_raport) AS last_visit
            FROM visits WHERE {where}
            GROUP BY magazin, asm, regional, firma
            ORDER BY nr_vizite DESC, magazin ASC
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    return {
        "total": summary["total_vizite"] if summary else 0,
        "magazine_unice": summary["magazine_unice"] if summary else 0,
        "avg_completion": float(summary["avg_completion"]) if summary and summary["avg_completion"] else 0.0,
        "rows": [dict(r) for r in rows],
    }


@router.get("", response_model=VisitReportResponse)
async def get_visits_report(
    month: str = Query(...),
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> VisitReportResponse:
    if not VISITS_DB.exists():
        raise HTTPException(status_code=503, detail="Baza de date vizite nu este disponibila.")

    tl_stores = await _get_tl_stores(user)
    filters = {
        "firma": normalize_filter(firma),
        "rm": normalize_filter(rm),
        "asm": normalize_filter(asm),
        "magazin": normalize_filter(magazin),
    }

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, partial(_query_sqlite, month, filters, tl_stores))

    report_rows = [
        VisitReportRow(
            magazin=r["magazin"] or "",
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
        for r in result["rows"]
    ]

    return VisitReportResponse(
        month=month,
        total_vizite=result["total"],
        magazine_unice=result["magazine_unice"],
        avg_completion=result["avg_completion"],
        rows=report_rows,
    )


# ── tree endpoint ─────────────────────────────────────────────────────────────

def _query_tree(filters: dict[str, str | None], tl_stores: list[str] | None) -> list[dict]:
    if not VISITS_DB.exists():
        return []

    clauses, params = _build_clauses(filters, tl_stores)
    where = " AND ".join(clauses)

    con = sqlite3.connect(f"file:{VISITS_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            f"""
            SELECT id, data_raport, ora_trimitere, asm, magazin, firma,
                   completion_pct, foto1, foto2, foto3, foto4
            FROM visits WHERE {where}
            ORDER BY asm ASC, data_raport DESC, ora_trimitere DESC
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    return [dict(r) for r in rows]


@router.get("/tree", response_model=VisitTreeResponse)
async def get_visits_tree(
    firma: str | None = None,
    rm: str | None = None,
    asm: str | None = None,
    magazin: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> VisitTreeResponse:
    if not VISITS_DB.exists():
        raise HTTPException(status_code=503, detail="Baza de date vizite nu este disponibila.")

    tl_stores = await _get_tl_stores(user)
    filters = {
        "firma": normalize_filter(firma),
        "rm": normalize_filter(rm),
        "asm": normalize_filter(asm),
        "magazin": normalize_filter(magazin),
    }

    loop = asyncio.get_event_loop()
    rows = await loop.run_in_executor(None, partial(_query_tree, filters, tl_stores))

    # Group: asm → month → day → visits
    asm_map: dict[str, dict[str, dict[str, list[VisitSummaryItem]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for r in rows:
        asm_key = r["asm"] or "—"
        month_key = r["data_raport"][:7] if r["data_raport"] else "—"
        day_key = r["data_raport"] or "—"
        has_photos = any(r[f"foto{i}"] for i in range(1, 5))
        asm_map[asm_key][month_key][day_key].append(
            VisitSummaryItem(
                id=r["id"],
                magazin=r["magazin"] or "",
                ora=r["ora_trimitere"],
                completion_pct=r["completion_pct"],
                firma=r["firma"],
                has_photos=has_photos,
            )
        )

    asms: list[AsmGroup] = []
    for asm_key in sorted(asm_map):
        months: list[VisitMonthGroup] = []
        for month_key in sorted(asm_map[asm_key], reverse=True):
            days: list[VisitDayGroup] = []
            for day_key in sorted(asm_map[asm_key][month_key], reverse=True):
                visits = asm_map[asm_key][month_key][day_key]
                days.append(VisitDayGroup(date=day_key, nr_vizite=len(visits), visits=visits))
            total_month = sum(d.nr_vizite for d in days)
            months.append(VisitMonthGroup(month=month_key, nr_vizite=total_month, days=days))
        total_asm = sum(m.nr_vizite for m in months)
        asms.append(AsmGroup(asm=asm_key, nr_vizite=total_asm, months=months))

    return VisitTreeResponse(asms=asms)


# ── single visit detail ───────────────────────────────────────────────────────

def _query_visit(visit_id: str) -> dict | None:
    if not VISITS_DB.exists():
        return None
    con = sqlite3.connect(f"file:{VISITS_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT * FROM visits WHERE id = ?", [visit_id]).fetchone()
    finally:
        con.close()
    return dict(row) if row else None


@router.get("/visit/{visit_id}", response_model=VisitDetail)
async def get_visit_detail(
    visit_id: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> VisitDetail:
    loop = asyncio.get_event_loop()
    row = await loop.run_in_executor(None, partial(_query_visit, visit_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Vizita nu a fost gasita.")

    photos = _photo_filenames(visit_id)

    def _b(v: Any) -> bool:
        return bool(v) if v is not None else False

    return VisitDetail(
        id=row["id"],
        data_raport=row["data_raport"],
        ora_trimitere=row["ora_trimitere"],
        firma=row["firma"],
        regional=row["regional"],
        asm=row["asm"],
        magazin=row["magazin"],
        durata_vizita_ore=row["durata_vizita_ore"],
        curatenie=_b(row["curatenie"]),
        imagine=_b(row["imagine"]),
        uniforma=_b(row["uniforma"]),
        afise=_b(row["afise"]),
        produse_promo=_b(row["produse_promo"]),
        tpu=row["tpu"],
        sticla=row["sticla"],
        altele=row["altele"],
        avizat=_b(row["avizat"]),
        charisma=row["charisma"],
        casa=row["casa"],
        incarcari_epay=row["incarcari_epay"],
        incarcari_charisma=row["incarcari_charisma"],
        agent1_nume=row["agent1_nume"],
        agent1_perf=row["agent1_perf"],
        agent1_doi_pe_bon=row["agent1_doi_pe_bon"],
        agent1_focus=row["agent1_focus"],
        agent1_analiza=row["agent1_analiza"],
        agent1_plan=row["agent1_plan"],
        agent2_nume=row["agent2_nume"],
        agent2_perf=row["agent2_perf"],
        agent2_doi_pe_bon=row["agent2_doi_pe_bon"],
        agent2_focus=row["agent2_focus"],
        agent2_analiza=row["agent2_analiza"],
        agent2_plan=row["agent2_plan"],
        photos=photos,
        completion_pct=row["completion_pct"],
        notes=row["notes"],
    )


# ── photo serving ─────────────────────────────────────────────────────────────

@router.get("/photo/{visit_id}/{filename}")
async def get_visit_photo(
    visit_id: str,
    filename: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> FileResponse:
    # Sanitize: no path traversal
    if "/" in filename or "\\" in filename or ".." in visit_id:
        raise HTTPException(status_code=400, detail="Invalid path.")

    photo_path = IMAGES_DIR / visit_id / filename
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Poza nu a fost gasita.")

    mime, _ = mimetypes.guess_type(filename)
    return FileResponse(photo_path, media_type=mime or "image/jpeg")


# ── shared helper ─────────────────────────────────────────────────────────────

async def _get_tl_stores(user: dict[str, Any]) -> list[str] | None:
    if user["role"] != "tl":
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch(
            "SELECT site_code FROM tl_store_assignments WHERE user_id = $1",
            user["id"],
        )
    return [r["site_code"] for r in records]
