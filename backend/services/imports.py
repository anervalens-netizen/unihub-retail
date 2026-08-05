from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import logging
import os
import shutil
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import asyncpg
import pandas as pd
from fastapi import HTTPException, status
from fastapi import UploadFile

from models import (
    ImportHistoryEntry,
    ImportJobStatus,
    ImportResponse,
    PromoActualImportResponse,
    SalesGenerationPromotionRequest,
)
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
    enqueue_grile_check,
    enqueue_sales_import,
    enqueue_sales_promotion,
    get_job_status,
    remove_sales_import_spool_file,
    stage_sales_import_spool_file,
)
from services.product_lists import (
    get_data_dir,
    get_repo_root,
    normalize_column_name,
    resolve_path,
)
from services.sales_generation import SalesGenerationConflictError
from services.sales_generation_flow import (
    claim_validated_sales_generation,
    restore_sales_generation_claim,
)

logger = logging.getLogger(__name__)
DEFAULT_MAX_SALES_UPLOAD_BYTES = 32 * 1024 * 1024
ALLOWED_SALES_EXTENSIONS = frozenset({".xlsx", ".xls"})
PROMO_REPORT_SHEET = "AccesoriPromoLunar"
PROMO_REPORT_SITE_ALIASES = {"sitecode", "site_code", "site"}
PROMO_REPORT_CODE_ALIASES = {"cod", "item_code", "itemcode", "cod_produs"}
PROMO_REPORT_QTY_ALIASES = {"promo_luna_curenta", "promo_qty", "cantitate_promo", "promo"}


class PromoGenerationConflictError(RuntimeError):
    """Raised when another writer moves the promo pointer during validation."""


class PromoGenerationPointerIntegrityError(PromoGenerationConflictError):
    """Raised when the current promo pointer cannot preserve rollback lineage."""


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
    payload = ImportResponse(**result.result) if result.result else None
    return ImportJobStatus(
        job_id=result.job_id,
        status=result.status.value,
        result=payload,
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


def _promo_pointer_sha256(data_dir: Path) -> str | None:
    pointer_path = data_dir / "promo_generations" / "current.json"
    return (
        hashlib.sha256(pointer_path.read_bytes()).hexdigest()
        if pointer_path.exists()
        else None
    )


def _publish_promo_generation(
    *,
    data_dir: Path,
    config: dict,
    content: bytes,
    suffix: str,
    material_sha256: str,
    expected_pointer_sha256: str | None,
) -> tuple[str, str, str]:
    generation_root = data_dir / "promo_generations"
    source_sha256 = hashlib.sha256(content).hexdigest()
    seed = hashlib.sha256(
        _canonical_json_bytes(config)
        + source_sha256.encode("ascii")
        + material_sha256.encode("ascii")
    ).hexdigest()
    generation_id = seed[:32]
    generation_dir = generation_root / generation_id
    actual_name = f"promo_actuals{suffix}"
    config_name = "hub_specials.json"
    final_actual_path = generation_dir / actual_name
    for promotion in config["promotions"]:
        if promotion.get("actuals_source_file") == "@GENERATION_ACTUALS@":
            promotion["actuals_source_file"] = str(final_actual_path)
    config_bytes = _canonical_json_bytes(config)
    config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    actuals_manifest: list[dict[str, str]] = []
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

    generation_root.mkdir(parents=True, exist_ok=True)
    staging = generation_root / f".staging-{uuid4()}"
    lock_path = generation_root / ".promotion.lock"
    try:
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            pointer_path = generation_root / "current.json"
            current_pointer_sha256 = (
                hashlib.sha256(pointer_path.read_bytes()).hexdigest()
                if pointer_path.exists()
                else None
            )
            if current_pointer_sha256 != expected_pointer_sha256:
                raise PromoGenerationConflictError(
                    "Pointerul promo a fost schimbat de alt worker"
                )
            previous_generation_id = _previous_promo_generation_id(pointer_path)
            if generation_dir.exists():
                config_path = generation_dir / config_name
                if (
                    not final_actual_path.is_file()
                    or hashlib.sha256(final_actual_path.read_bytes()).hexdigest()
                    != source_sha256
                    or not config_path.is_file()
                    or hashlib.sha256(config_path.read_bytes()).hexdigest()
                    != config_sha256
                ):
                    raise RuntimeError("Coliziune de generație promo")
            else:
                staging.mkdir(mode=0o700)
                (staging / actual_name).write_bytes(content)
                (staging / config_name).write_bytes(config_bytes)
                staging.replace(generation_dir)
            pointer = {
                "version": 1,
                "generation_id": generation_id,
                "previous_generation_id": previous_generation_id,
                "config_file": f"{generation_id}/{config_name}",
                "config_sha256": config_sha256,
                "actuals_sha256": source_sha256,
                "actuals": actuals_manifest,
                "material_sha256": material_sha256,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
            pointer_tmp = generation_root / f".current-{uuid4()}.tmp"
            pointer_tmp.write_bytes(_canonical_json_bytes(pointer))
            pointer_tmp.replace(pointer_path)
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


class ImportsService:
    def __init__(self, repo: ImportsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def import_sales(
        self,
        file: UploadFile,
        *,
        cutoff_date: date | None = None,
        requested_by_sub: str = "legacy-direct",
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
                spool_path = await asyncio.to_thread(
                    stage_sales_import_spool_file,
                    content,
                    source_sha256,
                )
                if str(spool_path) != str(recovered["source_spool_path"]):
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
                        coverage_report=dict(coverage_report or {}),
                        generation_state="validated",
                        generation_token=str(recovered["generation_token"]),
                        manifest_sha256=str(recovered["manifest_sha256"]),
                        manifest=manifest,
                    ),
                )

        if cutoff_date is None and requested_by_sub == "legacy-direct":
            job = await enqueue_sales_import(content, filename=file.filename)
        else:
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
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    previous_owner_id = await claim_validated_sales_generation(
                        conn,
                        snapshot_id=snapshot_id,
                        generation_token=request.generation_token,
                        expected_manifest_sha256=request.manifest_sha256,
                        new_owner_id=new_owner_id,
                    )
        except SalesGenerationConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        try:
            job = await enqueue_sales_promotion(
                snapshot_id=snapshot_id,
                generation_token=request.generation_token,
                owner_id=new_owner_id,
                manifest_sha256=request.manifest_sha256,
                requested_by_sub=requested_by_sub,
                override_reason=request.override_reason,
            )
        except JobPublishUncertainError:
            raise
        except Exception:
            try:
                async with self.pool.acquire() as conn:
                    async with conn.transaction():
                        await restore_sales_generation_claim(
                            conn,
                            snapshot_id=snapshot_id,
                            generation_token=request.generation_token,
                            current_owner_id=new_owner_id,
                            previous_owner_id=previous_owner_id,
                        )
            except Exception:
                logger.exception(
                    "Failed to restore sales generation claim snapshot=%s",
                    snapshot_id,
                )
            raise
        job_status = await get_job_status(job.job_id)
        return _to_public_import_status(job_status)

    async def import_promo_actuals(
        self,
        *,
        file: UploadFile,
        import_month: str,
        cutoff_date: date,
    ) -> PromoActualImportResponse:
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

        data_dir = get_data_dir()
        expected_pointer_sha256 = _promo_pointer_sha256(data_dir)
        report_rows, promo_units = await asyncio.to_thread(
            self._validate_promo_actuals_report,
            content,
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
                suffix=Path(file.filename).suffix.casefold(),
                material_sha256=material_sha256,
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
        return PromoActualImportResponse(
            import_month=import_month,
            cutoff_date=cutoff_date,
            filename=file.filename,
            report_rows=report_rows,
            promo_units=promo_units,
            updated_promotions=updated_promotions,
            generation_id=generation_id,
            config_sha256=config_sha256,
            source_sha256=source_sha256,
            material_sha256=material_sha256,
        )

    @staticmethod
    def _validate_promo_actuals_report(content: bytes) -> tuple[int, int]:
        try:
            dataframe = pd.read_excel(
                BytesIO(content),
                sheet_name=PROMO_REPORT_SHEET,
                keep_default_na=False,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Raportul trebuie sa contina foaia {PROMO_REPORT_SHEET}",
            ) from exc
        columns = {normalize_column_name(column): str(column) for column in dataframe.columns}
        site_column = next((columns[key] for key in PROMO_REPORT_SITE_ALIASES if key in columns), None)
        code_column = next((columns[key] for key in PROMO_REPORT_CODE_ALIASES if key in columns), None)
        promo_column = next((columns[key] for key in PROMO_REPORT_QTY_ALIASES if key in columns), None)
        if not site_column or not code_column or not promo_column:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul trebuie sa contina coloanele SiteCode, Cod si Promo Luna Curenta",
            )
        net_units: dict[tuple[str, str], int] = {}
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
        positive_net_units = [quantity for quantity in net_units.values() if quantity > 0]
        if not positive_net_units:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul nu contine unitati promo nete pozitive",
            )
        return len(positive_net_units), sum(positive_net_units)

    async def get_import_job_status(self, job_id: str) -> ImportJobStatus:
        result = await get_job_status(job_id)
        return _to_public_import_status(result)

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
