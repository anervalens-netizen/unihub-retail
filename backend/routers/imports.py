from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from db.connection import get_pool
from models import ImportHistoryEntry, ImportResponse
from repositories.imports import ImportsRepository
from services.imports import ImportsService

router = APIRouter(prefix="/api/import", tags=["imports"])

async def get_imports_service() -> ImportsService:
    pool = await get_pool()
    repo = ImportsRepository(pool)
    return ImportsService(repo, pool)


@router.post("/sales", response_model=ImportResponse)
async def upload_sales_file(
    file: UploadFile = File(...),
    svc: ImportsService = Depends(get_imports_service),
) -> ImportResponse:
    return await svc.import_sales(file)


@router.get("/history", response_model=list[ImportHistoryEntry])
async def get_import_history(
    svc: ImportsService = Depends(get_imports_service),
) -> list[ImportHistoryEntry]:
    return await svc.get_import_history()
