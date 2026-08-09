from __future__ import annotations

from fastapi import APIRouter, Depends

from composition import build_stores_service
from auth import AuthClaims
from models import (
    StoreActivityChangeRequest,
    StoreActivityChangeResponse,
    StoreOption,
    StoreTargetInput,
    StoreTargetsSaveResponse,
)
from services.filter_options import FilterOptionsService
from services.stores import StoresService
from permissions import require_business_write_access, require_import_admin
from rate_limits import BUSINESS_WRITE_LIMIT, rate_limit

router = APIRouter(prefix="/api/stores", tags=["stores"])


get_stores_service = build_stores_service


@router.get("", response_model=list[StoreOption])
async def list_stores(
    svc: StoresService = Depends(get_stores_service),
) -> list[StoreOption]:
    return await svc.get_active_stores()


@router.post("/targets", response_model=StoreTargetsSaveResponse)
async def save_targets(
    payload: list[StoreTargetInput],
    _claims=Depends(require_business_write_access),
    _rate_limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: StoresService = Depends(get_stores_service),
) -> StoreTargetsSaveResponse:
    inserted = await svc.save_targets([item.model_dump() for item in payload])
    FilterOptionsService.clear_cache()
    return StoreTargetsSaveResponse(inserted=inserted)


@router.post(
    "/{site_code}/activity",
    response_model=StoreActivityChangeResponse,
)
async def change_store_activity(
    site_code: str,
    payload: StoreActivityChangeRequest,
    claims: AuthClaims = Depends(require_import_admin),
    _rate_limit: None = Depends(rate_limit(BUSINESS_WRITE_LIMIT)),
    svc: StoresService = Depends(get_stores_service),
) -> StoreActivityChangeResponse:
    result = await svc.change_activity(
        site_code=site_code.strip(),
        expected_is_active=payload.expected_is_active,
        new_is_active=payload.is_active,
        reason=payload.reason,
        requested_by_sub=claims.sub,
    )
    FilterOptionsService.clear_cache()
    return result
