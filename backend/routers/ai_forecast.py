from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from composition import build_ai_forecast_service
from models import ReportingUnavailableResponse
from schemas.common import BoundedListItem100, BoundedText120, MonthStr
from schemas.ai_forecast import AiForecastResponse, AiForecastRollingResponse
from services.ai_forecast import AiForecastService
from services.reporting_consistency import (
    REPORTING_GENERATION_UNSTABLE_DETAIL,
    ReportingGenerationUnstable,
)

router = APIRouter(prefix="/api/ai-forecast", tags=["ai-forecast"])


get_ai_forecast_service = build_ai_forecast_service


@router.get(
    "/current",
    response_model=AiForecastResponse,
    responses={
        503: {
            "model": ReportingUnavailableResponse,
            "description": "Generatia de vanzari s-a modificat in timpul incarcarii forecastului",
        }
    },
)
async def get_current_ai_forecast(
    month: MonthStr,
    metric: str = Query("sales_value", pattern="^(sales_value|units)$"),
    firma: BoundedText120 | None = None,
    regional: BoundedText120 | None = None,
    asm: BoundedText120 | None = None,
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AiForecastService = Depends(get_ai_forecast_service),
) -> AiForecastResponse:
    try:
        response = await svc.get_current(
            month=month,
            metric=metric,  # type: ignore[arg-type]
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
        )
    except ReportingGenerationUnstable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REPORTING_GENERATION_UNSTABLE_DETAIL,
        ) from None
    if response is None:
        raise HTTPException(status_code=404, detail="Nu exista forecast AI pentru luna selectata")
    return response


@router.get("/rolling-12", response_model=AiForecastRollingResponse)
async def get_rolling_12_ai_forecast(
    month: MonthStr,
    metric: str = Query("sales_value", pattern="^(sales_value|units)$"),
    firma: BoundedText120 | None = None,
    regional: BoundedText120 | None = None,
    asm: BoundedText120 | None = None,
    site_code: list[BoundedListItem100] | None = Query(None, max_length=100),
    svc: AiForecastService = Depends(get_ai_forecast_service),
) -> AiForecastRollingResponse:
    response = await svc.get_rolling_12(
        month=month,
        metric=metric,  # type: ignore[arg-type]
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
    )
    if response is None:
        raise HTTPException(status_code=404, detail="Nu exista forecast AI pe 12 luni pentru luna selectata")
    return response
