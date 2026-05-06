from __future__ import annotations

from dataclasses import asdict

from fastapi import HTTPException, status
from fastapi import UploadFile

from models import ImportHistoryEntry, ImportResponse
from repositories.imports import ImportsRepository
from routers.filters import clear_filter_options_cache
from services.importer import import_sales_file
import asyncpg


class ImportsService:
    def __init__(self, repo: ImportsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def import_sales(self, file: UploadFile) -> ImportResponse:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fișier invalid")
        content = await file.read()
        async with self.pool.acquire() as conn:
            result = await import_sales_file(conn, content, filename=file.filename)
        clear_filter_options_cache()
        return ImportResponse(**asdict(result))

    async def get_import_history(self) -> list[ImportHistoryEntry]:
        rows = await self.repo.get_import_history()
        return [ImportHistoryEntry(**dict(row)) for row in rows]
