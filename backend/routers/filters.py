from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import get_current_user
from models import FilterOptions
from services.filters import build_scope_filter, normalize_filter

router = APIRouter(prefix="/api/filters", tags=["filters"])

# Cache: (month, user_role, user_id) -> (result, timestamp)
_filter_options_cache: dict[tuple[str, str, int], tuple[FilterOptions, float]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached_filter_options(month: str, user: dict[str, Any]) -> FilterOptions | None:
    key = (month, user["role"], user["id"])
    if key in _filter_options_cache:
        result, timestamp = _filter_options_cache[key]
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return result
    return None


def _set_cached_filter_options(month: str, user: dict[str, Any], result: FilterOptions):
    key = (month, user["role"], user["id"])
    _filter_options_cache[key] = (result, time.time())


def clear_filter_options_cache() -> None:
    _filter_options_cache.clear()


@router.get("/options", response_model=FilterOptions)
async def get_filter_options(
    month: str = Query(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> FilterOptions:
    cached = _get_cached_filter_options(month, user)
    if cached is not None:
        return cached

    scope_sql, scope_params = build_scope_filter(user, base_alias="agg", param_start=2)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT agg.firma, agg.regional, agg.asm, agg.site_code, agg.locatie, agg.agent
            FROM reporting_agent_month agg
            WHERE agg.import_month = $1
              {f"AND {scope_sql}" if scope_sql else ""}
            ORDER BY agg.firma, agg.regional, agg.asm, agg.locatie, agg.agent
            """,
            month,
            *scope_params,
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
    _set_cached_filter_options(month, user, result)
    return result


@router.get("/months", response_model=list[str])
async def get_available_months(
    user: dict[str, Any] = Depends(get_current_user),
) -> list[str]:
    scope_sql, scope_params = build_scope_filter(user, base_alias="agg", param_start=1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT snap.import_month
            FROM import_snapshots snap
            WHERE snap.status = 'completed'
              AND EXISTS (
                  SELECT 1
                  FROM reporting_agent_month agg
                  WHERE agg.import_month = snap.import_month
                    {f"AND {scope_sql}" if scope_sql else ""}
              )
            ORDER BY snap.import_month DESC
            """,
            *scope_params,
        )
    return [row["import_month"] for row in rows]
