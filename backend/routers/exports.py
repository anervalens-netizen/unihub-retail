from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

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
    months: list[str] = Field(min_length=1, max_length=144)
    dimensions: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)
    monthly_metrics: list[str] = Field(default_factory=list)
    daily_metrics: list[str] = Field(default_factory=list)
    comparison_levels: list[str] = Field(default_factory=list)
    selected_days: list[int] = Field(default_factory=lambda: list(range(1, 32)), max_length=31)
    filters: ExportFilters = Field(default_factory=ExportFilters)
    include_closed_stores: bool = False
    preview_limit: int = Field(default=100, ge=1, le=500)
    filename: str | None = None


class ExportColumnDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: str
    group: str


class ExportDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str
    dimensions: list[ExportColumnDef]


class ExportComparisonLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str


class ExportCatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    datasets: list[ExportDataset]
    metrics: list[ExportColumnDef]
    monthly_metrics: list[ExportColumnDef]
    daily_metrics: list[ExportColumnDef]
    comparison_levels: list[ExportComparisonLevel]


class ExportPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[ExportColumnDef]
    rows: list[dict[str, Any]]
    total_rows: int
    truncated: bool


async def get_exports_service() -> ExportsService:
    pool = await get_pool()
    return ExportsService(ExportsRepository(pool))


@router.get("/catalog", response_model=ExportCatalogResponse)
async def get_catalog(
    svc: ExportsService = Depends(get_exports_service),
) -> ExportCatalogResponse:
    return ExportCatalogResponse.model_validate(svc.catalog())


@router.post("/preview", response_model=ExportPreviewResponse)
async def preview_export(
    body: ExportRequest,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportsService = Depends(get_exports_service),
) -> ExportPreviewResponse:
    try:
        return ExportPreviewResponse.model_validate(await svc.preview(body.model_dump()))
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/download")
async def download_export(
    body: ExportRequest,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportsService = Depends(get_exports_service),
) -> StreamingResponse:
    try:
        artifact = await svc.build_xlsx_artifact(body.model_dump())
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return StreamingResponse(
        artifact.iter_chunks(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(artifact.size),
        },
        background=BackgroundTask(artifact.close),
    )
