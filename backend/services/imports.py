from __future__ import annotations

import logging
import os
import hashlib
import json
from datetime import date
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, status
from fastapi import UploadFile
import pandas as pd

from models import ImportHistoryEntry, ImportJobStatus, ImportResponse, PromoActualImportResponse
from repositories.imports import ImportsRepository
from services.dashboard_specials import get_special_cards_config_path, month_overlaps_period
from services.jobs import JobStatus, enqueue_grile_check, enqueue_sales_import, get_job_status
from services.product_lists import get_data_dir, normalize_column_name
import asyncpg

logger = logging.getLogger(__name__)
DEFAULT_MAX_SALES_UPLOAD_BYTES = 32 * 1024 * 1024
ALLOWED_SALES_EXTENSIONS = frozenset({".xlsx", ".xls"})
PROMO_REPORT_SHEET = "AccesoriPromoLunar"
PROMO_REPORT_SITE_ALIASES = {"sitecode", "site_code", "site"}
PROMO_REPORT_CODE_ALIASES = {"cod", "item_code", "itemcode", "cod_produs"}
PROMO_REPORT_QTY_ALIASES = {"promo_luna_curenta", "promo_qty", "cantitate_promo", "promo"}


async def trigger_grile_check_after_import(import_month: str, snapshot_id: int | None) -> None:
    """Best-effort: enqueue verificarea grilelor dupa un import reusit.

    NU propaga niciodata exceptii — importul de vanzari nu trebuie sa fie
    afectat daca enqueue-ul esueaza (Valkey down etc.).
    """
    try:
        result = await enqueue_grile_check(
            month=import_month, source="auto", source_snapshot_id=snapshot_id
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

    async def import_sales(self, file: UploadFile) -> ImportJobStatus:
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

        job = await enqueue_sales_import(content, filename=file.filename)
        job_status = await get_job_status(job.job_id)
        return ImportJobStatus(
            job_id=job.job_id,
            status=job_status.status.value,
            result=ImportResponse(**job_status.result) if job_status.result else None,
            error=job_status.error,
        )

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

        report_rows, promo_units = self._validate_promo_actuals_report(content)
        config_path = get_special_cards_config_path()
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
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

        suffix = Path(file.filename).suffix.casefold()
        digest = hashlib.sha256(content).hexdigest()[:12]
        destination = get_data_dir() / "promo_actuals" / import_month / f"promo_firma_{cutoff_date.isoformat()}_{digest}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_destination = destination.with_suffix(f"{destination.suffix}.tmp")
        temporary_destination.write_bytes(content)
        temporary_destination.replace(destination)

        updated_promotions = 0
        for promotion in config["promotions"]:
            if not isinstance(promotion, dict):
                continue
            try:
                start_date = date.fromisoformat(str(promotion.get("start_date", "")))
                end_date = date.fromisoformat(str(promotion.get("end_date", "")))
            except ValueError:
                continue
            if not month_overlaps_period(import_month, start_date, end_date):
                continue
            promotion["actuals_source_file"] = str(destination)
            promotion["actuals_sheet"] = PROMO_REPORT_SHEET
            promotion["actuals_cutoff_date"] = cutoff_date.isoformat()
            updated_promotions += 1
        if updated_promotions == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nu exista promotii configurate pentru luna selectata",
            )

        temporary_config = config_path.with_suffix(f"{config_path.suffix}.tmp")
        temporary_config.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary_config.replace(config_path)
        logger.info(
            "promo actuals imported month=%s cutoff=%s rows=%s units=%s file=%s",
            import_month,
            cutoff_date,
            report_rows,
            promo_units,
            destination.name,
        )
        return PromoActualImportResponse(
            import_month=import_month,
            cutoff_date=cutoff_date,
            filename=file.filename,
            report_rows=report_rows,
            promo_units=promo_units,
            updated_promotions=updated_promotions,
        )

    @staticmethod
    def _validate_promo_actuals_report(content: bytes) -> tuple[int, int]:
        try:
            dataframe = pd.read_excel(BytesIO(content), sheet_name=PROMO_REPORT_SHEET)
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
        promo_values = pd.to_numeric(dataframe[promo_column], errors="coerce").fillna(0)
        positive_rows = 0
        promo_units = 0
        for index, value in promo_values.items():
            quantity = int(round(float(value or 0)))
            if quantity <= 0:
                continue
            site_code = str(dataframe.at[index, site_column]).strip()
            item_code = str(dataframe.at[index, code_column]).strip()
            if not site_code or site_code.lower() == "nan" or not item_code or item_code.lower() == "nan":
                continue
            positive_rows += 1
            promo_units += quantity
        if positive_rows == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Raportul nu contine unitati promo pozitive",
            )
        return positive_rows, promo_units

    async def get_import_job_status(self, job_id: str) -> ImportJobStatus:
        result = await get_job_status(job_id)
        payload = ImportResponse(**result.result) if result.result else None
        return ImportJobStatus(
            job_id=result.job_id,
            status=result.status.value,
            result=payload,
            error=result.error,
        )

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
