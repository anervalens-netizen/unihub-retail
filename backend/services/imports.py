from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Literal
from uuid import uuid4

import asyncpg
import pandas as pd
from fastapi import HTTPException, UploadFile, status

from models import (
    ImportCoverageReport,
    ImportHistoryEntry,
    ImportJobStatus,
    ImportResponse,
    PromoActualImportResponse,
    SalesGenerationManifest,
    SalesGenerationPromotionRequest,
)
from repositories.imports import ImportsRepository
from schemas.erp_reconciliation import ErpReconciliationResponse
from services.dashboard_specials import (
    get_special_cards_config_path,
    month_overlaps_period,
    validate_special_cards_config,
)
from services.jobs import (
    JobPublishUncertainError,
    JobResult,
    JobStatus,
    enqueue_campaign_reporting_publication,
    enqueue_grile_check,
    enqueue_promo_actuals_import,
    enqueue_sales_import,
    enqueue_sales_promotion,
    get_job_status,
    remove_sales_import_spool_file,
    retain_sales_import_spool_file,
    stage_sales_import_spool_file,
    verify_sales_import_artifact,
)
from services.legacy_xls import read_spreadsheet_frame
from services.product_lists import get_data_dir
from services.promo_actuals_parser import (
    PROMO_REPORT_SHEET,
    PromoActualsParseResult,
    validate_promo_actuals_report,
)
from services.promo_actuals_processing import (
    load_promo_config,
    publish_promo_config,
    update_promo_config,
)
from services.promo_generation_publisher import (
    PromoGenerationConflictError,
    PromoGenerationPointerIntegrityError,
    _canonical_json_bytes,
    _promo_pointer_sha256,
    _publish_promo_generation,
)
from services.sales_generation_flow import (
    attach_sales_generation_source,
    mark_sales_generation_artifact_retained,
)
from services.sales_import_reupload import recover_validated_sales_import
from services.spreadsheet_safety import (
    PROMO_ACTUALS_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
)


logger = logging.getLogger(__name__)
DEFAULT_MAX_SALES_UPLOAD_BYTES = 32 * 1024 * 1024
ALLOWED_SALES_EXTENSIONS = frozenset({".xlsx", ".xls"})



def _promo_actuals_material_bytes(
    parsed: PromoActualsParseResult,
    *,
    source_sha256: str,
    import_month: str,
    cutoff_date: date,
) -> bytes:
    return _canonical_json_bytes(
        {
            "version": 1,
            "source_sha256": source_sha256,
            "import_month": import_month,
            "cutoff_date": cutoff_date.isoformat(),
            "report_rows": parsed.report_rows,
            "promo_units": parsed.promo_units,
            "rows": list(parsed.rows),
        }
    )


def _to_public_import_status(result: JobResult) -> ImportJobStatus:
    if result.status in {JobStatus.BACKEND_UNAVAILABLE, JobStatus.UNKNOWN}:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job status unavailable",
        )
    job_kind: Literal["sales", "promo_actuals", "erp_reconciliation"] = (
        "promo_actuals"
        if result.job_id.startswith("promo-actuals:")
        else "erp_reconciliation"
        if result.job_id.startswith("erp-reconciliation:")
        else "sales"
    )
    payload = ImportResponse(**result.result) if result.result and job_kind == "sales" else None
    promo_payload = PromoActualImportResponse(**result.result) if result.result and job_kind == "promo_actuals" else None
    erp_payload = (
        ErpReconciliationResponse(**result.result)
        if result.result and job_kind == "erp_reconciliation"
        else None
    )
    return ImportJobStatus(
        job_id=result.job_id,
        status=result.status.value,
        job_kind=job_kind,
        result=payload,
        promo_result=promo_payload,
        erp_result=erp_payload,
        error=result.error,
    )


async def trigger_grile_check_after_import(import_month: str, snapshot_id: int | None) -> None:
    """Best-effort: enqueue verificarea grilelor dupa un import reusit.

    NU propaga niciodata exceptii — importul de vanzari nu trebuie sa fie
    afectat daca enqueue-ul esueaza (Valkey down etc.).
    """
    try:
        result = await enqueue_grile_check(
            month=import_month,
            source="auto",
            source_snapshot_id=snapshot_id,
            triggered_by_sub="system:sales-import",
            sales_import_authority=True,
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


async def trigger_campaign_reporting_publication(
    import_month: str,
    *,
    requested_by_sub: str,
    reason: str,
) -> None:
    """Best-effort hook after a campaign input becomes authoritative.

    Publishing is bounded to the imports worker; an unavailable queue must not
    roll back a successful sales/promo generation.
    """
    try:
        job = await enqueue_campaign_reporting_publication(
            month=import_month,
            requested_by_sub=requested_by_sub,
            reason=reason,
        )
        logger.info(
            "campaign reporting publication queued month=%s job=%s",
            import_month,
            job.job_id,
        )
    except Exception:  # noqa: BLE001 -- source promotion stays successful
        logger.exception(
            "enqueue campaign reporting publication esuat pentru %s",
            import_month,
        )


async def get_public_import_job_status(job_id: str) -> ImportJobStatus:
    """Canonical typed projection for every public import-worker job."""
    return _to_public_import_status(await get_job_status(job_id))


class ImportsService:
    def __init__(self, repo: ImportsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def import_sales(
        self,
        file: UploadFile,
        *,
        cutoff_date: date | None = None,
        requested_by_sub: str = "unknown",
    ) -> ImportJobStatus:
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
        if cutoff_date is not None:
            source_sha256 = hashlib.sha256(content).hexdigest()
            recovered = await self.repo.get_validated_sales_generation(
                source_sha256=source_sha256,
                cutoff_date=cutoff_date,
            )
            if recovered is not None:
                return await recover_validated_sales_import(
                    recovered,
                    pool=self.pool,
                    content=content,
                    source_sha256=source_sha256,
                    verify=verify_sales_import_artifact,
                    stage=stage_sales_import_spool_file,
                    remove=remove_sales_import_spool_file,
                    retain=retain_sales_import_spool_file,
                    attach=attach_sales_generation_source,
                    mark_retained=mark_sales_generation_artifact_retained,
                )

        job = await enqueue_sales_import(
            content,
            filename=file.filename,
            cutoff_date=cutoff_date.isoformat() if cutoff_date else None,
            requested_by_sub=requested_by_sub,
        )
        job_status = await get_job_status(job.job_id)
        return _to_public_import_status(job_status)

    async def promote_sales_generation(
        self,
        *,
        snapshot_id: int,
        request: SalesGenerationPromotionRequest,
        requested_by_sub: str,
    ) -> ImportJobStatus:
        new_owner_id = str(uuid4())
        job = await enqueue_sales_promotion(
            snapshot_id=snapshot_id,
            generation_token=request.generation_token,
            owner_id=new_owner_id,
            manifest_sha256=request.manifest_sha256,
            requested_by_sub=requested_by_sub,
            override_reason=request.override_reason,
        )
        job_status = await get_job_status(job.job_id)
        return _to_public_import_status(job_status)

    async def import_promo_actuals(
        self,
        *,
        file: UploadFile,
        import_month: str,
        cutoff_date: date,
    ) -> ImportJobStatus:
        if not file.filename or Path(file.filename).suffix.casefold() not in ALLOWED_SALES_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul promo accepta numai fisiere .xlsx sau .xls",
            )
        try:
            month_start = date.fromisoformat(f"{import_month}-01")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Luna este invalida") from exc
        if cutoff_date < month_start or cutoff_date.strftime("%Y-%m") != import_month:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Data cutoff trebuie sa fie in luna selectata",
            )

        max_bytes = int(os.getenv("MAX_PROMO_REPORT_UPLOAD_BYTES", str(DEFAULT_MAX_SALES_UPLOAD_BYTES)))
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Raportul depaseste limita de {max_bytes // (1024 * 1024)} MB",
            )
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Raportul este gol")
        job = await enqueue_promo_actuals_import(
            content,
            filename=file.filename,
            import_month=import_month,
            cutoff_date=cutoff_date.isoformat(),
        )
        return _to_public_import_status(await get_job_status(job.job_id))

    async def process_promo_actuals(
        self,
        *,
        content: bytes,
        filename: str,
        import_month: str,
        cutoff_date: date,
    ) -> PromoActualImportResponse:
        measurement = SpreadsheetParserMeasurement("promo_actuals")
        try:
            with measurement:
                preflight = validate_spreadsheet_upload(
                    content,
                    Path(filename).suffix,
                    limits=PROMO_ACTUALS_SPREADSHEET_LIMITS,
                )
                measurement.set_preflight(preflight)
                parsed = await asyncio.to_thread(
                    self._validate_promo_actuals_report,
                    content,
                )
                if not isinstance(parsed, PromoActualsParseResult):
                    raise RuntimeError("Parserul promo nu a produs materializarea canonică")
                measurement.set_rows(parsed.report_rows)
        except SpreadsheetUploadError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        data_dir = get_data_dir()
        expected_pointer_sha256 = _promo_pointer_sha256(data_dir)
        report_rows, promo_units = parsed
        source_sha256 = hashlib.sha256(content).hexdigest()
        actuals_material = _promo_actuals_material_bytes(
            parsed,
            source_sha256=source_sha256,
            import_month=import_month,
            cutoff_date=cutoff_date,
        )
        config = load_promo_config(
            data_dir=data_dir,
            expected_pointer_sha256=expected_pointer_sha256,
            config_path=get_special_cards_config_path(),
            pointer_sha256=_promo_pointer_sha256,
        )
        updated_promotions = update_promo_config(
            config,
            import_month=import_month,
            cutoff_date=cutoff_date,
            sheet_name=PROMO_REPORT_SHEET,
        )
        (
            generation_id,
            config_sha256,
            source_sha256,
            material_sha256,
        ) = publish_promo_config(
            data_dir=data_dir,
            config=config,
            content=content,
            suffix=Path(filename).suffix.casefold(),
            actuals_material=actuals_material,
            parser_resources=measurement.as_dict(),
            expected_pointer_sha256=expected_pointer_sha256,
            validate_config=validate_special_cards_config,
            publisher=_publish_promo_generation,
        )
        logger.info(
            "promo actuals promoted month=%s cutoff=%s rows=%s units=%s generation=%s",
            import_month,
            cutoff_date,
            report_rows,
            promo_units,
            generation_id,
        )
        await trigger_campaign_reporting_publication(
            import_month,
            requested_by_sub="system:promo-actuals",
            reason=f"promo_actuals_generation:{generation_id}",
        )
        return PromoActualImportResponse(
            import_month=import_month,
            cutoff_date=cutoff_date,
            filename=filename,
            report_rows=report_rows,
            promo_units=promo_units,
            updated_promotions=updated_promotions,
            generation_id=generation_id,
            config_sha256=config_sha256,
            source_sha256=source_sha256,
            material_sha256=material_sha256,
        )

    @staticmethod
    def _validate_promo_actuals_report(
        content: bytes,
        *,
        sheet_name: str = PROMO_REPORT_SHEET,
    ) -> PromoActualsParseResult:
        return validate_promo_actuals_report(
            content,
            sheet_name=sheet_name,
            reader=read_spreadsheet_frame,
            reader_limits=PROMO_ACTUALS_SPREADSHEET_LIMITS,
        )


    async def get_import_job_status(self, job_id: str) -> ImportJobStatus:
        return await get_public_import_job_status(job_id)

    async def get_import_history(self) -> list[ImportHistoryEntry]:
        rows = await self.repo.get_import_history()
        history: list[ImportHistoryEntry] = []
        for row in rows:
            payload = dict(row)
            report = payload.get("coverage_report")
            if isinstance(report, str):
                payload["coverage_report"] = json.loads(report)
            history.append(ImportHistoryEntry(**payload))
        return history
