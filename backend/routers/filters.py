from __future__ import annotations

import time

from fastapi import APIRouter, Query

from db.connection import get_pool
from models import FilterOptions
from services.filters import normalize_filter

router = APIRouter(prefix="/api/filters", tags=["filters"])

_filter_options_cache: dict[str, tuple[FilterOptions, float]] = {}
_CACHE_TTL_SECONDS = 300


def _get_cached_filter_options(month: str) -> FilterOptions | None:
    if month in _filter_options_cache:
        result, timestamp = _filter_options_cache[month]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return result
    return None


def _set_cached_filter_options(month: str, result: FilterOptions) -> None:
    _filter_options_cache[month] = (result, time.time())


def clear_filter_options_cache() -> None:
    _filter_options_cache.clear()


@router.get("/options", response_model=FilterOptions)
async def get_filter_options(
    month: str = Query(...),
) -> FilterOptions:
    cached = _get_cached_filter_options(month)
    if cached is not None:
        return cached

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT agg.firma, agg.regional, agg.asm, agg.site_code, agg.locatie, agg.agent
            FROM reporting_agent_month agg
            WHERE agg.import_month = $1
            ORDER BY agg.firma, agg.regional, agg.asm, agg.locatie, agg.agent
            """,
            month,
        )

    firme = sorted({row["firma"] for row in rows if normalize_filter(row["firma"])})
    regionali = sorted({row["regional"] for row in rows if normalize_filter(row["regional"])})
    asmi = sorted({row["asm"] for row in rows if normalize_filter(row["asm"])})
    magazine = list(
        {
            item["site_code"]: {
                "site_code": item["site_code"],
                "locatie": item["locatie"],
                "firma": item["firma"],
                "regional": item["regional"],
                "asm": item["asm"],
            }
            for item in [dict(row) for row in rows]
        }.values()
    )
    magazine.sort(key=lambda item: item["locatie"])
    agenti = list(
        {
            (item["agent"], item["site_code"]): {
                "agent": item["agent"],
                "site_code": item["site_code"],
                "locatie": item["locatie"],
                "firma": item["firma"],
                "regional": item["regional"],
                "asm": item["asm"],
            }
            for item in [dict(row) for row in rows]
            if normalize_filter(item["agent"])
        }.values()
    )
    agenti.sort(key=lambda item: (item["agent"], item["locatie"]))
    result = FilterOptions(
        firme=firme,
        regionali=regionali,
        asmi=asmi,
        magazine=magazine,
        agenti=agenti,
    )
    _set_cached_filter_options(month, result)
    return result


@router.get("/months", response_model=list[str])
async def get_available_months() -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT snap.import_month
            FROM import_snapshots snap
            WHERE snap.status = 'completed'
            ORDER BY snap.import_month DESC
            """,
        )
    return [row["import_month"] for row in rows]
