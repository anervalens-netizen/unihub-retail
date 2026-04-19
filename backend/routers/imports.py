from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from db.connection import get_pool
from models import ImportHistoryEntry, ImportResponse
from routers.filters import clear_filter_options_cache
from services.importer import import_sales_file

router = APIRouter(prefix="/api/import", tags=["imports"])


@router.post("/sales", response_model=ImportResponse)
async def upload_sales_file(
    file: UploadFile = File(...),
) -> ImportResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fișier invalid")
    content = await file.read()
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await import_sales_file(conn, content, filename=file.filename)
    clear_filter_options_cache()
    return ImportResponse(**asdict(result))


@router.get("/history", response_model=list[ImportHistoryEntry])
async def get_import_history() -> list[ImportHistoryEntry]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, import_month, filename, upload_date, is_month_final, rows_in_file,
                   rows_imported, status, error_message, imported_by, created_at
            FROM import_snapshots
            ORDER BY created_at DESC
            """
        )
    return [ImportHistoryEntry(**dict(row)) for row in rows]
