from __future__ import annotations

import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest
from fastapi import HTTPException, UploadFile

import services.imports as imports_module
from services.exports import ExportValidationError, ExportsService
from services.imports import ImportsService
from services.spreadsheet_safety import SpreadsheetUploadError


def _upload(content: bytes = b"checked spreadsheet", filename: str = "source.xlsx") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


def _service(repo: Any | None = None) -> ImportsService:
    return ImportsService(
        repo=repo or MagicMock(),
        pool=cast(asyncpg.Pool, MagicMock()),
    )


def _validated_generation(*, spool_path: str, encode_json: bool = False) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "rows_filtered": 2,
        "store_count": 3,
        "agent_count": 4,
    }
    coverage: dict[str, Any] = {"stores_present_count": 3}
    return {
        "id": 214,
        "import_month": "2026-08",
        "filename": "source.xlsx",
        "is_month_final": False,
        "rows_in_file": 10,
        "rows_imported": 8,
        "coverage_report": json.dumps(coverage) if encode_json else coverage,
        "generation_token": "58daa48f-ceb4-4963-88ab-441a46fedd64",
        "manifest_sha256": "a" * 64,
        "source_spool_path": spool_path,
        "source_artifact_required": False,
        "source_artifact_state": None,
        "source_artifact_sha256": None,
        "source_artifact_bytes": None,
        "manifest": json.dumps(manifest) if encode_json else manifest,
    }


@pytest.mark.parametrize("value", [object(), 501])
def test_export_preview_limit_rejects_invalid_values(value: object) -> None:
    service = ExportsService(cast(Any, object()))

    with pytest.raises(ExportValidationError):
        service._preview_limit({"preview_limit": value})


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["sales", "promo"])
async def test_imports_translate_spreadsheet_preflight_errors(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    def reject_upload(*_args: object) -> None:
        raise SpreadsheetUploadError("unsafe spreadsheet")

    monkeypatch.setattr(imports_module, "validate_spreadsheet_upload", reject_upload)
    service = _service()

    with pytest.raises(HTTPException) as exc_info:
        if operation == "sales":
            await service.import_sales(_upload())
        else:
            await service.import_promo_actuals(
                file=_upload(),
                import_month="2026-08",
                cutoff_date=date(2026, 8, 4),
            )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "unsafe spreadsheet"


@pytest.mark.asyncio
async def test_sales_recovery_rejects_a_different_durable_spool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(
        return_value=_validated_generation(spool_path="/retained/original.upload")
    )
    monkeypatch.setattr(imports_module, "validate_spreadsheet_upload", lambda *_args: None)
    monkeypatch.setattr(
        imports_module,
        "stage_sales_import_spool_file",
        lambda *_args: Path("/retained/different.upload"),
    )
    remove = MagicMock()
    monkeypatch.setattr(imports_module, "remove_sales_import_spool_file", remove)

    with pytest.raises(HTTPException) as exc_info:
        await _service(repo).import_sales(
            _upload(),
            cutoff_date=date(2026, 8, 4),
        )

    assert exc_info.value.status_code == 409
    remove.assert_called_once_with(Path("/retained/different.upload"))


@pytest.mark.asyncio
async def test_sales_recovery_decodes_persisted_json_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"same checked spreadsheet"
    digest = hashlib.sha256(content).hexdigest()
    retained = "/retained/source.upload"
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(
        return_value=_validated_generation(spool_path=retained, encode_json=True)
    )
    monkeypatch.setattr(imports_module, "validate_spreadsheet_upload", lambda *_args: None)
    monkeypatch.setattr(
        imports_module,
        "stage_sales_import_spool_file",
        lambda *_args: Path(retained),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(imports_module, "enqueue_sales_import", enqueue)

    result = await _service(repo).import_sales(
        _upload(content),
        cutoff_date=date(2026, 8, 4),
    )

    assert result.status == "complete"
    assert result.result is not None
    assert result.result.coverage_report.model_dump(exclude_none=True) == {"stores_present_count": 3}
    assert result.result.manifest.model_dump(exclude_none=True) == {
        "anomalies": [],
        "rows_filtered": 2,
        "store_count": 3,
        "agent_count": 4,
    }
    repo.get_validated_sales_generation.assert_awaited_once_with(
        source_sha256=digest,
        cutoff_date=date(2026, 8, 4),
    )
    enqueue.assert_not_awaited()
