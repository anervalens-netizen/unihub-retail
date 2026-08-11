"""Pure projections and canonical history loaders for Dashboard."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from domain.filter_scope import FilterInput
from schemas.dashboard import (
    DashboardHistoryResponse,
    MonthlyHistoryPoint,
    YearHistoryResponse,
    YearHistoryPoint,
)
from services.dashboard.ports import DashboardServicePort
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, normalize_filter_values, scoped_clauses
from services.request_deadline import RequestDeadline


_RO_MONTHS = {
    1: "Ian", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Iun",
    7: "Iul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _normalize_year_scope(
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
) -> tuple[list[str] | None, ...]:
    normalized = (
        normalize_filter_values(firma),
        normalize_filter_values(regional),
        normalize_filter_values(asm),
        normalize_filter_values(site_code),
        normalize_filter_values(agent),
    )
    if normalized[3]:
        return None, None, None, normalized[3], normalized[4]
    return normalized


def _append_array_scope(
    clauses: list[str],
    params: list[Any],
    values: list[tuple[list[str] | None, str]],
    *,
    start: int,
) -> None:
    position = start
    for value, column in values:
        if value is not None:
            clauses.append(f"{column} = ANY(${position}::TEXT[])")
            params.append(value)
            position += 1


def _scope_positions(
    values: list[tuple[str, list[str] | None]],
    *,
    start: int,
) -> dict[str, int]:
    positions: dict[str, int] = {}
    for key, value in values:
        if value is not None:
            positions[key] = start + len(positions)
    return positions


def project_year_history(
    year: int,
    rows: list[dict[str, Any]],
    aggregate_row: dict[str, Any] | None,
) -> list[YearHistoryPoint]:
    """Project repository rows into the stable year-history response."""
    visible_rows = [
        row
        for row in rows
        if row["total_sales"] > 0
        or row["total_target"] > 0
        or row["total_quantity"] > 0
    ]
    points: list[YearHistoryPoint] = []
    has_monthly_sales = any(
        row["total_sales"] > 0 or row["total_quantity"] > 0
        for row in visible_rows
    )
    if year <= 2023 and aggregate_row and not has_monthly_sales and aggregate_row["total_sales"] > 0:
        points.append(
            YearHistoryPoint(
                label="Ian-Aug" if year == 2023 else str(year),
                sort_key=f"{year}-00",
                total_sales=aggregate_row["total_sales"],
                total_target=Decimal(0),
                total_quantity=aggregate_row["total_quantity"],
                is_aggregate=True,
            )
        )
    for row in visible_rows:
        month_num = int(row["import_month"][5:7])
        points.append(
            YearHistoryPoint(
                label=_RO_MONTHS[month_num],
                sort_key=row["import_month"],
                total_sales=row["total_sales"],
                total_target=row["total_target"],
                total_quantity=row["total_quantity"],
                is_aggregate=False,
            )
        )
    return points


async def load_monthly_history(
    service: DashboardServicePort,
    month: str,
    months_back: int,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    *,
    deadline: RequestDeadline | None = None,
) -> DashboardHistoryResponse:
    params, positions = build_scoped_params(
        [month, months_back],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )

    sales_clauses: list[str] = []
    sales_clauses.extend(
        scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="s" if current_scope else "agg",
            agent_alias="agg",
            month_alias=None,
        )
    )
    if current_scope:
        sales_clauses = _expand_current_manager_scope(sales_clauses, positions)
    if current_scope and not include_closed_stores:
        sales_clauses.append("s.is_active = true")

    rows = await service.repo.fetch_monthly_history(sales_clauses, params, current_scope, pool=service._pool_for(deadline))
    return DashboardHistoryResponse(
        history=[MonthlyHistoryPoint(**dict(row)) for row in rows]
    )

async def load_history_by_year(
    service: DashboardServicePort,
    year: int,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    *,
    deadline: RequestDeadline | None = None,
) -> YearHistoryResponse:
    _firma, _regional, _asm, _site_code, _agent = _normalize_year_scope(
        firma, regional, asm, site_code, agent
    )

    start_month = f"{year}-01"
    end_month = f"{year}-12"

    rep_params: list[Any] = [start_month, end_month]
    rep_clauses: list[str] = []
    _append_array_scope(rep_clauses, rep_params, [
        (_firma, "s.firma" if current_scope else "agg.firma"),
        (_regional, "s.regional" if current_scope else "agg.regional"),
        (_asm, "s.asm" if current_scope else "agg.asm"),
        (_site_code, "agg.site_code"),
        (_agent, "agg.agent"),
    ], start=3)

    if current_scope:
        rep_positions = _scope_positions([
            ("firma", _firma),
            ("regional", _regional),
            ("asm", _asm),
            ("site_code", _site_code),
            ("agent", _agent),
        ], start=3)
        rep_clauses = _expand_current_manager_scope(rep_clauses, rep_positions)

    if current_scope and not include_closed_stores:
        rep_clauses.append("s.is_active = TRUE")

    rows = await service.repo.fetch_year_history_monthly(rep_clauses, rep_params, pool=service._pool_for(deadline))
    aggregate_row = None
    has_monthly_sales = any(
        row["total_sales"] > 0 or row["total_quantity"] > 0
        for row in rows
    )
    if year <= 2023 and _agent is None and not has_monthly_sales:
        hist_params: list[Any] = [year]
        hist_clauses: list[str] = []
        if year == 2023:
            hist_clauses.append("has.is_partial_year = TRUE")
        _append_array_scope(hist_clauses, hist_params, [
            (_firma, "s.firma" if current_scope else "has.firma"),
            (_regional, "s.regional"),
            (_asm, "s.asm"),
            (_site_code, "has.site_code"),
        ], start=2)

        if current_scope:
            hist_positions = _scope_positions([
                ("firma", _firma),
                ("regional", _regional),
                ("asm", _asm),
                ("site_code", _site_code),
            ], start=2)
            hist_clauses = _expand_current_manager_scope(hist_clauses, hist_positions)

        if current_scope and not include_closed_stores:
            hist_clauses.append("s.is_active = TRUE")

        aggregate_row = await service.repo.fetch_year_history_agg(
            year, hist_clauses, hist_params, pool=service._pool_for(deadline)
        )

    return YearHistoryResponse(
        points=project_year_history(year, [dict(row) for row in rows], aggregate_row)
    )
