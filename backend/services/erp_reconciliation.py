from __future__ import annotations
import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable
import asyncpg
import pandas as pd
from arq.jobs import Job
from fastapi import HTTPException, UploadFile, status
from repositories.erp_reconciliation import ErpReconciliationRepository
from schemas.campaigns import PromoIncentiveSummary
from schemas.erp_reconciliation import ErpReconciliationResponse
from services.campaigns import fetch_promo_incentive_summary
from services.erp_reconciliation_analysis import (
    MAX_RETURNED_ISSUES,
    reconcile_erp_report,
)
from services.legacy_xls import limits_from_upload_policy
from services.spreadsheet_readers import MissingWorksheetsError, read_required_spreadsheet_frames
from services.jobs import enqueue_erp_reconciliation
from services.spreadsheet_safety import (
    ERP_RECONCILIATION_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
)

logger = logging.getLogger(__name__)
DEFAULT_MAX_ERP_RECONCILIATION_BYTES = 16 * 1024 * 1024
ALLOWED_ERP_EXTENSIONS = frozenset({".xlsx", ".xls"})
STORE_IDENTITY_COLUMNS = ("Firma", "CodLocatie", "Locatie")
AGENT_IDENTITY_COLUMNS = (*STORE_IDENTITY_COLUMNS, "Agent")
STORE_BASE_METRIC_COLUMNS = (
    "AccValRealizat",
    "AccQttyRealizat",
    "NrBonuri",
    "NrBon2Acc",
)
STORE_AGENT_DERIVED_METRIC_COLUMNS = (
    "AccFocusQtty",
    "Audio",
    "Battery",
    "Suporti",
    "FoliiQtty",
    "Folii Sticla",
    "Folii TPU",
    "Still&Protectie",
    "Incarcare&Transfer",
)
COMMON_METRIC_COLUMNS = (
    *STORE_BASE_METRIC_COLUMNS,
    *STORE_AGENT_DERIVED_METRIC_COLUMNS,
)
STORE_REQUIRED_COLUMNS = (
    *STORE_IDENTITY_COLUMNS,
    "AccValTarget",
    *STORE_BASE_METRIC_COLUMNS,
)
AGENT_REQUIRED_COLUMNS = (*AGENT_IDENTITY_COLUMNS, *COMMON_METRIC_COLUMNS)

class ErpReportValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedErpReport:
    cutoff_date: date
    stores: dict[tuple[str], dict[str, Any]]
    agents: dict[tuple[str, str], dict[str, Any]]
    parser_resources: dict[str, int | float | str | None] | None = None

def _cell_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _cell_decimal(value: Any, *, sheet: str, column: str, row_number: int) -> Decimal:
    if value is None or pd.isna(value) or _cell_text(value) == "":
        raise ErpReportValidationError(
            f"{sheet}: valoare lipsa in coloana {column}, randul {row_number}"
        )
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ErpReportValidationError(
            f"{sheet}: valoare numerica invalida in coloana {column}, randul {row_number}"
        ) from exc
    if not parsed.is_finite():
        raise ErpReportValidationError(
            f"{sheet}: valoare numerica invalida in coloana {column}, randul {row_number}"
        )
    return parsed


def _header_indexes(raw: pd.DataFrame, sheet: str, required: Iterable[str]) -> dict[str, int]:
    if len(raw.index) < 3:
        raise ErpReportValidationError(
            f"Foaia {sheet} nu contine antetul si randurile detaliate. "
            "Regenereaza raportul ERP cu foaia populata."
        )
    headers = [_cell_text(value) for value in raw.iloc[1].tolist()]
    populated = [value for value in headers if value]
    duplicates = sorted({value for value in populated if populated.count(value) > 1})
    if duplicates:
        raise ErpReportValidationError(
            f"Foaia {sheet} are antete duplicate: {', '.join(duplicates)}"
        )
    indexes = {header: index for index, header in enumerate(headers) if header}
    missing = [column for column in required if column not in indexes]
    if missing:
        raise ErpReportValidationError(
            f"Foaia {sheet} nu contine coloanele: {', '.join(missing)}"
        )
    return indexes


def _parse_sheet(
    raw: pd.DataFrame,
    *,
    sheet: str,
    identity_columns: tuple[str, ...],
    required_columns: tuple[str, ...],
    metric_columns: tuple[str, ...],
    key_columns: tuple[str, ...],
) -> dict[tuple[str, ...], dict[str, Any]]:
    indexes = _header_indexes(raw, sheet, required_columns)
    parsed: dict[tuple[str, ...], dict[str, Any]] = {}
    for row_index in range(2, len(raw.index)):
        identity = {
            column: _cell_text(raw.iat[row_index, indexes[column]])
            for column in identity_columns
        }
        if not any(identity.values()):
            continue
        missing_identity = [column for column, value in identity.items() if not value]
        if missing_identity:
            raise ErpReportValidationError(
                f"{sheet}: identificatori lipsa la randul {row_index + 1}: "
                + ", ".join(missing_identity)
            )
        if identity["Locatie"].casefold().startswith("tr "):
            continue
        values: dict[str, Any] = dict(identity)
        for column in metric_columns:
            values[column] = _cell_decimal(
                raw.iat[row_index, indexes[column]],
                sheet=sheet,
                column=column,
                row_number=row_index + 1,
            )
        key = tuple(identity[column] for column in key_columns)
        if key in parsed:
            raise ErpReportValidationError(
                f"Foaia {sheet} contine cheia duplicata: {' / '.join(key)}"
            )
        parsed[key] = values
    if not parsed:
        raise ErpReportValidationError(f"Foaia {sheet} nu contine randuri Retail")
    return parsed


def _parse_erp_report_impl(
    content: bytes,
    import_month: str,
    *,
    cutoff_date: date,
    source_suffix: str,
) -> ParsedErpReport:
    try:
        month_start = date.fromisoformat(f"{import_month}-01")
    except ValueError as exc:
        raise ErpReportValidationError("Luna selectata este invalida") from exc
    if cutoff_date < month_start or cutoff_date.strftime("%Y-%m") != import_month:
        raise ErpReportValidationError("Cutoff-ul Retail nu este in luna selectata")
    try:
        frames = read_required_spreadsheet_frames(
            content,
            suffix=source_suffix,
            sheet_names=["Locatii", "Agenti"], header=None,
            limits=limits_from_upload_policy(ERP_RECONCILIATION_SPREADSHEET_LIMITS),
        )
        raw_stores, raw_agents = frames["Locatii"], frames["Agenti"]
    except ErpReportValidationError:
        raise
    except MissingWorksheetsError as exc:
        raise ErpReportValidationError(
            "Raportul nu contine foile: " + ", ".join(exc.missing)
        ) from exc
    except Exception as exc:
        raise ErpReportValidationError(
            "Raportul ERP nu poate fi citit ca fisier Excel"
        ) from exc

    store_headers = set(
        _header_indexes(raw_stores, "Locatii", STORE_REQUIRED_COLUMNS)
    )
    available_store_derived_metrics = tuple(
        metric
        for metric in STORE_AGENT_DERIVED_METRIC_COLUMNS
        if metric in store_headers
    )
    store_rows = _parse_sheet(
        raw_stores,
        sheet="Locatii",
        identity_columns=STORE_IDENTITY_COLUMNS,
        required_columns=STORE_REQUIRED_COLUMNS,
        metric_columns=(
            "AccValTarget",
            *STORE_BASE_METRIC_COLUMNS,
            *available_store_derived_metrics,
        ),
        key_columns=("CodLocatie",),
    )
    agent_rows = _parse_sheet(
        raw_agents,
        sheet="Agenti",
        identity_columns=AGENT_IDENTITY_COLUMNS,
        required_columns=AGENT_REQUIRED_COLUMNS,
        metric_columns=COMMON_METRIC_COLUMNS,
        key_columns=("CodLocatie", "Agent"),
    )

    missing_store_derived_metrics = tuple(
        metric
        for metric in STORE_AGENT_DERIVED_METRIC_COLUMNS
        if metric not in available_store_derived_metrics
    )
    if missing_store_derived_metrics:
        agent_metrics_by_store: dict[str, dict[str, Decimal]] = {}
        for agent_row in agent_rows.values():
            site_code = agent_row["CodLocatie"]
            totals = agent_metrics_by_store.setdefault(
                site_code,
                {metric: Decimal(0) for metric in missing_store_derived_metrics},
            )
            for metric in missing_store_derived_metrics:
                totals[metric] += agent_row[metric]
        for (site_code,), store_row in store_rows.items():
            totals = agent_metrics_by_store.get(site_code, {})
            for metric in missing_store_derived_metrics:
                store_row[metric] = totals.get(metric, Decimal(0))

    for metric in COMMON_METRIC_COLUMNS:
        store_total = sum((row[metric] for row in store_rows.values()), Decimal(0))
        agent_total = sum((row[metric] for row in agent_rows.values()), Decimal(0))
        if store_total != agent_total:
            raise ErpReportValidationError(
                f"Foile Locatii si Agenti nu au acelasi total pentru {metric}"
            )

    stores = {(key[0],): value for key, value in store_rows.items()}
    agents = {(key[0], key[1]): value for key, value in agent_rows.items()}
    return ParsedErpReport(
        cutoff_date=cutoff_date,
        stores=stores,
        agents=agents,
    )


def parse_erp_report(
    content: bytes,
    import_month: str,
    *,
    cutoff_date: date,
    source_suffix: str = ".xlsx",
) -> ParsedErpReport:
    measurement = SpreadsheetParserMeasurement("erp_reconciliation")
    with measurement:
        try:
            preflight = validate_spreadsheet_upload(
                content,
                source_suffix,
                limits=ERP_RECONCILIATION_SPREADSHEET_LIMITS,
            )
        except SpreadsheetUploadError as exc:
            raise ErpReportValidationError(str(exc)) from exc
        measurement.set_preflight(preflight)
        parsed = _parse_erp_report_impl(
            content,
            import_month,
            cutoff_date=cutoff_date,
            source_suffix=source_suffix,
        )
        measurement.set_rows(len(parsed.stores) + len(parsed.agents))
    return replace(parsed, parser_resources=measurement.as_dict())


class ErpReconciliationService:
    def __init__(self, repo: ErpReconciliationRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def reconcile(
        self,
        *,
        file: UploadFile,
        import_month: str,
    ) -> Job:
        if not file.filename or Path(file.filename).suffix.casefold() not in ALLOWED_ERP_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verificarea ERP accepta numai fisiere .xlsx sau .xls",
            )
        max_bytes = int(
            os.getenv(
                "MAX_ERP_RECONCILIATION_UPLOAD_BYTES",
                str(DEFAULT_MAX_ERP_RECONCILIATION_BYTES),
            )
        )
        content = await file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Raportul depaseste limita de {max_bytes // (1024 * 1024)} MB",
            )
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Raportul este gol")
        try:
            date.fromisoformat(f"{import_month}-01")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Luna selectata este invalida") from exc
        return await enqueue_erp_reconciliation(
            content,
            filename=file.filename,
            import_month=import_month,
        )

    async def process(
        self,
        *,
        content: bytes,
        filename: str,
        import_month: str,
    ) -> ErpReconciliationResponse:
        try:
            date.fromisoformat(f"{import_month}-01")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Luna selectata este invalida",
            ) from exc
        retail_cutoff_date = await self.repo.fetch_retail_cutoff(import_month)
        if retail_cutoff_date is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nu exista date Retail importate cu succes pentru luna {import_month}",
            )
        try:
            parse = partial(parse_erp_report,
                content,
                import_month,
                cutoff_date=retail_cutoff_date,
                source_suffix=Path(filename).suffix,
            )
            parsed = await asyncio.to_thread(parse)
        except ErpReportValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        reference = await self.repo.fetch_reference(import_month, parsed.cutoff_date)
        if reference["snapshot"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nu exista date Retail importate cu succes pentru luna {import_month}",
            )
        campaign_summary: PromoIncentiveSummary | None = None
        try:
            retail_cutoff_date = reference.get("retail_cutoff_date")
            campaign_cutoff = (
                parsed.cutoff_date
                if retail_cutoff_date is not None and retail_cutoff_date > parsed.cutoff_date
                else None
            )
            async with self.pool.acquire() as conn:
                campaign_summary = await fetch_promo_incentive_summary(
                    conn,
                    import_month,
                    None,
                    None,
                    None,
                    None,
                    None,
                    current_scope=True,
                    include_closed_stores=False,
                    cutoff_date=campaign_cutoff,
                )
        except Exception:  # noqa: BLE001 - reconcilierea de baza ramane disponibila
            logger.exception("ERP reconciliation could not load app-only campaign metrics")

        return reconcile_erp_report(
            parsed,
            reference,
            campaign_summary,
            import_month=import_month,
            filename=filename,
            file_digest=hashlib.sha256(content).hexdigest()[:12],
        )
