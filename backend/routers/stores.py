from __future__ import annotations

from fastapi import APIRouter, Depends

from db.connection import get_pool
from models import StoreOption, StoreTargetInput
from repositories.stores import StoresRepository
from routers.filters import clear_filter_options_cache
from services.stores import StoresService
from permissions import require_business_write_access

router = APIRouter(prefix="/api/stores", tags=["stores"])


async def get_stores_service() -> StoresService:
    pool = await get_pool()
    repo = StoresRepository(pool)
    return StoresService(repo, pool)


@router.get("", response_model=list[StoreOption])
async def list_stores(
    svc: StoresService = Depends(get_stores_service),
) -> list[StoreOption]:
    return await svc.get_active_stores()


@router.post("/targets")
async def save_targets(
    payload: list[StoreTargetInput],
    svc: StoresService = Depends(get_stores_service),
    _claims=Depends(require_business_write_access),
) -> dict[str, int]:
    inserted = await svc.save_targets([item.model_dump() for item in payload])
    clear_filter_options_cache()
    return {"inserted": inserted}
