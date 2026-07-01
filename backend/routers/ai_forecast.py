from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from db.connection import get_pool
from models import AiForecastResponse
from repositories.ai_forecast import AiForecastRepository
from services.ai_forecast import AiForecastService

router = APIRouter(prefix="/api/ai-forecast", tags=["ai-forecast"])


async def get_ai_forecast_service() -> AiForecastService:
    pool = await get_pool()
    return AiForecastService(AiForecastRepository(pool))


@router.get("/current", response_model=AiForecastResponse)
async def get_current_ai_forecast(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    svc: AiForecastService = Depends(get_ai_forecast_service),
) -> AiForecastResponse:
    response = await svc.get_current(
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Nu exista forecast AI pentru luna selectata")
    return response
