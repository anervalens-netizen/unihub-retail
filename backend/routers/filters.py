from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from composition import build_filters_service
from schemas.common import MonthStr
from models import FilterOptions
from services.filter_options import FilterOptionsService

router = APIRouter(prefix="/api/filters", tags=["filters"])

get_filters_service = build_filters_service


def clear_filter_options_cache() -> None:
    FilterOptionsService.clear_cache()


@router.get("/options", response_model=FilterOptions)
async def get_filter_options(
    month: MonthStr,
    svc: FilterOptionsService = Depends(get_filters_service),
) -> FilterOptions:
    return await svc.get_options(month)


@router.get("/months", response_model=list[str])
async def get_available_months(
    svc: FilterOptionsService = Depends(get_filters_service),
) -> list[str]:
    return await svc.get_available_months()
