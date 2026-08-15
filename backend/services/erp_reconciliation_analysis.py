"""Pure ERP-to-Retail reconciliation analysis.

Kept separate from spreadsheet parsing and queue orchestration so the public
service facade remains stable while the deterministic comparison stays small.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Literal, Mapping, Protocol

from schemas.campaigns import PromoIncentiveSummary
from schemas.erp_reconciliation import (
    ErpReconciliationAppMetric,
    ErpReconciliationIssue,
    ErpReconciliationMetric,
    ErpReconciliationResponse,
)


class ParsedErpReportView(Protocol):
    @property
    def cutoff_date(self) -> date: ...

    @property
    def stores(self) -> dict[tuple[str], dict[str, Any]]: ...

    @property
    def agents(self) -> dict[tuple[str, str], dict[str, Any]]: ...

    @property
    def parser_resources(self) -> dict[str, int | float | str | None] | None: ...

MAX_RETURNED_ISSUES = 500

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
    parsed: ParsedErpReportView,
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
    parsed: ParsedErpReportView,
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
    parsed: ParsedErpReportView,
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
    parsed: ParsedErpReportView,
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
    parsed: ParsedErpReportView,
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
