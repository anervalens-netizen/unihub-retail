from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from uuid import uuid4

import asyncpg
import pandas as pd
from fastapi import HTTPException, status
from fastapi import UploadFile

from models import (
    ImportCoverageReport,
    ImportHistoryEntry,
    ImportJobStatus,
    ImportResponse,
    PromoActualImportResponse,
    SalesGenerationManifest,
    SalesGenerationPromotionRequest,
)
from schemas.erp_reconciliation import ErpReconciliationResponse
from repositories.imports import ImportsRepository
from services.dashboard_specials import (
    get_special_cards_config_path,
    month_overlaps_period,
    validate_special_cards_config,
)
from services.jobs import (
    JobPublishUncertainError,
    JobResult,
    JobStatus,
    retain_sales_import_spool_file,
    enqueue_grile_check,
    enqueue_campaign_reporting_publication,
    enqueue_promo_actuals_import,
    enqueue_sales_import,
    enqueue_sales_promotion,
    get_job_status,
    remove_sales_import_spool_file,
    stage_sales_import_spool_file,
    verify_sales_import_artifact,
)
from services.sales_generation_flow import (
    attach_sales_generation_source,
    mark_sales_generation_artifact_retained,
)
from services.product_lists import (
    get_data_dir,
    get_repo_root,
    normalize_column_name,
    resolve_path,
)
from services.spreadsheet_safety import (
    PROMO_ACTUALS_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
)
from services.legacy_xls import read_spreadsheet_frame

logger = logging.getLogger(__name__)
DEFAULT_MAX_SALES_UPLOAD_BYTES = 32 * 1024 * 1024
ALLOWED_SALES_EXTENSIONS = frozenset({".xlsx", ".xls"})
PROMO_REPORT_SHEET = "AccesoriPromoLunar"
PROMO_REPORT_SITE_ALIASES = {"sitecode", "site_code", "site"}
PROMO_REPORT_CODE_ALIASES = {"cod", "item_code", "itemcode", "cod_produs"}
PROMO_REPORT_QTY_ALIASES = {"promo_luna_curenta", "promo_qty", "cantitate_promo", "promo"}
PROMO_REPORT_VALUE_ALIASES = {
    "promovaloare_luna_curenta",
    "promo_valoare_luna_curenta",
    "promo_value",
    "valoare_promo",
}


class PromoGenerationConflictError(RuntimeError):
    """Raised when another writer moves the promo pointer during validation."""


class PromoGenerationPointerIntegrityError(PromoGenerationConflictError):
    """Raised when the current promo pointer cannot preserve rollback lineage."""


@dataclass(frozen=True, slots=True)
class PromoActualsParseResult:
    report_rows: int
    promo_units: int
    rows: tuple[dict[str, str | int], ...]

    def __iter__(self):
        # Compatibility for callers that historically unpacked the two totals.
        yield self.report_rows
        yield self.promo_units

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple) and len(other) == 2:
            return (self.report_rows, self.promo_units) == other
        if isinstance(other, PromoActualsParseResult):
            return (
                self.report_rows,
                self.promo_units,
                self.rows,
            ) == (
                other.report_rows,
                other.promo_units,
                other.rows,
            )
        return NotImplemented


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


def _previous_promo_generation_id(pointer_path: Path) -> str | None:
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromoGenerationPointerIntegrityError(
            "Pointerul promo activ este invalid"
        ) from exc
    if not isinstance(pointer, dict):
        raise PromoGenerationPointerIntegrityError("Pointerul promo activ este invalid")
    generation_id = pointer.get("generation_id")
    if (
        not isinstance(generation_id, str)
        or len(generation_id) != 32
        or any(character not in "0123456789abcdef" for character in generation_id)
    ):
        raise PromoGenerationPointerIntegrityError("Pointerul promo activ este invalid")
    return generation_id


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


def _canonical_json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_durable_private_file(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o660)
    try:
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fchmod(descriptor, 0o660)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _promo_pointer_sha256(data_dir: Path) -> str | None:
    pointer_path = data_dir / "promo_generations" / "current.json"
    return (
        hashlib.sha256(pointer_path.read_bytes()).hexdigest()
        if pointer_path.exists()
        else None
    )


def _canonical_promo_actuals_material(
    actuals_material: bytes | None, source_sha256: str
) -> bytes:
    if actuals_material is not None:
        return actuals_material
    payload = {
        "version": 1, "source_sha256": source_sha256,
        "import_month": "", "cutoff_date": "",
        "report_rows": 0, "promo_units": 0, "rows": [],
    }
    return _canonical_json_bytes(payload)


def _publish_promo_generation(
    *,
    data_dir: Path,
    config: dict,
    content: bytes,
    suffix: str,
    material_sha256: str,
    actuals_material: bytes | None = None,
    parser_resources: dict[str, int | float | str | None] | None = None,
    expected_pointer_sha256: str | None = None,
) -> tuple[str, str, str]:
    generation_root = data_dir / "promo_generations"
    source_sha256 = hashlib.sha256(content).hexdigest()
    actuals_material = _canonical_promo_actuals_material(actuals_material, source_sha256)
    parser_resources = dict(parser_resources or {})
    actuals_material_sha256 = hashlib.sha256(actuals_material).hexdigest()
    seed = hashlib.sha256(
        _canonical_json_bytes(config)
        + source_sha256.encode("ascii")
        + material_sha256.encode("ascii")
        + actuals_material_sha256.encode("ascii")
    ).hexdigest()
    generation_id = seed[:32]
    generation_dir = generation_root / generation_id
    actual_name = f"promo_actuals{suffix}"
    actuals_material_name = "promo_actuals.json"
    config_name = "hub_specials.json"
    final_actual_path = generation_dir / actual_name
    final_material_path = generation_dir / actuals_material_name
    for promotion in config["promotions"]:
        if promotion.get("actuals_source_file") == "@GENERATION_ACTUALS@":
            promotion["actuals_source_file"] = str(final_actual_path)
            promotion["actuals_source_sha256"] = source_sha256
            promotion["actuals_material_file"] = str(final_material_path)
            promotion["actuals_material_sha256"] = actuals_material_sha256
    config_bytes = _canonical_json_bytes(config)
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    actuals_manifest: list[dict[str, str]] = []
    actuals_material_manifest: list[dict[str, str]] = []
    for source_file in sorted(
        {
            str(promotion["actuals_source_file"])
            for promotion in config["promotions"]
            if promotion.get("actuals_source_file")
        }
    ):
        source_path = resolve_path(source_file, get_repo_root())
        if source_path == final_actual_path:
            actuals_sha256 = source_sha256
        elif source_path.is_file():
            actuals_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
        else:
            raise ValueError("Sursa actuals promo lipsește")
        actuals_manifest.append({"file": source_file, "sha256": actuals_sha256})
    for material_file in sorted(
        {
            str(promotion["actuals_material_file"])
            for promotion in config["promotions"]
            if promotion.get("actuals_material_file")
        }
    ):
        material_path = resolve_path(material_file, get_repo_root())
        if material_path == final_material_path:
            candidate_sha256 = actuals_material_sha256
        elif material_path.is_file():
            candidate_sha256 = hashlib.sha256(material_path.read_bytes()).hexdigest()
        else:
            raise ValueError("Materializarea actuals promo lipsește")
        actuals_material_manifest.append(
            {"file": material_file, "sha256": candidate_sha256}
        )
    generation_root.mkdir(parents=True, exist_ok=True, mode=0o770)
    staging = generation_root / f".staging-{uuid4()}"
    lock_path = generation_root / ".promotion.lock"
    try:
        with lock_path.open("a+b") as lock_file:
            os.fchmod(lock_file.fileno(), 0o660)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            pointer_path = generation_root / "current.json"
            pointer_bytes = pointer_path.read_bytes() if pointer_path.exists() else None
            if pointer_bytes is not None:
                pointer_path.chmod(0o660)
            current_pointer_sha256 = (
                hashlib.sha256(pointer_bytes).hexdigest()
                if pointer_bytes is not None
                else None
            )
            if current_pointer_sha256 != expected_pointer_sha256:
                raise PromoGenerationConflictError(
                    "Pointerul promo a fost schimbat de alt worker"
                )
            previous_generation_id = _previous_promo_generation_id(pointer_path)
            current_pointer = (
                json.loads(pointer_bytes)
                if pointer_bytes is not None
                else None
            )
            if generation_dir.exists():
                config_path = generation_dir / config_name
                if (
                    not final_actual_path.is_file()
                    or hashlib.sha256(final_actual_path.read_bytes()).hexdigest()
                    != source_sha256
                    or not final_material_path.is_file()
                    or hashlib.sha256(final_material_path.read_bytes()).hexdigest()
                    != actuals_material_sha256
                    or not config_path.is_file()
                    or hashlib.sha256(config_path.read_bytes()).hexdigest()
                    != config_sha256
                ):
                    raise RuntimeError("Coliziune de generație promo")
                final_actual_path.chmod(0o660)
                final_material_path.chmod(0o660)
                config_path.chmod(0o660)
            else:
                staging.mkdir(mode=0o770)
                _write_durable_private_file(staging / actual_name, content)
                _write_durable_private_file(
                    staging / actuals_material_name,
                    actuals_material,
                )
                _write_durable_private_file(staging / config_name, config_bytes)
                _fsync_directory(staging)
                _fsync_directory(generation_root)
                staging.replace(generation_dir)
                _fsync_directory(generation_root)

            expected_pointer_hashes = {
                "version": 2,
                "generation_id": generation_id,
                "config_file": f"{generation_id}/{config_name}",
                "config_sha256": config_sha256,
                "actuals_sha256": source_sha256,
                "actuals": actuals_manifest,
                "actuals_material_sha256": actuals_material_sha256,
                "actuals_materials": actuals_material_manifest,
                "material_sha256": material_sha256,
            }
            if (
                isinstance(current_pointer, dict)
                and current_pointer.get("generation_id") == generation_id
            ):
                if any(
                    current_pointer.get(key) != value
                    for key, value in expected_pointer_hashes.items()
                ) or current_pointer.get("previous_generation_id") == generation_id:
                    raise PromoGenerationPointerIntegrityError(
                        "Pointerul generației promo identice este inconsistent"
                    )
                # Exact retry: keep lineage and promoted_at byte-for-byte.
                return generation_id, config_sha256, source_sha256
            pointer = {
                **expected_pointer_hashes,
                "previous_generation_id": previous_generation_id,
                "parser_resources": parser_resources,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
            pointer_tmp = generation_root / f".current-{uuid4()}.tmp"
            _write_durable_private_file(pointer_tmp, _canonical_json_bytes(pointer))
            _fsync_directory(generation_root)
            pointer_tmp.replace(pointer_path)
            _fsync_directory(generation_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return generation_id, config_sha256, source_sha256


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
                expected_path = str(recovered["source_spool_path"])
                artifact_required = bool(recovered["source_artifact_required"])
                artifact_state = recovered["source_artifact_state"]
                if artifact_required and artifact_state == "artifact_retained":
                    await asyncio.to_thread(
                        verify_sales_import_artifact,
                        expected_path,
                        source_sha256,
                        len(content),
                    )
                else:
                    spool_path = await asyncio.to_thread(
                        stage_sales_import_spool_file,
                        content,
                        source_sha256,
                    )
                    canonical_retained_path = (
                        spool_path.parent / "retained" / f"{source_sha256}.source"
                    )
                    allowed_recovery_paths = (
                        {str(spool_path), str(canonical_retained_path)}
                        if artifact_required
                        else {str(spool_path)}
                    )
                    if expected_path not in allowed_recovery_paths:
                        await asyncio.to_thread(
                            remove_sales_import_spool_file,
                            spool_path,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                "Generatia validata foloseste alta cale de sursa; "
                                "recovery automat refuzat"
                            ),
                        )
                    if artifact_required:
                        generation_token = str(recovered["generation_token"])
                        owner_id = str(recovered["owner_id"])
                        async with self.pool.acquire() as conn:
                            await attach_sales_generation_source(
                                conn,
                                snapshot_id=int(recovered["id"]),
                                generation_token=generation_token,
                                owner_id=owner_id,
                                source_spool_path=str(spool_path),
                                source_sha256=source_sha256,
                                source_byte_size=len(content),
                            )
                        retained_path = await asyncio.to_thread(
                            retain_sales_import_spool_file,
                            spool_path,
                            import_month=str(recovered["import_month"]),
                            snapshot_id=int(recovered["id"]),
                            expected_digest=source_sha256,
                            expected_bytes=len(content),
                        )
                        async with self.pool.acquire() as conn:
                            await mark_sales_generation_artifact_retained(
                                conn,
                                snapshot_id=int(recovered["id"]),
                                generation_token=generation_token,
                                owner_id=owner_id,
                                retained_path=str(retained_path),
                                source_sha256=source_sha256,
                                source_byte_size=len(content),
                            )
                manifest = recovered["manifest"]
                if isinstance(manifest, str):
                    manifest = json.loads(manifest)
                coverage_report = recovered["coverage_report"]
                if isinstance(coverage_report, str):
                    coverage_report = json.loads(coverage_report)
                manifest = dict(manifest or {})
                return ImportJobStatus(
                    job_id=f"sales-staged:{int(recovered['id'])}",
                    status="complete",
                    result=ImportResponse(
                        import_month=str(recovered["import_month"]),
                        rows_in_file=int(recovered["rows_in_file"] or 0),
                        rows_imported=int(recovered["rows_imported"] or 0),
                        rows_filtered=int(manifest.get("rows_filtered", 0)),
                        store_count=int(manifest.get("store_count", 0)),
                        agent_count=int(manifest.get("agent_count", 0)),
                        snapshot_id=int(recovered["id"]),
                        filename=str(recovered["filename"]),
                        is_month_final=bool(recovered["is_month_final"]),
                        coverage_report=ImportCoverageReport.model_validate(coverage_report or {}),
                        generation_state="validated",
                        generation_token=str(recovered["generation_token"]),
                        manifest_sha256=str(recovered["manifest_sha256"]),
                        manifest=SalesGenerationManifest.model_validate(manifest),
                    ),
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
        try:
            config_path = get_special_cards_config_path()
            if _promo_pointer_sha256(data_dir) != expected_pointer_sha256:
                raise PromoGenerationConflictError
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except PromoGenerationConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Configurația promo s-a schimbat; reîncarcă și reîncearcă",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuratia promo nu poate fi citita",
            ) from exc
        if not isinstance(config, dict) or not isinstance(config.get("promotions"), list):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuratia promo este invalida",
            )

        updated_promotions = 0
        for promotion in config["promotions"]:
            if not isinstance(promotion, dict):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Configuratia promo este invalida",
                )
            try:
                start_date = date.fromisoformat(str(promotion.get("start_date", "")))
                end_date = date.fromisoformat(str(promotion.get("end_date", "")))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Configuratia promo este invalida",
                ) from None
            if not month_overlaps_period(import_month, start_date, end_date):
                continue
            previous_cutoff = promotion.get("actuals_cutoff_date")
            try:
                previous_cutoff_date = (
                    date.fromisoformat(str(previous_cutoff))
                    if previous_cutoff
                    else None
                )
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Configuratia promo este invalida",
                ) from None
            if previous_cutoff_date and cutoff_date < previous_cutoff_date:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Cutoff-ul promo nu poate regresa față de generația "
                        "curentă"
                    ),
                )
            promotion["actuals_source_file"] = "@GENERATION_ACTUALS@"
            promotion["actuals_sheet"] = PROMO_REPORT_SHEET
            promotion["actuals_cutoff_date"] = cutoff_date.isoformat()
            updated_promotions += 1
        if updated_promotions == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nu exista promotii configurate pentru luna selectata",
            )

        try:
            _definitions, material_sha256 = validate_special_cards_config(config)
            generation_id, config_sha256, source_sha256 = _publish_promo_generation(
                data_dir=data_dir,
                config=config,
                content=content,
                suffix=Path(filename).suffix.casefold(),
                material_sha256=material_sha256,
                actuals_material=actuals_material,
                parser_resources=measurement.as_dict(),
                expected_pointer_sha256=expected_pointer_sha256,
            )
        except PromoGenerationPointerIntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Configuratia promo activa este invalida; importul a fost oprit",
            ) from exc
        except PromoGenerationConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Configurația promo s-a schimbat; reîncarcă și reîncearcă",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuratia promo este invalida",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Generatia promo nu a putut fi promovata",
            ) from exc
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
        try:
            dataframe = read_spreadsheet_frame(
                content,
                sheet_name=sheet_name,
                limits=PROMO_ACTUALS_SPREADSHEET_LIMITS,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Raportul trebuie sa contina foaia {sheet_name}",
            ) from exc
        columns = {normalize_column_name(column): str(column) for column in dataframe.columns}
        site_column = next((columns[key] for key in PROMO_REPORT_SITE_ALIASES if key in columns), None)
        code_column = next((columns[key] for key in PROMO_REPORT_CODE_ALIASES if key in columns), None)
        promo_column = next((columns[key] for key in PROMO_REPORT_QTY_ALIASES if key in columns), None)
        promo_value_column = next(
            (columns[key] for key in PROMO_REPORT_VALUE_ALIASES if key in columns),
            None,
        )
        if not site_column or not code_column or not promo_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul trebuie sa contina coloanele SiteCode, Cod si Promo Luna Curenta",
            )
        net_units: dict[tuple[str, str], int] = {}
        net_values: dict[tuple[str, str], Decimal] = {}
        for index, raw_value in dataframe[promo_column].items():
            if raw_value is None or str(raw_value).strip() == "":
                continue
            site_code = str(dataframe.at[index, site_column]).strip()
            item_code = str(dataframe.at[index, code_column]).strip()
            try:
                quantity_value = Decimal(str(raw_value).strip())
            except (InvalidOperation, ValueError):
                quantity_value = Decimal("NaN")
            if (
                not quantity_value.is_finite()
                or quantity_value != quantity_value.to_integral_value()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cantitatile promo trebuie sa fie intregi finite",
                )
            quantity = int(quantity_value)
            if quantity == 0:
                continue
            if not site_code or site_code.casefold() == "nan" or not item_code or item_code.casefold() == "nan":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Fiecare cantitate promo nenula necesita SiteCode si Cod",
                )
            key = (site_code, item_code)
            net_units[key] = net_units.get(key, 0) + quantity
            if promo_value_column is not None:
                raw_promo_value = dataframe.at[index, promo_value_column]
                promo_value_text = (
                    ""
                    if raw_promo_value is None or pd.isna(raw_promo_value)
                    else str(raw_promo_value).strip()
                )
                try:
                    promo_value = Decimal(promo_value_text or "0")
                except (InvalidOperation, ValueError):
                    promo_value = Decimal("NaN")
                if not promo_value.is_finite():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Valorile promo trebuie sa fie finite",
                    )
                net_values[key] = net_values.get(key, Decimal("0")) + promo_value.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
        positive_rows_list: list[dict[str, str | int]] = []
        positive_net_units: list[int] = []
        for (site_code, item_code), quantity in sorted(net_units.items()):
            if quantity <= 0:
                continue
            positive_net_units.append(quantity)
            positive_rows_list.append(
                {
                    "site_code": site_code,
                    "item_code": item_code,
                    "quantity": quantity,
                    "value": f"{net_values.get((site_code, item_code), Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}",
                }
            )
        positive_rows = tuple(positive_rows_list)
        if not positive_net_units:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul nu contine unitati promo nete pozitive",
            )
        return PromoActualsParseResult(
            report_rows=len(positive_rows),
            promo_units=sum(positive_net_units),
            rows=positive_rows,
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
