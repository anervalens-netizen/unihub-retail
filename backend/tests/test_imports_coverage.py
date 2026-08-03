from __future__ import annotations

import hashlib
import json
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
from services.jobs import JobPublishUncertainError, JobResult, JobStatus
from services.sales_generation import SalesGenerationConflictError


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


class _PromotionConnection:
    def transaction(self) -> _AsyncContext:
        return _AsyncContext(None)


class _PromotionPool:
    def __init__(self) -> None:
        self.connection = _PromotionConnection()

    def acquire(self) -> _AsyncContext:
        return _AsyncContext(self.connection)


def _service(pool: object | None = None) -> ImportsService:
    return ImportsService(
        repo=MagicMock(),
        pool=cast(asyncpg.Pool, pool if pool is not None else MagicMock()),
    )


def _upload(content: bytes = b"report", filename: str | None = "promo.xlsx") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


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
        staticmethod(lambda _: (1, 1)),
    )


def _promotion_request() -> SalesGenerationPromotionRequest:
    return SalesGenerationPromotionRequest(
        generation_token="a" * 36,
        manifest_sha256="b" * 64,
        override_reason="operator approved promotion",
    )


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


def test_publish_promo_generation_reuses_exact_generation_and_rejects_collision(
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
    second = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="d" * 64,
        expected_pointer_sha256=imports_module._promo_pointer_sha256(data_dir),
    )

    assert second == first
    generation_dir = data_dir / "promo_generations" / first[0]
    (generation_dir / "promo_actuals.xlsx").write_bytes(b"tampered")

    with pytest.raises(RuntimeError, match="Coliziune de generație promo"):
        imports_module._publish_promo_generation(
            data_dir=data_dir,
            config=_promotion_config(),
            content=b"uploaded-actuals",
            suffix=".xlsx",
            material_sha256="d" * 64,
            expected_pointer_sha256=imports_module._promo_pointer_sha256(data_dir),
        )


def test_publish_promo_generation_recovers_from_malformed_previous_pointer(
    tmp_path: Path,
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
    pointer_path = data_dir / "promo_generations" / "current.json"
    pointer_path.write_text("not-json", encoding="utf-8")
    malformed_sha256 = imports_module._promo_pointer_sha256(data_dir)

    second = imports_module._publish_promo_generation(
        data_dir=data_dir,
        config=_promotion_config(),
        content=b"uploaded-actuals",
        suffix=".xlsx",
        material_sha256="e" * 64,
        expected_pointer_sha256=malformed_sha256,
    )

    assert second == first
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["previous_generation_id"] is None


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
async def test_promote_sales_generation_claims_then_enqueues_with_same_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _PromotionPool()
    claim = AsyncMock(return_value="previous-owner")
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="promotion:1"))
    monkeypatch.setattr(imports_module, "claim_validated_sales_generation", claim)
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
    claim_args = claim.await_args
    assert claim_args is not None
    owner_id = claim_args.kwargs["new_owner_id"]
    enqueue.assert_awaited_once_with(
        snapshot_id=7,
        generation_token="a" * 36,
        owner_id=owner_id,
        manifest_sha256="b" * 64,
        requested_by_sub="owner:123",
        override_reason="operator approved promotion",
    )


@pytest.mark.asyncio
async def test_promote_sales_generation_maps_claim_conflict_before_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueue = AsyncMock()
    monkeypatch.setattr(
        imports_module,
        "claim_validated_sales_generation",
        AsyncMock(side_effect=SalesGenerationConflictError("stale generation")),
    )
    monkeypatch.setattr(imports_module, "enqueue_sales_promotion", enqueue)

    with pytest.raises(HTTPException) as exc:
        await _service(_PromotionPool()).promote_sales_generation(
            snapshot_id=7,
            request=_promotion_request(),
            requested_by_sub="owner:123",
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "stale generation"
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("restore_fails", [False, True])
async def test_promote_sales_generation_restores_claim_after_enqueue_fault(
    monkeypatch: pytest.MonkeyPatch,
    restore_fails: bool,
) -> None:
    claim = AsyncMock(return_value="previous-owner")
    restore = AsyncMock(
        side_effect=OSError("restore failed") if restore_fails else None
    )
    monkeypatch.setattr(imports_module, "claim_validated_sales_generation", claim)
    monkeypatch.setattr(
        imports_module,
        "enqueue_sales_promotion",
        AsyncMock(side_effect=OSError("enqueue failed")),
    )
    monkeypatch.setattr(imports_module, "restore_sales_generation_claim", restore)

    with pytest.raises(OSError, match="enqueue failed"):
        await _service(_PromotionPool()).promote_sales_generation(
            snapshot_id=7,
            request=_promotion_request(),
            requested_by_sub="owner:123",
        )

    restore.assert_awaited_once()
    restore_args = restore.await_args
    claim_args = claim.await_args
    assert restore_args is not None
    assert claim_args is not None
    assert restore_args.kwargs["current_owner_id"] == claim_args.kwargs["new_owner_id"]
    assert restore_args.kwargs["previous_owner_id"] == "previous-owner"


@pytest.mark.asyncio
async def test_promote_sales_generation_does_not_restore_uncertain_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restore = AsyncMock()
    monkeypatch.setattr(
        imports_module,
        "claim_validated_sales_generation",
        AsyncMock(return_value="previous-owner"),
    )
    monkeypatch.setattr(
        imports_module,
        "enqueue_sales_promotion",
        AsyncMock(side_effect=JobPublishUncertainError(job_id="promotion:unknown")),
    )
    monkeypatch.setattr(imports_module, "restore_sales_generation_claim", restore)

    with pytest.raises(JobPublishUncertainError) as exc:
        await _service(_PromotionPool()).promote_sales_generation(
            snapshot_id=7,
            request=_promotion_request(),
            requested_by_sub="owner:123",
        )

    assert exc.value.detail == {
        "status": "unknown",
        "job_id": "promotion:unknown",
        "operation_id": None,
    }
    restore.assert_not_awaited()


@pytest.mark.asyncio
async def test_promo_actuals_refuses_config_pointer_changed_before_read(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_promo_paths(monkeypatch, tmp_path, _promotion_config())
    pointers = iter(["before", "after"])
    monkeypatch.setattr(imports_module, "_promo_pointer_sha256", lambda _: next(pointers))

    with pytest.raises(HTTPException) as exc:
        await _service().import_promo_actuals(
            file=_upload(), import_month="2026-06", cutoff_date=date(2026, 6, 15)
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
        await _service().import_promo_actuals(
            file=_upload(), import_month="2026-06", cutoff_date=date(2026, 6, 15)
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
        await _service().import_promo_actuals(
            file=_upload(), import_month="2026-06", cutoff_date=date(2026, 6, 15)
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
