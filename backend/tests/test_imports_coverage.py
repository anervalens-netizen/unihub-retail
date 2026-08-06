from __future__ import annotations

import hashlib
import json
import stat
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pandas as pd
import pytest
from fastapi import HTTPException, UploadFile

import services.imports as imports_module
from models import SalesGenerationPromotionRequest
from services.imports import ImportsService
from services.jobs import JobResult, JobStatus


@pytest.fixture(autouse=True)
def bypass_structural_preflight_for_business_flow_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        imports_module,
        "validate_spreadsheet_upload",
        lambda *_args, **_kwargs: None,
    )


def _service(pool: object | None = None) -> ImportsService:
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(return_value=None)
    return ImportsService(
        repo=repo,
        pool=cast(asyncpg.Pool, pool if pool is not None else MagicMock()),
    )


def _upload(content: bytes = b"report", filename: str | None = "promo.xlsx") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> bool:
        return False


def _promotion_config(*, source_file: str = "@GENERATION_ACTUALS@") -> dict[str, object]:
    return {
        "promotions": [
            {
                "key": "active",
                "start_date": "2026-06-01",
                "end_date": "2026-06-30",
                "item_codes": ["I1"],
                "actuals_source_file": source_file,
            }
        ]
    }


@pytest.mark.asyncio
async def test_campaign_reporting_publication_hook_logs_queued_job(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="campaign-reporting:2026-06"))
    monkeypatch.setattr(
        imports_module,
        "enqueue_campaign_reporting_publication",
        enqueue,
    )

    with caplog.at_level("INFO", logger="services.imports"):
        await imports_module.trigger_campaign_reporting_publication(
            "2026-06",
            requested_by_sub="system:sales-import",
            reason="sales_generation_promoted",
        )

    enqueue.assert_awaited_once_with(
        month="2026-06",
        requested_by_sub="system:sales-import",
        reason="sales_generation_promoted",
    )
    assert "campaign reporting publication queued month=2026-06" in caplog.text


def _configure_promo_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config: object,
) -> None:
    config_path = tmp_path / "hub_specials.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(imports_module, "get_special_cards_config_path", lambda: config_path)
    monkeypatch.setattr(imports_module, "get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(
            lambda _: imports_module.PromoActualsParseResult(
                report_rows=1,
                promo_units=1,
                rows=(
                    {
                        "site_code": "S1",
                        "item_code": "I1",
                        "quantity": 1,
                        "value": "0.00",
                    },
                ),
            )
        ),
    )


def _promotion_request() -> SalesGenerationPromotionRequest:
    return SalesGenerationPromotionRequest(
        generation_token="a" * 36,
        manifest_sha256="b" * 64,
        override_reason="operator approved promotion",
    )


def test_promo_parse_result_compatibility_equality() -> None:
    rows = ({"site_code": "S1", "item_code": "I1", "quantity": 1, "value": "0.00"},)
    first = imports_module.PromoActualsParseResult(1, 1, rows)
    same = imports_module.PromoActualsParseResult(1, 1, rows)

    assert first == (1, 1)
    assert first == same
    assert first.__eq__(object()) is NotImplemented


@pytest.mark.parametrize("state", [JobStatus.BACKEND_UNAVAILABLE, JobStatus.UNKNOWN])
def test_job_status_unavailable_is_not_exposed_as_import_result(state: JobStatus) -> None:
    with pytest.raises(HTTPException) as exc:
        imports_module._to_public_import_status(JobResult(job_id="job-1", status=state))

    assert exc.value.status_code == 503
    assert exc.value.detail == "Job status unavailable"


def test_publish_promo_generation_hashes_external_source_and_rejects_missing_source(
    tmp_path: Path,
) -> None:
    external_actuals = tmp_path / "external.xlsx"
    external_actuals.write_bytes(b"external-actuals")
    config = _promotion_config(source_file=str(external_actuals))

    generation_id, _, _ = imports_module._publish_promo_generation(
        data_dir=tmp_path / "data",
        config=config,
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="c" * 64,
        expected_pointer_sha256=None,
    )

    pointer = json.loads(
        (tmp_path / "data" / "promo_generations" / "current.json").read_text(
            encoding="utf-8"
        )
    )
    assert pointer["generation_id"] == generation_id
    assert pointer["actuals"] == [
        {"file": str(external_actuals), "sha256": hashlib.sha256(b"external-actuals").hexdigest()}
    ]

    with pytest.raises(ValueError, match="Sursa actuals promo lipsește"):
        imports_module._publish_promo_generation(
            data_dir=tmp_path / "missing-data",
            config=_promotion_config(source_file=str(tmp_path / "missing.xlsx")),
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="c" * 64,
            expected_pointer_sha256=None,
        )


def test_publish_promo_generation_hashes_external_material_and_rejects_missing_material(
    tmp_path: Path,
) -> None:
    external_actuals = tmp_path / "external.xlsx"
    external_material = tmp_path / "external.json"
    external_actuals.write_bytes(b"external-actuals")
    external_material.write_bytes(b'{"rows":[]}\n')
    config = _promotion_config(source_file=str(external_actuals))
    promotion = cast(list[dict[str, object]], config["promotions"])[0]
    promotion["actuals_material_file"] = str(external_material)

    imports_module._publish_promo_generation(
        data_dir=tmp_path / "data",
        config=config,
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="c" * 64,
        expected_pointer_sha256=None,
    )
    pointer = json.loads(
        (tmp_path / "data" / "promo_generations" / "current.json").read_text()
    )
    assert pointer["actuals_materials"] == [
        {
            "file": str(external_material),
            "sha256": hashlib.sha256(external_material.read_bytes()).hexdigest(),
        }
    ]

    external_material.unlink()
    with pytest.raises(ValueError, match="Materializarea actuals promo lipsește"):
        imports_module._publish_promo_generation(
            data_dir=tmp_path / "missing-material-data",
            config=config,
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="c" * 64,
            expected_pointer_sha256=None,
        )


def test_publish_promo_generation_reuses_exact_generation(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    first = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="d" * 64,
        expected_pointer_sha256=None,
    )
    generation_root = data_dir / "promo_generations"
    pointer_path = generation_root / "current.json"
    pointer_before = pointer_path.read_bytes()
    second = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="d" * 64,
        expected_pointer_sha256=imports_module._promo_pointer_sha256(data_dir),
    )

    assert second == first
    assert pointer_path.read_bytes() == pointer_before
    pointer = json.loads(pointer_before)
    assert pointer["previous_generation_id"] != pointer["generation_id"]
    generation_dir = generation_root / first[0]
    assert stat.S_IMODE(generation_root.stat().st_mode) == 0o700
    assert stat.S_IMODE(generation_dir.stat().st_mode) == 0o700
    for artifact in (
        pointer_path,
        generation_dir / "promo_actuals.xlsx",
        generation_dir / "promo_actuals.json",
        generation_dir / "hub_specials.json",
    ):
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o600


def test_publish_promo_generation_rejects_inconsistent_exact_retry_pointer(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    first = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="d" * 64,
        expected_pointer_sha256=None,
    )
    pointer_path = data_dir / "promo_generations" / "current.json"
    pointer = json.loads(pointer_path.read_text())
    pointer["previous_generation_id"] = first[0]
    pointer_path.write_bytes(imports_module._canonical_json_bytes(pointer))

    with pytest.raises(imports_module.PromoGenerationPointerIntegrityError):
        imports_module._publish_promo_generation(
            data_dir=data_dir,
            config=_promotion_config(),
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="d" * 64,
            expected_pointer_sha256=imports_module._promo_pointer_sha256(data_dir),
        )


@pytest.mark.parametrize(
    ("artifact_name", "mutation"),
    [
        ("promo_actuals.xlsx", "missing"),
        ("promo_actuals.json", "missing"),
        ("hub_specials.json", "missing"),
        ("promo_actuals.xlsx", "tampered"),
        ("promo_actuals.json", "tampered"),
        ("hub_specials.json", "tampered"),
    ],
)
def test_publish_promo_generation_rejects_each_existing_artifact_integrity_failure(
    tmp_path: Path,
    artifact_name: str,
    mutation: str,
) -> None:
    data_dir = tmp_path / "data"
    first = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="e" * 64,
        expected_pointer_sha256=None,
    )
    artifact_path = data_dir / "promo_generations" / first[0] / artifact_name
    pointer_path = data_dir / "promo_generations" / "current.json"
    pointer_before = pointer_path.read_bytes()
    if mutation == "missing":
        artifact_path.unlink()
    else:
        artifact_path.write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="Coliziune de generație promo"):
        imports_module._publish_promo_generation(
            data_dir=data_dir,
            config=_promotion_config(),
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="e" * 64,
            expected_pointer_sha256=imports_module._promo_pointer_sha256(data_dir),
        )

    assert pointer_path.read_bytes() == pointer_before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_pointer",
    [
        b"not-json",
        b"[]",
        b'{"generation_id":"not-a-valid-generation"}',
    ],
)
async def test_promo_actuals_fails_closed_for_invalid_current_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    invalid_pointer: bytes,
) -> None:
    _configure_promo_paths(monkeypatch, tmp_path, _promotion_config())
    data_dir = tmp_path / "data"
    imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="e" * 64,
        expected_pointer_sha256=None,
    )
    generation_root = data_dir / "promo_generations"
    pointer_path = generation_root / "current.json"
    pointer_path.write_bytes(invalid_pointer)
    generation_dirs_before = {
        path.name for path in generation_root.iterdir() if path.is_dir()
    }

    with pytest.raises(HTTPException) as exc:
        await _service().process_promo_actuals(
            content=b"uploaded-actuals",
            filename="promo.xlsx",
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Configuratia promo activa este invalida; importul a fost oprit"
    assert isinstance(exc.value.__cause__, imports_module.PromoGenerationPointerIntegrityError)
    assert pointer_path.read_bytes() == invalid_pointer
    assert {path.name for path in generation_root.iterdir() if path.is_dir()} == generation_dirs_before


def test_publish_promo_generation_removes_staging_after_atomic_promotion_fault(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_replace = Path.replace

    def fail_staging_replace(path: Path, target: str | Path) -> Path:
        if path.name.startswith(".staging-"):
            raise OSError("filesystem promotion fault")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_staging_replace)
    data_dir = tmp_path / "data"

    with pytest.raises(OSError, match="filesystem promotion fault"):
        imports_module._publish_promo_generation(
            data_dir=data_dir,
            config=_promotion_config(),
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="f" * 64,
            expected_pointer_sha256=None,
        )

    assert not list((data_dir / "promo_generations").glob(".staging-*"))


@pytest.mark.asyncio
async def test_sales_import_with_explicit_cutoff_preserves_audit_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="sales-import:1"))
    monkeypatch.setattr(imports_module, "enqueue_sales_import", enqueue)
    monkeypatch.setattr(
        imports_module,
        "get_job_status",
        AsyncMock(return_value=JobResult(job_id="sales-import:1", status=JobStatus.QUEUED)),
    )

    result = await _service().import_sales(
        _upload(b"sales", "sales.xlsx"),
        cutoff_date=date(2026, 6, 20),
        requested_by_sub="owner:123",
    )

    assert result.status == "queued"
    enqueue.assert_awaited_once_with(
        b"sales",
        filename="sales.xlsx",
        cutoff_date="2026-06-20",
        requested_by_sub="owner:123",
    )


@pytest.mark.asyncio
async def test_promo_import_enqueues_and_returns_public_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="promo-import:1"))
    monkeypatch.setattr(imports_module, "enqueue_promo_actuals_import", enqueue)
    monkeypatch.setattr(
        imports_module,
        "get_job_status",
        AsyncMock(return_value=JobResult(job_id="promo-import:1", status=JobStatus.QUEUED)),
    )

    result = await _service().import_promo_actuals(
        file=_upload(b"promo", "promo.xlsx"),
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )

    assert result.job_id == "promo-import:1"
    enqueue.assert_awaited_once_with(
        b"promo",
        filename="promo.xlsx",
        import_month="2026-06",
        cutoff_date="2026-06-15",
    )


@pytest.mark.asyncio
async def test_promo_processing_rejects_noncanonical_parser_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ImportsService,
        "_validate_promo_actuals_report",
        staticmethod(lambda _content: (1, 1)),
    )

    with pytest.raises(RuntimeError, match="materializarea canonică"):
        await _service().process_promo_actuals(
            content=b"promo",
            filename="promo.xlsx",
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )


@pytest.mark.asyncio
async def test_sales_import_recovers_exact_validated_generation_without_requeue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(
        return_value={
            "id": 214,
            "import_month": "2026-08",
            "filename": "sales.xlsx",
            "is_month_final": False,
            "rows_in_file": 8171,
            "rows_imported": 5674,
            "coverage_report": {"stores_present_count": 77},
            "generation_token": "58daa48f-ceb4-4963-88ab-441a46fedd64",
            "manifest_sha256": "a" * 64,
            "source_spool_path": "/tmp/sales-spool/source.upload",
            "source_artifact_required": False,
            "source_artifact_state": None,
            "source_artifact_sha256": None,
            "source_artifact_bytes": None,
            "manifest": {
                "generation_state": "validated",
                "rows_filtered": 2497,
                "store_count": 77,
                "agent_count": 147,
                "cutoff_date": "2026-08-04",
                "receipt_count": 3870,
                "site_day_count": 296,
                "total_value": "100.00",
                "total_quantity": 10,
                "business_sha256": "b" * 64,
                "anomalies": [],
            },
        }
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(imports_module, "enqueue_sales_import", enqueue)
    stage_spool = MagicMock(return_value=Path("/tmp/sales-spool/source.upload"))
    monkeypatch.setattr(imports_module, "stage_sales_import_spool_file", stage_spool)
    svc = ImportsService(repo=repo, pool=cast(asyncpg.Pool, MagicMock()))

    result = await svc.import_sales(
        _upload(b"same sales bytes", "sales.xlsx"),
        cutoff_date=date(2026, 8, 4),
        requested_by_sub="owner:123",
    )

    assert result.status == "complete"
    assert result.job_id == "sales-staged:214"
    assert result.result is not None
    assert result.result.generation_state == "validated"
    assert result.result.snapshot_id == 214
    assert result.result.rows_imported == 5674
    repo.get_validated_sales_generation.assert_awaited_once_with(
        source_sha256=hashlib.sha256(b"same sales bytes").hexdigest(),
        cutoff_date=date(2026, 8, 4),
    )
    stage_spool.assert_called_once_with(
        b"same sales bytes",
        hashlib.sha256(b"same sales bytes").hexdigest(),
    )
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_sales_import_recovers_from_retained_artifact_without_restaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sha256 = hashlib.sha256(b"same sales bytes").hexdigest()
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(
        return_value={
            "id": 214,
            "import_month": "2026-08",
            "filename": "sales.xlsx",
            "is_month_final": False,
            "rows_in_file": 1,
            "rows_imported": 1,
            "coverage_report": {},
            "generation_token": "58daa48f-ceb4-4963-88ab-441a46fedd64",
            "owner_id": "a8bc1c44-752f-43c7-b0b0-f99b95134a74",
            "manifest_sha256": "a" * 64,
            "source_spool_path": f"/tmp/sales-spool/retained/{source_sha256}.source",
            "source_artifact_required": True,
            "source_artifact_state": "artifact_retained",
            "source_artifact_sha256": source_sha256,
            "source_artifact_bytes": len(b"same sales bytes"),
            "manifest": {"generation_state": "validated"},
        }
    )
    verify = MagicMock(return_value=len(b"same sales bytes"))
    stage = MagicMock()
    monkeypatch.setattr(imports_module, "verify_sales_import_artifact", verify)
    monkeypatch.setattr(imports_module, "stage_sales_import_spool_file", stage)

    result = await ImportsService(
        repo=repo,
        pool=cast(asyncpg.Pool, MagicMock()),
    ).import_sales(
        _upload(b"same sales bytes", "sales.xlsx"),
        cutoff_date=date(2026, 8, 4),
        requested_by_sub="owner:123",
    )

    assert result.status == "complete"
    verify.assert_called_once_with(
        f"/tmp/sales-spool/retained/{source_sha256}.source",
        source_sha256,
        len(b"same sales bytes"),
    )
    stage.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_retained_path", [False, True])
async def test_sales_import_exact_retry_repairs_missing_retention_state(
    monkeypatch: pytest.MonkeyPatch,
    expected_retained_path: bool,
) -> None:
    content = b"same sales bytes"
    source_sha256 = hashlib.sha256(content).hexdigest()
    owner_id = "a8bc1c44-752f-43c7-b0b0-f99b95134a74"
    token = "58daa48f-ceb4-4963-88ab-441a46fedd64"
    repo = MagicMock()
    repo.get_validated_sales_generation = AsyncMock(
        return_value={
            "id": 214,
            "import_month": "2026-08",
            "filename": "sales.xlsx",
            "is_month_final": False,
            "rows_in_file": 1,
            "rows_imported": 1,
            "coverage_report": {},
            "generation_token": token,
            "owner_id": owner_id,
            "manifest_sha256": "a" * 64,
            "source_spool_path": (
                f"/tmp/sales-spool/retained/{source_sha256}.source"
                if expected_retained_path
                else f"/tmp/sales-spool/{source_sha256}.upload"
            ),
            "source_artifact_required": True,
            "source_artifact_state": None,
            "source_artifact_sha256": None,
            "source_artifact_bytes": None,
            "manifest": {"generation_state": "validated"},
        }
    )
    spool_path = Path(f"/tmp/sales-spool/{source_sha256}.upload")
    retained_path = Path(f"/tmp/sales-spool/retained/{source_sha256}.source")
    monkeypatch.setattr(
        imports_module,
        "stage_sales_import_spool_file",
        MagicMock(return_value=spool_path),
    )
    monkeypatch.setattr(
        imports_module,
        "retain_sales_import_spool_file",
        MagicMock(return_value=retained_path),
    )
    attach = AsyncMock()
    mark = AsyncMock()
    monkeypatch.setattr(imports_module, "attach_sales_generation_source", attach)
    monkeypatch.setattr(imports_module, "mark_sales_generation_artifact_retained", mark)
    connection = MagicMock()
    pool = MagicMock()
    pool.acquire.return_value = _AsyncContext(connection)

    result = await ImportsService(
        repo=repo,
        pool=cast(asyncpg.Pool, pool),
    ).import_sales(
        _upload(content, "sales.xlsx"),
        cutoff_date=date(2026, 8, 4),
        requested_by_sub="owner:123",
    )

    assert result.status == "complete"
    attach.assert_awaited_once_with(
        connection,
        snapshot_id=214,
        generation_token=token,
        owner_id=owner_id,
        source_spool_path=str(spool_path),
        source_sha256=source_sha256,
        source_byte_size=len(content),
    )
    mark.assert_awaited_once_with(
        connection,
        snapshot_id=214,
        generation_token=token,
        owner_id=owner_id,
        retained_path=str(retained_path),
        source_sha256=source_sha256,
        source_byte_size=len(content),
    )


@pytest.mark.asyncio
async def test_promote_sales_generation_enqueues_without_web_db_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = MagicMock()
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="promotion:1"))
    monkeypatch.setattr(imports_module, "enqueue_sales_promotion", enqueue)
    monkeypatch.setattr(
        imports_module,
        "get_job_status",
        AsyncMock(return_value=JobResult(job_id="promotion:1", status=JobStatus.QUEUED)),
    )

    result = await _service(pool).promote_sales_generation(
        snapshot_id=7,
        request=_promotion_request(),
        requested_by_sub="owner:123",
    )

    assert result.job_id == "promotion:1"
    assert pool.acquire.call_count == 0
    assert enqueue.await_args is not None
    enqueue.assert_awaited_once_with(
        snapshot_id=7,
        generation_token="a" * 36,
        owner_id=enqueue.await_args.kwargs["owner_id"],
        manifest_sha256="b" * 64,
        requested_by_sub="owner:123",
        override_reason="operator approved promotion",
    )


@pytest.mark.asyncio
async def test_promo_actuals_refuses_config_pointer_changed_before_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_promo_paths(monkeypatch, tmp_path, _promotion_config())
    pointers = iter(["before", "after"])
    monkeypatch.setattr(imports_module, "_promo_pointer_sha256", lambda _: next(pointers))

    with pytest.raises(HTTPException) as exc:
        await _service().process_promo_actuals(
            content=b"report",
            filename="promo.xlsx",
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "config",
    [
        {"promotions": ["not-an-object"]},
        {
            "promotions": [
                {
                    "start_date": "not-a-date",
                    "end_date": "2026-06-30",
                }
            ]
        },
        {
            "promotions": [
                {
                    "start_date": "2026-06-01",
                    "end_date": "2026-06-30",
                    "actuals_cutoff_date": "not-a-date",
                }
            ]
        },
    ],
)
async def test_promo_actuals_fails_closed_for_invalid_promotion_entries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    config: dict[str, object],
) -> None:
    _configure_promo_paths(monkeypatch, tmp_path, config)

    with pytest.raises(HTTPException) as exc:
        await _service().process_promo_actuals(
            content=b"report",
            filename="promo.xlsx",
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )

    assert exc.value.status_code == 500
    assert exc.value.detail == "Configuratia promo este invalida"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code", "detail"),
    [
        (imports_module.PromoGenerationConflictError("stale pointer"), 409, "s-a schimbat"),
        (ValueError("invalid material"), 500, "Configuratia promo este invalida"),
        (OSError("disk full"), 500, "Generatia promo nu a putut fi promovata"),
    ],
)
async def test_promo_actuals_maps_generation_faults_without_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: Exception,
    status_code: int,
    detail: str,
) -> None:
    _configure_promo_paths(monkeypatch, tmp_path, _promotion_config())

    def fail_publish(**_: object) -> tuple[str, str, str]:
        raise failure

    monkeypatch.setattr(imports_module, "_publish_promo_generation", fail_publish)
    with pytest.raises(HTTPException) as exc:
        await _service().process_promo_actuals(
            content=b"report",
            filename="promo.xlsx",
            import_month="2026-06",
            cutoff_date=date(2026, 6, 15),
        )

    assert exc.value.status_code == status_code
    assert detail in str(exc.value.detail)


@pytest.mark.parametrize(
    "dataframe",
    [
        pd.DataFrame({"site_code": ["S1"], "item_code": ["I1"], "promo_qty": ["not-a-number"]}),
        pd.DataFrame({"site_code": [""], "item_code": ["I1"], "promo_qty": [1]}),
    ],
)
def test_validate_promo_actuals_rejects_invalid_decimal_or_missing_positive_key(
    monkeypatch: pytest.MonkeyPatch,
    dataframe: pd.DataFrame,
) -> None:
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: dataframe)

    with pytest.raises(HTTPException) as exc:
        ImportsService._validate_promo_actuals_report(b"report")

    assert exc.value.status_code == 400


def test_validate_promo_actuals_rejects_nonfinite_promo_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = pd.DataFrame(
        {
            "site_code": ["S1"],
            "item_code": ["I1"],
            "promo_qty": [1],
            "promo_value": ["not-a-number"],
        }
    )
    monkeypatch.setattr(imports_module.pd, "read_excel", lambda *args, **kwargs: dataframe)

    with pytest.raises(HTTPException, match="Valorile promo trebuie sa fie finite"):
        ImportsService._validate_promo_actuals_report(b"report")
