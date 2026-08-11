from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping
import asyncpg
import pandas as pd
from arq.jobs import Job
from fastapi import HTTPException, UploadFile, status
from repositories.erp_reconciliation import ErpReconciliationRepository
from schemas.campaigns import PromoIncentiveSummary
from schemas.erp_reconciliation import (
    ErpReconciliationAppMetric,
    ErpReconciliationIssue,
    ErpReconciliationMetric,
    ErpReconciliationResponse,
)
from services.campaigns import fetch_promo_incentive_summary
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
MAX_RETURNED_ISSUES = 500
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


def _sum(rows: Iterable[Mapping[str, Any]], key: str) -> Decimal:
    return sum((Decimal(str(row[key] or 0)) for row in rows), Decimal(0))


def _normalized(value: Any) -> str:
    return str(value or "").strip().casefold()


def _metric(
    key: str,
    label: str,
    report_value: Decimal,
    retail_value: Decimal,
    unit: str,
    *,
    status_value: str | None = None,
    note: str | None = None,
) -> ErpReconciliationMetric:
    difference = report_value - retail_value
    return ErpReconciliationMetric(
        key=key,
        label=label,
        report_value=report_value,
        retail_value=retail_value,
        difference=difference,
        unit=unit,  # type: ignore[arg-type]
        status=status_value or ("ok" if difference == 0 else "difference"),  # type: ignore[arg-type]
        note=note,
    )


def _category_quantity(
    rows: Iterable[Mapping[str, Any]],
    *,
    category: str,
    subcategories: set[str] | None = None,
    exclude_subcategories: set[str] | None = None,
) -> Decimal:
    category_key = category.casefold()
    included = {value.casefold() for value in subcategories or set()}
    excluded = {value.casefold() for value in exclude_subcategories or set()}
    total = Decimal(0)
    for row in rows:
        if _normalized(row["category"]) != category_key:
            continue
        subcategory = _normalized(row["subcategory"])
        if included and subcategory not in included:
            continue
        if subcategory in excluded:
            continue
        total += Decimal(str(row["quantity"] or 0))
    return total


def _focus_quantity(rows: Iterable[Mapping[str, Any]], *subcategories: str) -> Decimal:
    wanted = {value.casefold() for value in subcategories}
    return sum(
        (
            Decimal(str(row["quantity"] or 0))
            for row in rows
            if _normalized(row["focus_subcategory"]) in wanted
        ),
        Decimal(0),
    )


def _issue(
    *,
    severity: str,
    scope: str,
    entity: str,
    metric: str,
    note: str,
    site_code: str | None = None,
    report_value: Decimal | None = None,
    retail_value: Decimal | None = None,
) -> ErpReconciliationIssue:
    return ErpReconciliationIssue(
        severity=severity,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        site_code=site_code,
        entity=entity,
        metric=metric,
        report_value=report_value,
        retail_value=retail_value,
        difference=(
            report_value - retail_value
            if report_value is not None and retail_value is not None
            else None
        ),
        note=note,
    )


def _coverage_issues(
    parsed: ParsedErpReport,
    db_stores: Mapping[tuple[str], Mapping[str, Any]],
    db_agents: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[ErpReconciliationIssue]:
    report_store_keys = set(parsed.stores)
    report_agent_keys = set(parsed.agents)
    db_store_keys = set(db_stores)
    db_agent_keys = set(db_agents)
    issues = [
        _issue(
            severity="error",
            scope="store",
            site_code=store_key[0],
            entity=parsed.stores[store_key]["Locatie"],
            metric="coverage",
            note="Magazinul exista in raport, dar nu este in cohorta activa Retail.",
        )
        for store_key in sorted(report_store_keys - db_store_keys)
    ]
    issues.extend(
        _issue(
            severity="error",
            scope="store",
            site_code=store_key[0],
            entity=str(db_stores[store_key]["locatie"]),
            metric="coverage",
            note="Magazinul activ Retail lipseste din raport.",
        )
        for store_key in sorted(db_store_keys - report_store_keys)
    )
    issues.extend(
        _issue(
            severity="error",
            scope="agent",
            site_code=agent_key[0],
            entity=agent_key[1],
            metric="coverage",
            note="Agentul exista in raport, dar lipseste din snapshotul Retail.",
        )
        for agent_key in sorted(report_agent_keys - db_agent_keys)
    )
    issues.extend(
        _issue(
            severity="error",
            scope="agent",
            site_code=agent_key[0],
            entity=agent_key[1],
            metric="coverage",
            note="Agentul din snapshotul Retail lipseste din raport.",
        )
        for agent_key in sorted(db_agent_keys - report_agent_keys)
    )
    return issues


def _store_target_issues(
    parsed: ParsedErpReport,
    db_stores: Mapping[tuple[str], Mapping[str, Any]],
) -> list[ErpReconciliationIssue]:
    issues: list[ErpReconciliationIssue] = []
    for store_key in sorted(set(parsed.stores) & set(db_stores)):
        report_row = parsed.stores[store_key]
        retail_row = db_stores[store_key]
        report_target = Decimal(str(report_row["AccValTarget"]))
        retail_target = Decimal(str(retail_row["target_value"] or 0))
        if report_target != retail_target:
            issues.append(
                _issue(
                    severity="warning",
                    scope="store",
                    site_code=store_key[0],
                    entity=report_row["Locatie"],
                    metric="Target",
                    report_value=report_target,
                    retail_value=retail_target,
                    note="Targetul magazinului difera.",
                )
            )
    return issues


def _agent_detail_issues(
    parsed: ParsedErpReport,
    db_agents: Mapping[tuple[str, str], Mapping[str, Any]],
    receipt_rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[ErpReconciliationIssue]:
    detail_columns = (
        ("AccValRealizat", "total_sales", "Vanzari", Decimal("0.51")),
        ("AccQttyRealizat", "total_quantity", "Cantitate", Decimal(0)),
        ("AccFocusQtty", "focus_quantity", "Focus", Decimal(0)),
        ("NrBon2Acc", "receipt_2plus_count", "Bonuri 2+", Decimal(0)),
    )
    issues: list[ErpReconciliationIssue] = []
    for agent_key in sorted(set(parsed.agents) & set(db_agents)):
        report_row = parsed.agents[agent_key]
        retail_row = db_agents[agent_key]
        for report_column, retail_column, label, tolerance in detail_columns:
            report_value = Decimal(str(report_row[report_column]))
            retail_value = Decimal(str(retail_row[retail_column] or 0))
            if abs(report_value - retail_value) > tolerance:
                issues.append(
                    _issue(
                        severity="warning",
                        scope="agent",
                        site_code=agent_key[0],
                        entity=agent_key[1],
                        metric=label,
                        report_value=report_value,
                        retail_value=retail_value,
                        note=(
                            "Valoarea depaseste toleranta de rotunjire a raportului ERP."
                            if report_column == "AccValRealizat"
                            else f"{label} difera intre raport si Retail."
                        ),
                    )
                )
        report_receipts = Decimal(str(report_row["NrBonuri"]))
        raw_receipts = Decimal(str(receipt_rows.get(agent_key, {}).get("all_receipts", 0)))
        positive_receipts = Decimal(str(retail_row["receipt_count"] or 0))
        if report_receipts not in {raw_receipts, positive_receipts}:
            issues.append(
                _issue(
                    severity="warning",
                    scope="agent",
                    site_code=agent_key[0],
                    entity=agent_key[1],
                    metric="Bonuri ERP",
                    report_value=report_receipts,
                    retail_value=raw_receipts,
                    note="NrBonuri nu coincide cu nicio semantica Retail cunoscuta pentru bonuri.",
                )
            )
    return issues


def _reconciliation_metrics(
    parsed: ParsedErpReport,
    db_stores: Mapping[tuple[str], Mapping[str, Any]],
    db_agents: Mapping[tuple[str, str], Mapping[str, Any]],
    receipt_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    reference: Mapping[str, Any],
) -> list[ErpReconciliationMetric]:
    report_stores = list(parsed.stores.values())
    report_agents = list(parsed.agents.values())
    retail_stores = list(db_stores.values())
    retail_agents = list(db_agents.values())
    raw_receipt_total = _sum(receipt_rows.values(), "all_receipts")
    return_only_total = _sum(receipt_rows.values(), "return_only_receipts")
    positive_receipt_total = _sum(retail_agents, "receipt_count")
    report_receipt_total = _sum(report_agents, "NrBonuri")
    report_sales = _sum(report_agents, "AccValRealizat")
    retail_sales = _sum(retail_agents, "total_sales")
    sales_delta = report_sales - retail_sales
    rounding_tolerance = Decimal("0.51") * Decimal(max(1, len(report_agents)))
    sales_status = "ok" if sales_delta == 0 else (
        "explained" if abs(sales_delta) <= rounding_tolerance else "difference"
    )
    receipt_status = (
        "ok"
        if report_receipt_total == positive_receipt_total
        else "explained"
        if report_receipt_total == raw_receipt_total
        and raw_receipt_total - positive_receipt_total == return_only_total
        else "difference"
    )
    focus_rows = [dict(row) for row in reference["focus_rows"]]
    category_rows = [dict(row) for row in reference["category_rows"]]
    return [
        _metric("target", "Target", _sum(report_stores, "AccValTarget"), _sum(retail_stores, "target_value"), "RON"),
        _metric(
            "sales", "Vanzari accesorii", report_sales, retail_sales, "RON",
            status_value=sales_status,
            note=(
                "Raportul ERP rotunjeste valorile la nivel de agent; Retail pastreaza zecimalele."
                if sales_status == "explained" else None
            ),
        ),
        _metric("quantity", "Cantitate accesorii", _sum(report_agents, "AccQttyRealizat"), _sum(retail_agents, "total_quantity"), "buc"),
        _metric(
            "receipts", "Bonuri", report_receipt_total, positive_receipt_total, "bonuri",
            status_value=receipt_status,
            note=(
                f"ERP include {int(return_only_total)} bonuri exclusiv de retur; cardul Retail le exclude intentionat."
                if receipt_status == "explained" else None
            ),
        ),
        _metric("receipt_2plus", "Bonuri cu minimum 2 accesorii", _sum(report_agents, "NrBon2Acc"), _sum(retail_agents, "receipt_2plus_count"), "bonuri"),
        _metric("focus", "Produse Focus", _sum(report_agents, "AccFocusQtty"), _sum(retail_agents, "focus_quantity"), "buc"),
        _metric("focus_audio", "Focus audio", _sum(report_agents, "Audio"), _focus_quantity(focus_rows, "Casti intraauriculare"), "buc"),
        _metric("focus_battery", "Focus baterii externe", _sum(report_agents, "Battery"), _focus_quantity(focus_rows, "Baterie Externa"), "buc"),
        _metric("focus_supports", "Focus suporturi", _sum(report_agents, "Suporti"), _focus_quantity(focus_rows, "Suport auto", "Suport telescopic"), "buc"),
        _metric("films", "Folii total", _sum(report_agents, "FoliiQtty"), _category_quantity(category_rows, category="Folii Sticla") + _category_quantity(category_rows, category="Folii TPU"), "buc"),
        _metric("glass_films", "Folii sticla", _sum(report_agents, "Folii Sticla"), _category_quantity(category_rows, category="Folii Sticla"), "buc"),
        _metric("tpu_films", "Folii TPU", _sum(report_agents, "Folii TPU"), _category_quantity(category_rows, category="Folii TPU"), "buc"),
        _metric("style_protection", "Stil si protectie", _sum(report_agents, "Still&Protectie"), _category_quantity(category_rows, category="Stil si Protectie", subcategories={"Capac protectie", "Husa protectie"}), "buc"),
        _metric("charging_transfer", "Incarcare si transfer", _sum(report_agents, "Incarcare&Transfer"), _category_quantity(category_rows, category="Incarcare si Transfer", exclude_subcategories={"Baterie Externa"}), "buc"),
    ]


def _campaign_metrics(
    campaign_summary: PromoIncentiveSummary | None,
) -> list[ErpReconciliationAppMetric]:
    unavailable_note = (
        "Raportul agregat nu contine codurile de produs, bonurile si unitatile promo "
        "necesare pentru o comparatie independenta. Valoarea este cea calculata acum de Retail."
    )

    def campaign_value(field: str) -> Decimal | None:
        if campaign_summary is None:
            return None
        if (
            field in {"incentive_qty", "incentive_qualified_qty", "incentive_value"}
            and campaign_summary.calculation_status != "complete"
        ):
            return None
        value = getattr(campaign_summary, field)
        return Decimal(str(value)) if value is not None else None

    definitions = (
        ("promo_units", "Unitati promo", "promo_qty", "buc"),
        ("incentive_sold_units", "Unitati vandute in mecanismele Incentive", "incentive_sold_qty", "buc"),
        ("incentive_eligible_units", "Unitati eligibile dupa promo", "incentive_qty", "buc"),
        ("incentive_qualified_units", "Unitati in magazine calificate", "incentive_qualified_qty", "buc"),
        ("incentive_value", "Incentive calculat acum", "incentive_value", "RON"),
    )
    return [
        ErpReconciliationAppMetric(
            key=key,
            label=label,
            value=campaign_value(field),
            unit=unit,  # type: ignore[arg-type]
            note=unavailable_note,
        )
        for key, label, field, unit in definitions
    ]


def reconcile_erp_report(
    parsed: ParsedErpReport,
    reference: Mapping[str, Any],
    campaign_summary: PromoIncentiveSummary | None,
    *,
    import_month: str,
    filename: str,
    file_digest: str,
) -> ErpReconciliationResponse:
    db_stores = {(str(row["site_code"]),): dict(row) for row in reference["stores"]}
    db_agents = {
        (str(row["site_code"]), str(row["agent"])): dict(row)
        for row in reference["agents"]
    }
    receipt_rows = {
        (str(row["site_code"]), str(row["agent"])): dict(row)
        for row in reference["receipt_rows"]
    }
    issues = _coverage_issues(parsed, db_stores, db_agents)
    issues.extend(_store_target_issues(parsed, db_stores))
    issues.extend(_agent_detail_issues(parsed, db_agents, receipt_rows))
    metrics = _reconciliation_metrics(parsed, db_stores, db_agents, receipt_rows, reference)
    app_only_metrics = _campaign_metrics(campaign_summary)

    retail_cutoff_date = reference.get("retail_cutoff_date")
    cutoff_matches = bool(
        retail_cutoff_date is not None and retail_cutoff_date >= parsed.cutoff_date
    )
    if not cutoff_matches:
        issues.append(
            _issue(
                severity="error",
                scope="report",
                entity=import_month,
                metric="Cutoff",
                note=(
                    f"Raportul este pana la {parsed.cutoff_date.isoformat()}, dar snapshotul Retail "
                    f"are date numai pana la {retail_cutoff_date.isoformat() if retail_cutoff_date else 'fara date'}."
                ),
            )
        )

    has_difference_metric = any(metric.status == "difference" for metric in metrics)
    overall_status: Literal["ok", "differences"] = (
        "differences" if issues or has_difference_metric or not cutoff_matches else "ok"
    )
    issue_count = len(issues)
    returned_issues = issues[:MAX_RETURNED_ISSUES]
    return ErpReconciliationResponse(
        status=overall_status,
        import_month=import_month,
        report_cutoff_date=parsed.cutoff_date,
        retail_cutoff_date=retail_cutoff_date,
        cutoff_matches=cutoff_matches,
        filename=filename,
        file_digest=file_digest,
        report_store_count=len(parsed.stores),
        retail_store_count=len(db_stores),
        report_agent_count=len(parsed.agents),
        retail_agent_count=len(db_agents),
        metrics=metrics,
        app_only_metrics=app_only_metrics,
        issues=returned_issues,
        issue_count=issue_count,
        omitted_issue_count=max(0, issue_count - len(returned_issues)),
        notes=[
            "Verificarea este read-only: nu inlocuieste snapshotul de vanzari si nu modifica Focus, Promo sau Incentive.",
            "Toate interogarile comparabile sunt limitate la perioada 1-cutoff a snapshotului Retail activ; coloanele ZileLuna/ZileTrecute/ZileRamase din raport sunt ignorate.",
            "Sunt folosite randurile detaliate din foile Locatii si Agenti; randul de subtotal cache-uit deasupra antetului nu este sursa de adevar.",
            "Locatiile TR sunt excluse, identic cu KPI-urile Retail.",
            "parser_resources="
            + json.dumps(
                parsed.parser_resources or {},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        ],
    )


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
