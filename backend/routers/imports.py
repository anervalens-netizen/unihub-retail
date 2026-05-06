from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile

from db.connection import get_pool
from models import ImportHistoryEntry, ImportJobStatus, ImportResponse
from repositories.imports import ImportsRepository
from services.imports import ImportsService

router = APIRouter(prefix="/api/import", tags=["imports"])

async def get_imports_service() -> ImportsService:
    pool = await get_pool()
    repo = ImportsRepository(pool)
    return ImportsService(repo, pool)


@router.post("/sales", response_model=ImportResponse | ImportJobStatus)
async def upload_sales_file(
    file: UploadFile = File(...),
    background: bool = Query(False, description="Process import asynchronously in background"),
    svc: ImportsService = Depends(get_imports_service),
) -> ImportResponse | ImportJobStatus:
    return await svc.import_sales(file, background=background)


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
