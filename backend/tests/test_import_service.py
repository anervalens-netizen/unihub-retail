from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
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
async def test_sales_import_rejects_missing_filename() -> None:
    upload = UploadFile(file=BytesIO(b"data"), filename=None)
    with pytest.raises(HTTPException) as exc:
        await service().import_sales(upload)
    assert exc.value.status_code == 400


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
async def test_sales_import_rejects_empty_file() -> None:
    upload = UploadFile(file=BytesIO(), filename="sales.xlsx")
    with pytest.raises(HTTPException) as exc:
        await service().import_sales(upload)
    assert exc.value.status_code == 400
    assert exc.value.detail == "Fisierul este gol"


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
    enqueue.assert_awaited_once_with(
        b"valid",
        filename="sales.xlsx",
        cutoff_date=None,
        requested_by_sub="unknown",
    )


@pytest.mark.asyncio
async def test_import_job_status_maps_result_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "import_month": "2099-07",
        "rows_in_file": 2,
        "rows_imported": 2,
        "rows_filtered": 0,
        "store_count": 1,
        "agent_count": 2,
        "snapshot_id": 12,
        "filename": "sales.xlsx",
        "is_month_final": False,
    }
    monkeypatch.setattr(
        imports_service,
        "get_job_status",
        AsyncMock(
            return_value=JobResult(
                job_id="sales-import:abc",
                status=JobStatus.COMPLETE,
                result=payload,
            )
        ),
    )

    result = await service().get_import_job_status("sales-import:abc")

    assert result.status == "complete"
    assert result.result is not None
    assert result.result.snapshot_id == 12


@pytest.mark.asyncio
@pytest.mark.parametrize("job_id", ["sales-import:abc", "sales-promote:213:abc"])
async def test_sales_job_status_uses_import_worker_queue(
    monkeypatch: pytest.MonkeyPatch,
    job_id: str,
) -> None:
    pool = MagicMock()
    job = MagicMock()
    job.status = AsyncMock(return_value=ArqJobStatus.queued)
    job_factory = MagicMock(return_value=job)
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(jobs_service, "Job", job_factory)

    result = await jobs_service.get_job_status(job_id)

    assert result.status is JobStatus.QUEUED
    job_factory.assert_called_once_with(
        job_id,
        pool,
        _queue_name=jobs_service.SALES_IMPORT_QUEUE_NAME,
    )


@pytest.mark.asyncio
async def test_import_history_maps_repository_rows() -> None:
    now = datetime.now(timezone.utc)
    repo = MagicMock()
    repo.get_import_history = AsyncMock(
        return_value=[
            {
                "id": 12,
                "import_month": "2099-07",
                "filename": "sales.xlsx",
                "upload_date": date(2099, 7, 31),
                "is_month_final": False,
                "rows_in_file": 2,
                "rows_imported": 2,
                "status": "completed",
                "error_message": None,
                "coverage_report": json.dumps(
                    {
                        "stores_present_count": 1,
                        "stores_missing_count": 0,
                    }
                ),
                "created_at": now,
            }
        ]
    )

    result = await ImportsService(repo, MagicMock()).get_import_history()

    assert len(result) == 1
    assert result[0].id == 12
    assert result[0].status == "completed"
    assert result[0].coverage_report.model_dump(exclude_none=True) == {
        "stores_present_count": 1,
        "stores_missing_count": 0,
    }


@pytest.mark.asyncio
async def test_grile_check_after_import_is_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(
        return_value=SimpleNamespace(
            status="queued",
            run_id=8,
        )
    )
    monkeypatch.setattr(imports_service, "enqueue_grile_check", enqueue)

    await imports_service.trigger_grile_check_after_import("2099-07", 12)

    enqueue.assert_awaited_once_with(
        month="2099-07",
        source="auto",
        source_snapshot_id=12,
        triggered_by_sub="system:sales-import",
        sales_import_authority=True,
    )

    enqueue.side_effect = RuntimeError("Valkey unavailable")
    await imports_service.trigger_grile_check_after_import("2099-07", 12)


@pytest.mark.asyncio
async def test_failed_content_hash_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
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
    for call in pool.enqueue_job.await_args_list:
        assert call.kwargs["_queue_name"] == jobs_service.SALES_IMPORT_QUEUE_NAME
        assert isinstance(call.args[1], str)
        assert call.args[2] == jobs_service.sha256(b"same content").hexdigest()
        assert call.args[3] == len(b"same content")
        assert b"same content" not in call.args


@pytest.mark.asyncio
async def test_failed_sales_promotion_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replacement = SimpleNamespace(job_id="sales-promote:replacement")
    pool = MagicMock()
    pool.delete = AsyncMock()
    existing = MagicMock()
    existing.status = AsyncMock(return_value=ArqJobStatus.complete)
    existing.result_info = AsyncMock(return_value=SimpleNamespace(success=False))
    publish = AsyncMock(side_effect=[None, replacement])
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(jobs_service, "Job", MagicMock(return_value=existing))
    monkeypatch.setattr(jobs_service, "_publish_arq_job", publish)

    result = await jobs_service.enqueue_sales_promotion(
        snapshot_id=214,
        generation_token="a" * 36,
        owner_id="b" * 36,
        manifest_sha256="c" * 64,
        requested_by_sub="codex:repair",
        override_reason=None,
    )

    assert result is replacement
    pool.delete.assert_awaited_once()
    assert publish.await_count == 2


@pytest.mark.asyncio
async def test_sales_import_spools_bytes_outside_valkey_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    queued = SimpleNamespace(job_id="sales-import:queued")
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=queued)
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))

    result = await jobs_service.enqueue_sales_import(b"excel bytes", "sales.xlsx")

    assert result is queued
    call = pool.enqueue_job.await_args
    spool_path = Path(call.args[1])
    assert spool_path.read_bytes() == b"excel bytes"
    assert call.args[0] == "import_sales_background"
    assert call.args[2] == jobs_service.sha256(b"excel bytes").hexdigest()
    assert call.args[3] == len(b"excel bytes")
    assert call.args[4] == "sales.xlsx"
    assert call.kwargs["_queue_name"] == jobs_service.SALES_IMPORT_QUEUE_NAME
    assert b"excel bytes" not in call.args


@pytest.mark.asyncio
async def test_promo_import_spools_bytes_and_uses_distinct_job_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    queued = SimpleNamespace(job_id="promo-actuals:queued")
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=queued)
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))

    result = await jobs_service.enqueue_promo_actuals_import(
        b"promo bytes",
        filename="promo.xlsx",
        import_month="2026-08",
        cutoff_date="2026-08-05",
    )

    assert result is queued
    call = pool.enqueue_job.await_args
    assert call.args[0] == "import_promo_actuals_background"
    assert Path(call.args[1]).read_bytes() == b"promo bytes"
    assert call.args[2] == jobs_service.sha256(b"promo bytes").hexdigest()
    assert call.args[4:] == ("promo.xlsx", "2026-08", "2026-08-05")
    assert call.kwargs["_job_id"].startswith("promo-actuals:")
    assert call.kwargs["_queue_name"] == jobs_service.SALES_IMPORT_QUEUE_NAME
    assert b"promo bytes" not in call.args


@pytest.mark.asyncio
async def test_failed_spooled_erp_job_can_be_retried(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    replacement = SimpleNamespace(job_id="erp-reconciliation:replacement")
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(side_effect=[None, replacement])
    pool.delete = AsyncMock()
    existing = MagicMock()
    existing.status = AsyncMock(return_value=ArqJobStatus.complete)
    existing.result_info = AsyncMock(return_value=SimpleNamespace(success=False))
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(jobs_service, "Job", MagicMock(return_value=existing))

    result = await jobs_service.enqueue_erp_reconciliation(
        b"erp bytes",
        filename="erp.xlsx",
        import_month="2026-08",
    )

    assert result is replacement
    pool.delete.assert_awaited_once()
    assert pool.enqueue_job.await_count == 2
    for call in pool.enqueue_job.await_args_list:
        assert call.args[0] == "reconcile_erp_background"
        assert call.args[4:] == ("erp.xlsx", "2026-08")
        assert call.kwargs["_job_id"].startswith("erp-reconciliation:")
    assert pool.enqueue_job.await_args_list[0].args[1] == pool.enqueue_job.await_args_list[1].args[1]


@pytest.mark.asyncio
async def test_same_bytes_for_distinct_erp_months_use_isolated_spool_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(
        side_effect=[
            SimpleNamespace(job_id="erp-reconciliation:first"),
            SimpleNamespace(job_id="erp-reconciliation:second"),
        ]
    )
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))

    await jobs_service.enqueue_erp_reconciliation(
        b"same erp bytes",
        filename="erp.xlsx",
        import_month="2026-07",
    )
    await jobs_service.enqueue_erp_reconciliation(
        b"same erp bytes",
        filename="erp.xlsx",
        import_month="2026-08",
    )

    first_path = Path(pool.enqueue_job.await_args_list[0].args[1])
    second_path = Path(pool.enqueue_job.await_args_list[1].args[1])
    assert first_path != second_path
    assert first_path.read_bytes() == second_path.read_bytes() == b"same erp bytes"


def test_stale_failed_spool_artifacts_expire_after_bounded_retention(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    monkeypatch.setenv("SALES_IMPORT_SPOOL_MAX_AGE_SECONDS", "3600")
    digest = jobs_service.sha256(b"failed payload").hexdigest()
    path = jobs_service.stage_sales_import_spool_file(
        b"failed payload",
        digest,
        namespace="a" * 64,
    )
    stale_time = time.time() - 3601
    os.utime(path, (stale_time, stale_time))

    assert jobs_service.cleanup_stale_sales_import_spool_files() == 1
    assert not path.exists()


@pytest.mark.asyncio
async def test_completed_spooled_job_removes_recreated_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"already complete"
    digest = jobs_service.sha256(content).hexdigest()
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    existing = MagicMock()
    existing.status = AsyncMock(return_value=ArqJobStatus.complete)
    existing.result_info = AsyncMock(return_value=SimpleNamespace(success=True))
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(jobs_service, "Job", MagicMock(return_value=existing))

    result = await jobs_service.enqueue_erp_reconciliation(
        content,
        filename="erp.xlsx",
        import_month="2026-08",
    )

    assert result is existing
    assert not (tmp_path / f"{digest}.upload").exists()


@pytest.mark.asyncio
async def test_spooled_job_removes_artifact_on_confirmed_publish_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"confirmed failure"
    digest = jobs_service.sha256(content).hexdigest()
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(
        jobs_service,
        "_publish_arq_job",
        AsyncMock(side_effect=RuntimeError("rejected before publish")),
    )

    with pytest.raises(RuntimeError, match="rejected before publish"):
        await jobs_service.enqueue_erp_reconciliation(
            content,
            filename="erp.xlsx",
            import_month="2026-08",
        )

    assert not (tmp_path / f"{digest}.upload").exists()


@pytest.mark.asyncio
async def test_spooled_job_preserves_artifact_when_publish_is_unconfirmed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = b"possibly accepted"
    digest = jobs_service.sha256(content).hexdigest()
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_service, "get_arq_pool", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(
        jobs_service,
        "_publish_arq_job",
        AsyncMock(side_effect=jobs_service.JobPublishUncertainError(job_id="erp-reconciliation:test")),
    )

    with pytest.raises(jobs_service.JobPublishUncertainError):
        await jobs_service.enqueue_erp_reconciliation(
            content,
            filename="erp.xlsx",
            import_month="2026-08",
        )

    artifacts = list(tmp_path.glob(f"{digest}.*.upload"))
    assert len(artifacts) == 1
    assert artifacts[0].read_bytes() == content
