from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile

from db.connection import get_pool
from models import ImportHistoryEntry, ImportJobStatus, ImportResponse, PromoActualImportResponse
from repositories.imports import ImportsRepository
from rate_limits import SALES_IMPORT_UPLOAD_LIMIT, rate_limit
from services.imports import ImportsService

router = APIRouter(prefix="/api/import", tags=["imports"])

async def get_imports_service() -> ImportsService:
    pool = await get_pool()
    repo = ImportsRepository(pool)
    return ImportsService(repo, pool)


@router.post("/sales", response_model=ImportJobStatus)
async def upload_sales_file(
    file: UploadFile = File(...),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ImportsService = Depends(get_imports_service),
) -> ImportJobStatus:
    return await svc.import_sales(file)


@router.post("/promo-actuals", response_model=PromoActualImportResponse)
async def upload_promo_actuals_file(
    import_month: str = Form(...),
    cutoff_date: date = Form(...),
    file: UploadFile = File(...),
    _rate_limit: None = Depends(rate_limit(SALES_IMPORT_UPLOAD_LIMIT)),
    svc: ImportsService = Depends(get_imports_service),
) -> PromoActualImportResponse:
    return await svc.import_promo_actuals(
        file=file,
        import_month=import_month,
        cutoff_date=cutoff_date,
    )


@router.get("/jobs/{job_id}", response_model=ImportJobStatus)
async def get_import_job_status(
    job_id: str,
    svc: ImportsService = Depends(get_imports_service),
) -> ImportJobStatus:
    return await svc.get_import_job_status(job_id)


@router.get("/history", response_model=list[ImportHistoryEntry])
async def get_import_history(
    svc: ImportsService = Depends(get_imports_service),
) -> list[ImportHistoryEntry]:
    return await svc.get_import_history()
