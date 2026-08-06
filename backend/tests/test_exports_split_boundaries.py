from __future__ import annotations

import hashlib
import asyncio
import resource
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from openpyxl import load_workbook

import services.export_complex_worker as child_renderer
import services.exports.service as service_module
from services.export_xlsx_formatting import days_filename_suffix
from services.exports import ExportValidationError, ExportsService


def metric_row(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "import_month": "2026-05",
        "day_of_month": 1,
        "total_sales": 100,
        "total_quantity": 10,
        "total_receipts": 5,
        "receipt_2plus_count": 1,
        "focus_quantity": 2,
        "target": 200,
        "working_days": 1,
        "store_count": 1,
        "agent_count": 1,
        "incentive_sales": 0,
        "incentive_quantity": 0,
        "incentive_bonus": 0,
        "promo_sales": 0,
        "promo_quantity": 0,
    }
    value.update(overrides)
    return value


def daily_metrics_request() -> dict[str, Any]:
    return {
        "export_mode": "table",
        "dataset": "stores",
        "months": ["2026-05", "2026-06"],
        "dimensions": ["site_code"],
        "metrics": ["total_sales"],
        "monthly_metrics": [],
        "daily_metrics": ["total_sales", "proc_bon2acc"],
        "selected_days": [1],
    }


def test_complex_request_boundary_accepts_only_supported_durable_shapes() -> None:
    service = ExportsService(cast(Any, None))
    daily_request = daily_metrics_request()

    assert ExportsService.is_complex_request(daily_request)
    assert service.validate_complex_request(daily_request) == "daily_metrics"
    assert service.validate_complex_request(
        {
            "export_mode": "daily_comparison",
            "months": ["2026-05", "2026-06"],
            "daily_metrics": ["total_sales"],
            "comparison_levels": ["general"],
            "selected_days": [1],
        }
    ) == "daily_comparison"
    assert not ExportsService.is_complex_request({"export_mode": "table"})

    invalid_requests = [
        {"export_mode": "table", "dataset": "stores", "months": ["2026-05"]},
        {
            **daily_request,
            "dataset": "incentive_products",
        },
        {
            **daily_request,
            "months": [],
        },
        {
            **daily_request,
            "daily_metrics": ["total_sales"] * 8,
        },
        {
            **daily_request,
            "monthly_metrics": ["total_sales"] * 20,
        },
    ]
    for request in invalid_requests:
        with pytest.raises(ExportValidationError):
            service.validate_complex_request(request)


def test_in_process_daily_renderer_preserves_layout_deltas_and_formats() -> None:
    service = ExportsService(cast(Any, None))
    request = daily_metrics_request()
    result = {
        "columns": [
            {"key": "site_code", "label": "Magazin", "type": "text", "group": "Identificare"},
            {"key": "total_sales", "label": "Vânzări", "type": "currency", "group": "Metrici"},
        ],
        "rows": [{"site_code": "S1", "total_sales": 250}],
    }
    daily_rows = [
        metric_row(import_month="2026-05", total_sales=100, receipt_2plus_count=1),
        metric_row(import_month="2026-06", total_sales=150, receipt_2plus_count=3),
    ]

    artifact = service._render_table_xlsx(request, result, [1], daily_rows)
    try:
        workbook = load_workbook(BytesIO(b"".join(artifact.iter_chunks())))
    finally:
        artifact.close()

    assert workbook.sheetnames == ["Raport", "Configuratie", "Evolutie zilnica"]
    assert workbook["Raport"]["B2"].number_format == "#,##0.00"
    evolution = workbook["Evolutie zilnica"]
    assert evolution["D2"].value == 50
    assert evolution["E2"].value == 50
    assert len(evolution._charts) == 1
    workbook.close()


@pytest.mark.asyncio
async def test_complex_artifact_adoption_rejects_worker_and_attestation_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = ExportsService(cast(Any, None))
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(service_module, "_complex_process_pool", lambda: executor)
    try:
        def rejected_renderer(_payload: dict[str, Any]) -> dict[str, Any]:
            raise ValueError("worker rejected payload")

        with pytest.raises(ExportValidationError, match="siguranta"):
            await service._run_complex_renderer(
                rejected_renderer,
                {"filename": "report.xlsx"},
                cells=1,
            )

        missing = tmp_path / "missing.xlsx"
        with pytest.raises(ExportValidationError, match="lipseste"):
            await service._run_complex_renderer(
                lambda _payload: {
                    "path": str(missing),
                    "size": 1,
                    "sha256": "0" * 64,
                    "peak_rss": 1,
                    "filename": "report.xlsx",
                },
                {"filename": "report.xlsx"},
                cells=1,
            )

        tampered = tmp_path / "tampered.xlsx"
        tampered.write_bytes(b"not-the-attested-content")
        with pytest.raises(ExportValidationError, match="integritate"):
            await service._run_complex_renderer(
                lambda _payload: {
                    "path": str(tampered),
                    "size": tampered.stat().st_size,
                    "sha256": "0" * 64,
                    "peak_rss": 1,
                    "filename": "report.xlsx",
                },
                {"filename": "report.xlsx"},
                cells=1,
            )
        assert not tampered.exists()
    finally:
        executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_cancelled_artifact_adoption_waits_for_bounded_result_then_unlinks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = ExportsService(cast(Any, None))
    executor = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(service_module, "_complex_process_pool", lambda: executor)
    started = Event()
    release = Event()
    orphan = tmp_path / "cancelled-worker.xlsx"

    def renderer(_payload: dict[str, Any]) -> dict[str, Any]:
        started.set()
        release.wait(timeout=5)
        orphan.write_bytes(b"worker-finished-after-cancel")
        return {"path": str(orphan)}

    task = asyncio.create_task(
        service._run_complex_renderer(
            renderer,
            {"filename": "report.xlsx"},
            cells=1,
        )
    )
    await asyncio.to_thread(started.wait, 5)
    task.cancel()
    release.set()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not orphan.exists()

        failed_started = Event()
        failed_release = Event()

        def failed_renderer(_payload: dict[str, Any]) -> dict[str, Any]:
            failed_started.set()
            failed_release.wait(timeout=5)
            raise ValueError("bounded worker failure after cancellation")

        failed_task = asyncio.create_task(
            service._run_complex_renderer(
                failed_renderer,
                {"filename": "report.xlsx"},
                cells=1,
            )
        )
        await asyncio.to_thread(failed_started.wait, 5)
        failed_task.cancel()
        failed_release.set()
        with pytest.raises(asyncio.CancelledError):
            await failed_task
    finally:
        executor.shutdown(wait=True)


def test_child_renderers_emit_hashed_artifacts_without_process_coverage_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(child_renderer, "_enforce_memory_limit", lambda _limit: None)
    monkeypatch.setattr(child_renderer, "_assert_memory_budget", lambda _limit: 4096)
    comparison_payload = {
        "request": {"filename": "comparison.xlsx"},
        "months": ["2026-05", "2026-06"],
        "metrics": ["total_sales"],
        "levels": ["general"],
        "level_config": {
            "general": {"label": "General", "sheet": "General", "dimensions": []}
        },
        "metric_labels": {"total_sales": "Vânzări"},
        "selected_days": [1],
        "tables": [
            (
                "general",
                {
                    "columns": [
                        {"key": "day_of_month", "label": "Zi", "type": "integer"},
                        {"key": "2026-05:total_sales", "label": "Mai", "type": "currency"},
                        {"key": "2026-06:total_sales", "label": "Iunie", "type": "currency"},
                    ],
                    "rows": [
                        {
                            "day_of_month": 1,
                            "2026-05:total_sales": 100,
                            "2026-06:total_sales": 150,
                        }
                    ],
                },
            )
        ],
        "include_closed_stores": False,
        "max_output_bytes": 64 * 1024 * 1024,
        "max_peak_rss_bytes": 512 * 1024 * 1024,
    }
    comparison = child_renderer.render_daily_comparison_xlsx(comparison_payload)
    comparison_path = Path(comparison["path"])
    try:
        content = comparison_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == comparison["sha256"]
        workbook = load_workbook(BytesIO(content))
        assert workbook.sheetnames == ["General", "Configuratie"]
        assert len(workbook["General"]._charts) == 1
        workbook.close()
    finally:
        comparison_path.unlink(missing_ok=True)

    request = daily_metrics_request()
    metrics_payload = {
        "request": request,
        "result": {
            "columns": [
                {"key": "site_code", "label": "Magazin", "type": "text"},
                {"key": "total_sales", "label": "Vânzări", "type": "currency"},
            ],
            "rows": [{"site_code": "S1", "total_sales": 250}],
        },
        "selected_days": [1],
        "daily_rows": [
            metric_row(import_month="2026-05", total_sales=100),
            metric_row(import_month="2026-06", total_sales=150),
        ],
        "filename": "daily.xlsx",
        "max_output_bytes": 64 * 1024 * 1024,
        "max_peak_rss_bytes": 512 * 1024 * 1024,
    }
    metrics = child_renderer.render_daily_metrics_xlsx(metrics_payload)
    metrics_path = Path(metrics["path"])
    try:
        content = metrics_path.read_bytes()
        assert hashlib.sha256(content).hexdigest() == metrics["sha256"]
        workbook = load_workbook(BytesIO(content))
        assert "Evolutie zilnica" in workbook.sheetnames
        workbook.close()
    finally:
        metrics_path.unlink(missing_ok=True)

    metrics_payload["max_output_bytes"] = 1
    with pytest.raises(ValueError, match="output budget"):
        child_renderer.render_daily_metrics_xlsx(metrics_payload)


def test_child_memory_and_output_fences_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="positive"):
        child_renderer._enforce_memory_limit(0)

    real_peak_rss = child_renderer._peak_rss_bytes
    monkeypatch.setattr(child_renderer, "_peak_rss_bytes", lambda: 101)
    with pytest.raises(MemoryError, match="RSS"):
        child_renderer._assert_memory_budget(100)
    monkeypatch.setattr(child_renderer, "_peak_rss_bytes", real_peak_rss)

    monkeypatch.setattr(
        child_renderer.resource,
        "getrusage",
        lambda *_args: SimpleNamespace(ru_maxrss=1),
    )
    assert child_renderer._peak_rss_bytes() == 1024
    assert child_renderer._assert_memory_budget(2048) == 1024

    set_limit = MagicMock()
    monkeypatch.setattr(child_renderer.resource, "setrlimit", set_limit)
    monkeypatch.setattr(
        child_renderer.resource,
        "getrlimit",
        lambda *_args: (resource.RLIM_INFINITY, resource.RLIM_INFINITY),
    )
    child_renderer._enforce_memory_limit(4096)
    set_limit.assert_called_with(resource.RLIMIT_AS, (4096, resource.RLIM_INFINITY))

    monkeypatch.setattr(child_renderer.resource, "getrlimit", lambda *_args: (1024, 2048))
    child_renderer._enforce_memory_limit(4096)
    set_limit.assert_called_with(resource.RLIMIT_AS, (1024, 2048))

    monkeypatch.setattr(child_renderer, "_assert_memory_budget", lambda _limit: 1)
    from openpyxl import Workbook

    workbook = Workbook()
    with pytest.raises(ValueError, match="output budget"):
        child_renderer._save_hashed_workbook(
            workbook,
            max_output_bytes=1,
            max_peak_rss_bytes=100,
        )
    workbook.close()

    assert days_filename_suffix(None) == ""
    assert days_filename_suffix([1, 2]) == "_zile_1-2"
    assert days_filename_suffix(list(range(1, 12))) == "_zile_11selectate"
