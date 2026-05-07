from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import HTTPException, status
from fastapi import UploadFile

from models import ImportHistoryEntry, ImportJobStatus, ImportResponse
from repositories.imports import ImportsRepository
from services.importer import import_sales_file
from services.jobs import JobStatus, enqueue_sales_import, get_job_status
import asyncpg


class ImportsService:
    def __init__(self, repo: ImportsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def import_sales(self, file: UploadFile, background: bool = False) -> ImportResponse | ImportJobStatus:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fișier invalid")

        if background:
            content = await file.read()
            job = await enqueue_sales_import(content, filename=file.filename)
            return ImportJobStatus(job_id=job.job_id, status=JobStatus.QUEUED.value)

        content = await file.read()
        async with self.pool.acquire() as conn:
            result = await import_sales_file(conn, content, filename=file.filename)
        from routers.filters import clear_filter_options_cache

        clear_filter_options_cache()
        return ImportResponse(**asdict(result))

    async def get_import_job_status(self, job_id: str) -> ImportJobStatus:
        result = await get_job_status(job_id)
        return ImportJobStatus(job_id=result.job_id, status=result.status.value)

    async def get_import_history(self) -> list[ImportHistoryEntry]:
        rows = await self.repo.get_import_history()
        return [ImportHistoryEntry(**dict(row)) for row in rows]
