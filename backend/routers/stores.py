from __future__ import annotations

from fastapi import APIRouter

from db.connection import get_pool
from models import StoreOption, StoreTargetInput
from routers.filters import clear_filter_options_cache
from services.importer import upsert_store_targets

router = APIRouter(prefix="/api/stores", tags=["stores"])


@router.get("", response_model=list[StoreOption])
async def list_stores() -> list[StoreOption]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT site_code, locatie, firma, regional, asm
            FROM stores
            WHERE is_active = true
            ORDER BY locatie
            """,
        )
    return [StoreOption(**dict(row)) for row in rows]


@router.post("/targets")
async def save_targets(
    payload: list[StoreTargetInput],
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
