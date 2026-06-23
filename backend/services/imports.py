from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import HTTPException, status
from fastapi import UploadFile

from models import ImportHistoryEntry, ImportJobStatus, ImportResponse
from repositories.imports import ImportsRepository
from services.jobs import JobStatus, enqueue_grile_check, enqueue_sales_import, get_job_status
import asyncpg

logger = logging.getLogger(__name__)
DEFAULT_MAX_SALES_UPLOAD_BYTES = 32 * 1024 * 1024
ALLOWED_SALES_EXTENSIONS = frozenset({".xlsx", ".xls"})


async def trigger_grile_check_after_import(import_month: str, snapshot_id: int | None) -> None:
    """Best-effort: enqueue verificarea grilelor dupa un import reusit.

    NU propaga niciodata exceptii — importul de vanzari nu trebuie sa fie
    afectat daca enqueue-ul esueaza (Valkey down etc.).
    """
    try:
        result = await enqueue_grile_check(
            month=import_month, source="auto", source_snapshot_id=snapshot_id
        )
        logger.info(
            "grile check %s (auto) for %s snapshot=%s run=%s",
            result.status,
            import_month,
            snapshot_id,
            result.run_id,
        )
    except Exception:  # noqa: BLE001 — best-effort, nu strica importul
        logger.exception("enqueue grile check (auto) esuat pentru %s", import_month)


class ImportsService:
    def __init__(self, repo: ImportsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def import_sales(self, file: UploadFile) -> ImportJobStatus:
        if not file.filename:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fișier invalid")
        if Path(file.filename).suffix.casefold() not in ALLOWED_SALES_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Importul accepta numai fisiere .xlsx sau .xls",
            )

        max_bytes = int(
            os.getenv("MAX_SALES_UPLOAD_BYTES", str(DEFAULT_MAX_SALES_UPLOAD_BYTES))
        )
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Fisierul depaseste limita de {max_bytes // (1024 * 1024)} MB",
            )
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fisierul este gol",
            )

        job = await enqueue_sales_import(content, filename=file.filename)
        job_status = await get_job_status(job.job_id)
        return ImportJobStatus(
            job_id=job.job_id,
            status=job_status.status.value,
            result=ImportResponse(**job_status.result) if job_status.result else None,
            error=job_status.error,
        )

    async def get_import_job_status(self, job_id: str) -> ImportJobStatus:
        result = await get_job_status(job_id)
        payload = ImportResponse(**result.result) if result.result else None
        return ImportJobStatus(
            job_id=result.job_id,
            status=result.status.value,
            result=payload,
            error=result.error,
        )

    async def get_import_history(self) -> list[ImportHistoryEntry]:
        rows = await self.repo.get_import_history()
        return [ImportHistoryEntry(**dict(row)) for row in rows]
