from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import ConfigDict, Field
from schemas.common import StrictApiModel
from starlette.background import BackgroundTask

from auth import AuthClaims
from composition import build_export_operations_service, build_exports_service
from models import ExportOperationResponse, ExportOperationUnavailableResponse
from permissions import require_report_export_access
from rate_limits import REPORT_EXPORT_LIMIT, rate_limit
from domain.export_operations import ExportOperationCapacityError
from services.export_operations import (
    ExportArtifactExpiredError,
    ExportArtifactIntegrityError,
    ExportOperationConflictError,
    ExportOperationNotFoundError,
    ExportOperationsService,
)
from services.exports import ExportValidationError, ExportsService

router = APIRouter(prefix="/api/exports", tags=["exports"])


class ExportFilters(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    firma: list[str] = Field(default_factory=list)
    regional: list[str] = Field(default_factory=list)
    asm: list[str] = Field(default_factory=list)
    site_code: list[str] = Field(default_factory=list)
    agent: list[str] = Field(default_factory=list)


class ExportRequest(StrictApiModel):
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


class ExportColumnDef(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: str
    group: str


class ExportDataset(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    description: str
    dimensions: list[ExportColumnDef]


class ExportComparisonLevel(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str


class ExportCatalogResponse(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    datasets: list[ExportDataset]
    metrics: list[ExportColumnDef]
    monthly_metrics: list[ExportColumnDef]
    daily_metrics: list[ExportColumnDef]
    comparison_levels: list[ExportComparisonLevel]


class ExportPreviewResponse(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[ExportColumnDef]
    rows: list[dict[str, Any]]
    total_rows: int
    truncated: bool


get_exports_service = build_exports_service
get_export_operations_service = build_export_operations_service


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


@router.post(
    "/download",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
async def download_export(
    body: ExportRequest,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportsService = Depends(get_exports_service),
) -> StreamingResponse:
    if ExportsService.is_complex_request(body.model_dump()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exporturile cu evolutie zilnica se genereaza prin operatia durabila.",
        )
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


@router.post(
    "/operations",
    response_model=ExportOperationResponse,
    responses={
        400: {"description": "Cerere complexa invalida"},
        409: {"description": "Capacitate activa epuizata"},
        503: {
            "model": ExportOperationUnavailableResponse,
            "description": "Publicare ARQ indisponibila sau neconfirmata",
        },
    },
)
async def create_export_operation(
    body: ExportRequest,
    claims: AuthClaims = Depends(require_report_export_access),
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportOperationsService = Depends(get_export_operations_service),
) -> ExportOperationResponse:
    try:
        return await svc.reserve(body.model_dump(mode="json"), requested_by_sub=claims.sub)
    except ExportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ExportOperationCapacityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exista deja prea multe exporturi complexe active.",
    ) from exc


@router.get("/operations/resumable", response_model=ExportOperationResponse | None)
async def get_resumable_export_operation(
    claims: AuthClaims = Depends(require_report_export_access),
    svc: ExportOperationsService = Depends(get_export_operations_service),
) -> ExportOperationResponse | None:
    return await svc.resumable(requested_by_sub=claims.sub)


@router.get(
    "/operations/{operation_id}",
    response_model=ExportOperationResponse,
    responses={404: {"description": "Operatie inexistenta sau apartinand altui subiect"}},
)
async def get_export_operation(
    operation_id: int,
    claims: AuthClaims = Depends(require_report_export_access),
    svc: ExportOperationsService = Depends(get_export_operations_service),
) -> ExportOperationResponse:
    try:
        return await svc.status(operation_id, requested_by_sub=claims.sub)
    except ExportOperationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exportul nu exista.") from exc


@router.post(
    "/operations/{operation_id}/cancel",
    response_model=ExportOperationResponse,
    responses={
        404: {"description": "Operatie inexistenta sau apartinand altui subiect"},
        409: {"description": "Operatie deja terminala"},
    },
)
async def cancel_export_operation(
    operation_id: int,
    claims: AuthClaims = Depends(require_report_export_access),
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportOperationsService = Depends(get_export_operations_service),
) -> ExportOperationResponse:
    try:
        return await svc.cancel(operation_id, requested_by_sub=claims.sub)
    except ExportOperationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exportul nu exista.") from exc
    except ExportOperationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/operations/{operation_id}/download",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        },
        404: {"description": "Operatie inexistenta sau apartinand altui subiect"},
        409: {"description": "Operatie nefinalizata sau artifact invalid"},
        410: {"description": "Artifact expirat"},
    },
)
async def download_export_operation(
    operation_id: int,
    claims: AuthClaims = Depends(require_report_export_access),
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: ExportOperationsService = Depends(get_export_operations_service),
) -> StreamingResponse:
    try:
        artifact = await svc.download(operation_id, requested_by_sub=claims.sub)
    except ExportOperationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exportul nu exista.") from exc
    except ExportArtifactExpiredError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Artifactul exportului a expirat.") from exc
    except ExportOperationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ExportArtifactIntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifactul exportului nu a trecut verificarea de integritate.",
        ) from exc

    return StreamingResponse(
        artifact.iter_chunks(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "Content-Length": str(artifact.size),
        },
        background=BackgroundTask(artifact.close),
    )
