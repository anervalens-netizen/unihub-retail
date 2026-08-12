"""Canonical Dashboard performance-detail loader and scoring rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status

from domain.filter_scope import FilterInput
from schemas.dashboard import (
    AgentStats,
    DashboardSummary,
    MonthlyHistoryPoint,
    PerformanceDetailResponse,
    PerformancePeerRow,
    PerformanceScoreBreakdown,
    RegionalStats,
    StoreStats,
)
from services.dashboard.ports import DashboardServicePort
from services.dashboard.queries import (
    _fetch_agent_stats_rows,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
)
from services.dashboard.projections import public_stats_row
from services.dashboard.scheduler import _gather_cancel_on_error
from services.filters import normalize_filter
from services.request_deadline import RequestDeadline


MONEY_QUANTUM = Decimal("0.01")

PERFORMANCE_COMPONENT_WEIGHT = Decimal("20")


def score_breakdown(summary: DashboardSummary) -> PerformanceScoreBreakdown:
    target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct or Decimal(0)
    bon_pct = summary.proc_bon2acc or Decimal(0)
    focus_pct = summary.prc_focus_acc_qty or Decimal(0)
    target_score = (
        min(max(target_pct, Decimal(0)), Decimal(120)) / Decimal(120) * Decimal(60)
    ).quantize(Decimal("0.1"))
    return PerformanceScoreBreakdown(
        target_points=target_score,
        bon2acc_points=score_bon2acc(bon_pct),
        focus_points=score_focus(focus_pct),
    )


def score_total(breakdown: PerformanceScoreBreakdown) -> int:
    score = breakdown.target_points + breakdown.bon2acc_points + breakdown.focus_points
    return max(0, min(100, round(float(score))))


def score_bon2acc(value: Decimal) -> Decimal:
    if value > Decimal("35"):
        points = PERFORMANCE_COMPONENT_WEIGHT
    elif value >= Decimal("30"):
        points = PERFORMANCE_COMPONENT_WEIGHT * Decimal(2) / Decimal(3)
    elif value >= Decimal("20"):
        points = PERFORMANCE_COMPONENT_WEIGHT / Decimal(3)
    else:
        points = Decimal(0)
    return points.quantize(Decimal("0.1"))


def score_focus(value: Decimal) -> Decimal:
    if value > Decimal("8"):
        points = PERFORMANCE_COMPONENT_WEIGHT
    elif value >= Decimal("6"):
        points = PERFORMANCE_COMPONENT_WEIGHT * Decimal(2) / Decimal(3)
    else:
        points = Decimal(0)
    return points.quantize(Decimal("0.1"))


def trend_sales(summary: DashboardSummary) -> Decimal:
    if not summary.is_month_final and summary.forecast_sales is not None:
        return summary.forecast_sales
    return summary.total_sales


def score_label(score: int) -> str:
    if score >= 85:
        return "Foarte bine"
    if score >= 70:
        return "Bun"
    if score >= 55:
        return "De urmarit"
    return "Necesita interventie"


def _validated_performance_key(
    level: Literal["regional", "store", "agent"],
    key: str | None,
) -> str:
    normalized = key.strip() if level != "store" and key is not None else key
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cheia entitatii lipseste.",
        )
    return normalized


@dataclass(slots=True)
class _PerformanceSelection:
    title: str
    subtitle: str | None = None
    firma: str | None = None
    regional: str | None = None
    site_code: FilterInput = None
    agent: str | None = None
    peer_rows: list[PerformancePeerRow] | None = None
    agent_stats: AgentStats | None = None


async def _load_regional_selection(
    conn: object,
    *,
    month: str,
    key: str,
    firma: str | None,
    current_scope: bool,
    include_closed_stores: bool,
) -> _PerformanceSelection:
    rows = await _fetch_regional_stats(
        conn,
        month=month,
        firma=firma,
        regional=None,
        asm=None,
        site_code=None,
        agent=None,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    peers = [RegionalStats(**public_stats_row(row)) for row in rows]
    if not any(row.regional == key for row in peers):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RM-ul nu are date in luna selectata.",
        )
    return _PerformanceSelection(
        title=key,
        firma=firma,
        regional=key,
        peer_rows=regional_peer_rows(peers, key),
    )


async def _load_store_selection(
    conn: object,
    *,
    month: str,
    key: str,
    current_scope: bool,
    include_closed_stores: bool,
) -> _PerformanceSelection:
    rows = await _fetch_store_stats_rows(
        conn,
        month=month,
        firma=None,
        regional=None,
        asm=None,
        site_code=key,
        agent=None,
        current_scope=current_scope,
        include_closed_stores=True,
    )
    selected = StoreStats(**dict(rows[0])) if rows else None
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Magazinul nu are date in luna selectata.",
        )
    peer_source = await _fetch_store_stats_rows(
        conn,
        month=month,
        firma=selected.firma,
        regional=selected.regional,
        asm=None,
        site_code=None,
        agent=None,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    return _PerformanceSelection(
        title=selected.locatie,
        subtitle=f"{selected.site_code} · {selected.firma} · {selected.regional}",
        site_code=key,
        peer_rows=store_peer_rows(
            [StoreStats(**dict(row)) for row in peer_source], key
        ),
    )


async def _load_agent_selection(
    conn: object,
    *,
    month: str,
    key: str,
    site_code: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> _PerformanceSelection:
    rows = await _fetch_agent_stats_rows(
        conn,
        month=month,
        firma=None,
        regional=None,
        asm=None,
        site_code=site_code,
        agent=key,
        current_scope=current_scope,
        include_closed_stores=True,
    )
    selected = AgentStats(**dict(rows[0])) if rows else None
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agentul nu are date in luna selectata.",
        )
    peer_source = await _fetch_agent_stats_rows(
        conn,
        month=month,
        firma=None,
        regional=None,
        asm=None,
        site_code=selected.site_code,
        agent=None,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    return _PerformanceSelection(
        title=selected.agent,
        subtitle=f"{selected.locatie} · {selected.firma}",
        site_code=selected.site_code,
        agent=key,
        agent_stats=selected,
        peer_rows=agent_peer_rows(
            [AgentStats(**dict(row)) for row in peer_source],
            selected.agent,
            selected.site_code,
        ),
    )


async def _select_performance_entity(
    conn: object,
    *,
    month: str,
    level: Literal["regional", "store", "agent"],
    key: str,
    firma: str | None,
    site_code: FilterInput,
    current_scope: bool,
    include_closed_stores: bool,
) -> _PerformanceSelection:
    common = {
        "conn": conn,
        "month": month,
        "key": key,
        "current_scope": current_scope,
        "include_closed_stores": include_closed_stores,
    }
    if level == "regional":
        return await _load_regional_selection(firma=firma, **common)
    if level == "store":
        return await _load_store_selection(**common)
    if level == "agent":
        return await _load_agent_selection(site_code=site_code, **common)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nivel invalid.")


async def load_performance_detail(
    service: DashboardServicePort,
    month: str,
    level: Literal["regional", "store", "agent"],
    key: str | None,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = True,
    include_closed_stores: bool = False,
    *,
    deadline: RequestDeadline | None = None,
) -> PerformanceDetailResponse:
    del regional, asm, agent
    key = _validated_performance_key(level, key)
    context_summary: DashboardSummary | None = None

    async with service._pool_for(deadline).acquire() as conn:
        selection = await _select_performance_entity(
            conn,
            month=month,
            level=level,
            key=key,
            firma=normalize_filter(firma),
            site_code=site_code,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
        )

    peer_rows = selection.peer_rows or []

    summary, history_response, daily = await _gather_cancel_on_error(
        service.get_summary(
            month,
            selection.firma if level == "regional" else None,
            selection.regional,
            None,
            selection.site_code,
            selection.agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            deadline=deadline,
        ),
        service.get_monthly_history(
            month,
            14,
            selection.firma if level == "regional" else None,
            selection.regional,
            None,
            selection.site_code,
            selection.agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            deadline=deadline,
        ),
        service.get_daily_sales(
            month,
            selection.firma if level == "regional" else None,
            selection.regional,
            None,
            selection.site_code,
            selection.agent,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            deadline=deadline,
        ),
        task_name="dashboard:performance-detail",
    )

    if level == "agent" and selection.site_code and selection.agent_stats is not None:
        summary = apply_agent_target_summary(summary, selection.agent_stats)
        context_summary = await service.get_summary(
            month,
            None,
            None,
            None,
            selection.site_code,
            None,
            current_scope=current_scope,
            include_closed_stores=include_closed_stores,
            deadline=deadline,
        )

    breakdown = score_breakdown(summary)
    score = score_total(breakdown)
    label = score_label(score)
    strengths, risks = performance_signals(summary, history_response.history, level)
    note = performance_note(summary, history_response.history, label, peer_rows, level)

    return PerformanceDetailResponse(
        level=level,
        key=key,
        title=selection.title,
        subtitle=selection.subtitle,
        month=month,
        summary=summary,
        history=history_response.history,
        daily=daily,
        score=score,
        score_breakdown=breakdown,
        score_label=label,
        note=note,
        strengths=strengths,
        risks=risks,
        peer_rows=peer_rows,
        context_summary=context_summary,
    )

def apply_agent_target_summary(
    summary: DashboardSummary,
    agent_stats: AgentStats,
) -> DashboardSummary:
    target = agent_stats.target or Decimal(0)
    target_progress_pct = (
        (summary.total_sales * Decimal(100) / target).quantize(MONEY_QUANTUM)
        if target > 0
        else None
    )
    forecast_target_progress_pct = (
        (summary.forecast_sales * Decimal(100) / target).quantize(MONEY_QUANTUM)
        if target > 0 and summary.forecast_sales is not None
        else None
    )
    return summary.model_copy(
        update={
            "total_target": target,
            "target_progress_pct": target_progress_pct,
            "forecast_target_progress_pct": forecast_target_progress_pct,
        }
    )

def performance_signals(
    summary: DashboardSummary,
    history: list[MonthlyHistoryPoint],
    level: Literal["regional", "store", "agent"],
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    risks: list[str] = []
    _append_target_signal(summary, strengths, risks)
    _append_bon2acc_signal(summary, strengths, risks)
    _append_focus_signal(summary, strengths, risks)
    _append_trend_signal(summary, history, level, strengths, risks)
    return strengths[:3], risks[:3]


def _append_target_signal(
    summary: DashboardSummary, strengths: list[str], risks: list[str]
) -> None:
    target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct
    if target_pct is not None and target_pct >= 100:
        strengths.append("Ritmul proiectat acopera targetul lunii.")
    elif target_pct is not None and target_pct < 85:
        risks.append("Ritmul proiectat este sub 85% din target.")


def _append_bon2acc_signal(
    summary: DashboardSummary, strengths: list[str], risks: list[str]
) -> None:
    if summary.proc_bon2acc is not None and summary.proc_bon2acc > 35:
        strengths.append("Bon2Acc este foarte bine, peste 35%.")
    elif summary.proc_bon2acc is not None and summary.proc_bon2acc < 20:
        risks.append("Bon2Acc este critic scazut, sub 20%.")
    elif summary.proc_bon2acc is not None and summary.proc_bon2acc < 30:
        risks.append("Bon2Acc este scazut, sub 30%.")


def _append_focus_signal(
    summary: DashboardSummary, strengths: list[str], risks: list[str]
) -> None:
    if summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty > 8:
        strengths.append("Focus-ul este bun, peste 8%.")
    elif summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty < 6:
        risks.append("Focus-ul este scazut, sub 6%.")


def _append_trend_signal(
    summary: DashboardSummary,
    history: list[MonthlyHistoryPoint],
    level: Literal["regional", "store", "agent"],
    strengths: list[str],
    risks: list[str],
) -> None:
    previous = [point for point in history if point.month < summary.month and point.total_sales > 0][-3:]
    if previous:
        avg_previous = sum((point.total_sales for point in previous), Decimal(0)) / Decimal(len(previous))
        if avg_previous > 0:
            sales_for_trend = trend_sales(summary)
            delta_pct = (sales_for_trend - avg_previous) * Decimal(100) / avg_previous
            entity_label = "agentul" if level == "agent" else "zona"
            if delta_pct >= 10:
                strengths.append(f"{entity_label.capitalize()} este peste media ultimelor 3 luni.")
            elif delta_pct <= -10:
                risks.append(f"{entity_label.capitalize()} este sub media ultimelor 3 luni.")

def performance_note(
    summary: DashboardSummary,
    history: list[MonthlyHistoryPoint],
    score_label: str,
    peer_rows: list[PerformancePeerRow],
    level: Literal["regional", "store", "agent"],
) -> str:
    target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct
    target_text = f"{target_pct:.1f}%" if target_pct is not None else "fara target disponibil"
    previous = [point for point in history if point.month < summary.month and point.total_sales > 0][-3:]
    trend_text = "istoric insuficient pentru trend"
    if previous:
        avg_previous = sum((point.total_sales for point in previous), Decimal(0)) / Decimal(len(previous))
        if avg_previous > 0:
            sales_for_trend = trend_sales(summary)
            delta_pct = (sales_for_trend - avg_previous) * Decimal(100) / avg_previous
            trend_text = f"{delta_pct:+.1f}% vs media ultimelor 3 luni"
    selected_peer = next((peer for peer in peer_rows if peer.is_selected), None)
    peer_text = f"rank {selected_peer.rank} in grupul comparabil" if selected_peer else "fara comparatie peer"
    label = {"regional": "RM-ul", "store": "Magazinul", "agent": "Agentul"}[level]
    return f"{label} este in zona {score_label.lower()}: proiectie target {target_text}, {trend_text}, {peer_text}."

def regional_peer_rows(
    rows: list[RegionalStats],
    selected_key: str,
) -> list[PerformancePeerRow]:
    ranked = sorted(rows, key=lambda row: (row.proc_realizare_target or Decimal(0), row.total_vanzari), reverse=True)
    peers = [
        PerformancePeerRow(
            label=row.regional,
            sublabel=f"{row.nr_agenti} agenti · {row.zile_active} zile active",
            total_sales=row.total_vanzari,
            target_progress_pct=row.proc_realizare_target,
            forecast_target_pct=row.forecast_target_pct,
            proc_bon2acc=row.proc_bon2acc,
            prc_focus_acc_qty=row.prc_focus_acc_qty,
            rank=index + 1,
            is_selected=row.regional == selected_key,
        )
        for index, row in enumerate(ranked)
    ]
    return compact_peer_rows(peers)

def store_peer_rows(
    rows: list[StoreStats],
    selected_site_code: str,
) -> list[PerformancePeerRow]:
    ranked = sorted(rows, key=lambda row: (row.proc_realizare_target or Decimal(0), row.total_vanzari), reverse=True)
    peers = [
        PerformancePeerRow(
            label=row.locatie,
            sublabel=f"{row.site_code} · {row.nr_agenti} agenti",
            total_sales=row.total_vanzari,
            target_progress_pct=row.proc_realizare_target,
            forecast_target_pct=row.forecast_target_pct,
            rank=index + 1,
            is_selected=row.site_code == selected_site_code,
        )
        for index, row in enumerate(ranked)
    ]
    return compact_peer_rows(peers)

def agent_peer_rows(
    rows: list[AgentStats],
    selected_agent: str,
    selected_site_code: str,
) -> list[PerformancePeerRow]:
    ranked = sorted(rows, key=lambda row: (row.proc_realizare_target or Decimal(0), row.total_vanzari), reverse=True)
    peers = [
        PerformancePeerRow(
            label=row.agent,
            sublabel=row.locatie,
            total_sales=row.total_vanzari,
            target_progress_pct=row.proc_realizare_target,
            proc_bon2acc=row.proc_bon2acc,
            prc_focus_acc_qty=row.prc_focus_acc_qty,
            rank=index + 1,
            is_selected=row.agent == selected_agent and row.site_code == selected_site_code,
        )
        for index, row in enumerate(ranked)
    ]
    return compact_peer_rows(peers)

def compact_peer_rows(peers: list[PerformancePeerRow]) -> list[PerformancePeerRow]:
    selected = next((row for row in peers if row.is_selected), None)
    compact = peers[:12]
    if selected is not None and all(row.rank != selected.rank for row in compact):
        compact = compact[:11] + [selected]
    return compact
