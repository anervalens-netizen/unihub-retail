from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi import HTTPException, UploadFile

import services.imports as imports_module
from services.exports import ExportValidationError, ExportsService
from services.imports import ImportsService
from services.jobs import JobResult, JobStatus
from services.spreadsheet_safety import SpreadsheetUploadError


def _upload(content: bytes = b"checked spreadsheet", filename: str = "source.xlsx") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


def _service(repo: Any | None = None) -> ImportsService:
    return ImportsService(
        repo=repo or MagicMock(),
        pool=cast(asyncpg.Pool, MagicMock()),
    )


@pytest.mark.parametrize("value", [object(), 501])
def test_export_preview_limit_rejects_invalid_values(value: object) -> None:
    service = ExportsService(cast(Any, object()))

    with pytest.raises(ExportValidationError):
        service._preview_limit({"preview_limit": value})


@pytest.mark.asyncio
async def test_promo_worker_translates_spreadsheet_preflight_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_upload(*_args: object, **_kwargs: object) -> None:
        raise SpreadsheetUploadError("unsafe spreadsheet")

    monkeypatch.setattr(imports_module, "validate_spreadsheet_upload", reject_upload)

    with pytest.raises(HTTPException) as exc_info:
        await _service().process_promo_actuals(
            content=b"unsafe spreadsheet",
            filename="source.xlsx",
            import_month="2026-08",
            cutoff_date=date(2026, 8, 4),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsafe spreadsheet"


@pytest.mark.asyncio
async def test_sales_web_boundary_only_bounds_bytes_and_queues_worker_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    preflight = MagicMock(side_effect=AssertionError("web must not parse XLSX"))
    enqueue = AsyncMock(return_value=MagicMock(job_id="sales-import:queued"))
    monkeypatch.setattr(imports_module, "validate_spreadsheet_upload", preflight)
    monkeypatch.setattr(imports_module, "enqueue_sales_import", enqueue)
    monkeypatch.setattr(
        imports_module,
        "get_job_status",
        AsyncMock(
            return_value=JobResult(
                job_id="sales-import:queued",
                status=JobStatus.QUEUED,
            )
        ),
    )

    result = await _service().import_sales(_upload())

    assert result.status == "queued"
    preflight.assert_not_called()
    enqueue.assert_awaited_once()
