from __future__ import annotations

from fastapi import APIRouter, Depends

from db.connection import get_pool
from dependencies import get_current_user, require_role
from models import StoreOption, StoreTargetInput
from routers.filters import clear_filter_options_cache
from routers.shared import build_scope_filter
from services.importer import upsert_store_targets

router = APIRouter(prefix="/api/stores", tags=["stores"])


@router.get("", response_model=list[StoreOption])
async def list_stores(user: dict = Depends(get_current_user)) -> list[StoreOption]:
    scope_sql, scope_params = build_scope_filter(user, base_alias="s", param_start=1)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT site_code, locatie, firma, regional, asm
            FROM stores s
            WHERE is_active = true
              {f"AND {scope_sql}" if scope_sql else ""}
            ORDER BY locatie
            """,
            *scope_params,
        )
    return [StoreOption(**dict(row)) for row in rows]


@router.post("/targets")
async def save_targets(
    payload: list[StoreTargetInput],
    user: dict = Depends(require_role("admin")),
) -> dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        inserted = await upsert_store_targets(
            conn,
            [item.model_dump() for item in payload],
            source_file="manual-api",
        )
    clear_filter_options_cache()
    return {"inserted": inserted}
