from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from arq.jobs import JobStatus as ArqJobStatus
from fastapi import HTTPException, UploadFile

import services.imports as imports_service
import services.jobs as jobs_service
from services.imports import ImportsService
from services.jobs import JobResult, JobStatus


def service() -> ImportsService:
    return ImportsService(MagicMock(), MagicMock())


@pytest.mark.asyncio
async def test_sales_import_rejects_unsupported_extension() -> None:
    upload = UploadFile(file=BytesIO(b"data"), filename="sales.csv")
    with pytest.raises(HTTPException) as exc:
        await service().import_sales(upload)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_sales_import_enforces_bounded_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_SALES_UPLOAD_BYTES", "4")
    upload = UploadFile(file=BytesIO(b"12345"), filename="sales.xlsx")
    with pytest.raises(HTTPException) as exc:
        await service().import_sales(upload)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_sales_import_is_always_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="sales-import:abc"))
    status = AsyncMock(
        return_value=JobResult(
            job_id="sales-import:abc",
            status=JobStatus.QUEUED,
        )
    )
    monkeypatch.setattr(imports_service, "enqueue_sales_import", enqueue)
    monkeypatch.setattr(imports_service, "get_job_status", status)
    upload = UploadFile(file=BytesIO(b"valid"), filename="sales.xlsx")

    result = await service().import_sales(upload)

    assert result.job_id == "sales-import:abc"
    assert result.status == "queued"
    enqueue.assert_awaited_once_with(b"valid", filename="sales.xlsx")


@pytest.mark.asyncio
async def test_failed_content_hash_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacement = SimpleNamespace(job_id="sales-import:replacement")
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(side_effect=[None, replacement])
    pool.delete = AsyncMock()
    existing = MagicMock()
    existing.status = AsyncMock(return_value=ArqJobStatus.complete)
    existing.result_info = AsyncMock(return_value=SimpleNamespace(success=False))
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(jobs_service, "Job", MagicMock(return_value=existing))

    result = await jobs_service.enqueue_sales_import(b"same content", "sales.xlsx")

    assert result is replacement
    pool.delete.assert_awaited_once()
    assert pool.enqueue_job.await_count == 2
