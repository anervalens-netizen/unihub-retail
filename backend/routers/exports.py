from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from db.connection import get_pool
from rate_limits import REPORT_EXPORT_LIMIT, rate_limit
from repositories.exports import ExportsRepository
from services.exports import ExportValidationError, ExportsService

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firma: list[str] = Field(default_factory=list)
    regional: list[str] = Field(default_factory=list)
    asm: list[str] = Field(default_factory=list)
    site_code: list[str] = Field(default_factory=list)
    agent: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_mode: str = "table"
    dataset: str
    months: list[str] = Field(min_length=1, max_length=24)
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    monthly_metrics: list[str] = Field(default_factory=list)
    daily_metrics: list[str] = Field(default_factory=list)
    comparison_levels: list[str] = Field(default_factory=list)
    filters: ExportFilters = Field(default_factory=ExportFilters)
    include_closed_stores: bool = False
    preview_limit: int = Field(default=100, ge=1, le=500)
    filename: str | None = Field(default=None, max_length=120)


async def get_exports_service() -> ExportsService:
    pool = await get_pool()
    return ExportsService(ExportsRepository(pool))


@router.get("/catalog")
async def get_catalog(
    svc: ExportsService = Depends(get_exports_service),
) -> dict:
    return svc.catalog()


@router.post("/preview")
async def preview_export(
    body: ExportRequest,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportsService = Depends(get_exports_service),
) -> dict:
    try:
        return await svc.preview(body.model_dump())
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/download")
async def download_export(
    body: ExportRequest,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportsService = Depends(get_exports_service),
) -> StreamingResponse:
    try:
        content, filename = await svc.build_xlsx(body.model_dump())
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
