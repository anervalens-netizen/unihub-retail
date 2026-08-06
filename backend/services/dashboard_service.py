from __future__ import annotations

import asyncio
from decimal import Decimal
from collections.abc import Awaitable
from typing import Any, Literal, cast

import asyncpg
from fastapi import HTTPException, status

from schemas.dashboard import (
    DashboardSummary,
    DashboardAllBatchResponse,
    DashboardAllQuery,
    DashboardAllResponse,
    DailySalesPoint,
    DashboardSpecialCard,
    DashboardSpecialCardsResponse,
    DashboardHistoryResponse,
    MonthlyHistoryPoint,
    YearHistoryResponse,
    AgentStats,
    StoreStats,
    PeriodComparisonPayload,
    CategoryMixItem,
    ReceiptBucketItem,
    BrandMixItem,
    PerformanceDetailResponse,
    PerformancePeerRow,
    PerformanceScoreBreakdown,
    RegionalStats,
    AsmStats,
)
from schemas.campaigns import PromoIncentiveSummary
from schemas.premium_glass import PremiumGlassAnalysis
from config import RuntimeConfig
from repositories.dashboard import DashboardRepository
from services.dashboard.queries import (
    apply_current_promo_metrics,
    _enrich_store_stats_with_campaign,
    _fetch_agent_stats_rows,
    _fetch_asm_stats,
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_focus_subcategory_mix,
    _fetch_daily_last_year_for_current_cohort,
    _fetch_period_comparison,
    _fetch_promo_incentive_summary,
    _fetch_receipt_bucket_mix,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
    _load_dashboard_campaign_context,
)
from services.dashboard.specials_data import _get_special_cards_data
from services.dashboard.history import project_year_history
from services.dashboard.orchestration import gather_dashboard_phase
from services.dashboard.metrics import observe_dashboard_component
from services.dashboard.scheduler import (
    DASHBOARD_COMPONENT_CONCURRENCY,
    DEFAULT_DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY,
    _gather_cancel_on_error,
    _gather_named,
)
from services.dashboard.batch import (
    load_dashboard_all_batch,
    load_dashboard_history_details_batch,
)
from services.dashboard.performance import (
    score_bon2acc,
    score_breakdown,
    score_focus,
    score_label,
    score_total,
    trend_sales,
)
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, normalize_filter, scoped_clauses
from services.premium_glass import build_premium_glass_card, get_premium_glass_analysis
from services.request_deadline import RequestDeadline


_MONEY = Decimal("0.01")


class DashboardService:
    def __init__(
        self,
        repo: DashboardRepository,
        pool: asyncpg.Pool,
        runtime_config: RuntimeConfig | None = None,
    ):
        self.repo = repo
        self.pool = pool
        global_component_concurrency = (
            runtime_config.dashboard_global_component_concurrency
            if runtime_config is not None
            else DEFAULT_DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY
        )
        if global_component_concurrency is None:
            raise ValueError("Dashboard requires web RuntimeConfig")
        self.dashboard_global_component_concurrency: int = global_component_concurrency

    def _pool_for(self, deadline: RequestDeadline | None) -> Any:
        return deadline.bind_pool(self.pool) if deadline is not None else self.pool

    async def get_summary(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = False,
        include_closed_stores: bool = False,
        *,
        deadline: RequestDeadline | None = None,
    ) -> DashboardSummary:
        params, positions = build_scoped_params(
            [month],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        clauses = scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="s" if current_scope else "agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
        )
        if current_scope:
            clauses = _expand_current_manager_scope(clauses, positions)
        if current_scope and not include_closed_stores:
            clauses.append("s.is_active = true")

        cartela_clauses = scoped_clauses(
            positions,
            site_alias="c",
            store_alias="cs",
            agent_alias="c",
        )
        if current_scope:
            cartela_clauses = _expand_current_manager_scope(
                cartela_clauses, positions, store_alias="cs"
            )
        if current_scope and not include_closed_stores:
            cartela_clauses.append("cs.is_active = true")

        row = await self.repo.fetch_summary(clauses, params, cartela_clauses, current_scope, pool=self._pool_for(deadline))
        if row is None:
            return DashboardSummary(
                month=month,
                total_sales=Decimal(0),
                total_target=Decimal(0),
                target_progress_pct=None,
                forecast_sales=None,
                forecast_target_progress_pct=None,
                total_quantity=0,
                total_receipts=0,
                proc_bon2acc=None,
                prc_focus_acc_qty=None,
                total_stores=0,
                total_agents=0,
                working_days=0,
                daily_average=None,
                medie_produs=None,
                is_month_final=True,
                last_sale_date=None,
                imported_day_of_month=None,
                days_in_month=None,
                cartele_qty=0,
            )
        return DashboardSummary(**dict(row))

    async def get_daily_sales(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = False,
        include_closed_stores: bool = False,
        *,
        deadline: RequestDeadline | None = None,
    ) -> list[DailySalesPoint]:
        params, positions = build_scoped_params(
            [month],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        clauses = scoped_clauses(
            positions,
            site_alias="agg",
            store_alias="s" if current_scope else "agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
        )
        if current_scope:
            clauses = _expand_current_manager_scope(clauses, positions)
        if current_scope and not include_closed_stores:
            clauses.append("s.is_active = true")

        rows = await self.repo.fetch_daily_sales(clauses, params, current_scope, pool=self._pool_for(deadline))
        return [DailySalesPoint(**dict(row)) for row in rows]

    async def get_special_cards(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        *,
        deadline: RequestDeadline | None = None,
    ) -> DashboardSpecialCardsResponse:
        cards = await _get_special_cards_data(
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            pool=self._pool_for(deadline),
        )
        async with self._pool_for(deadline).acquire() as conn:
            premium_glass = await get_premium_glass_analysis(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=True,
                include_closed_stores=False,
            )
        cards.append(build_premium_glass_card(premium_glass))
        return DashboardSpecialCardsResponse(cards=cards)

    async def get_premium_glass(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        surface: Literal["all", "screen", "camera"] = "all",
        current_scope: bool = True,
        include_closed_stores: bool = False,
        *,
        deadline: RequestDeadline | None = None,
    ) -> PremiumGlassAnalysis:
        async with self._pool_for(deadline).acquire() as conn:
            return await get_premium_glass_analysis(
                conn,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                surface=surface,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )

    async def get_monthly_history(
        self,
        month: str,
        months_back: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
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

        rows = await self.repo.fetch_monthly_history(sales_clauses, params, current_scope, pool=self._pool_for(deadline))
        return DashboardHistoryResponse(
            history=[MonthlyHistoryPoint(**dict(row)) for row in rows]
        )

    async def get_history_by_year(
        self,
        year: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = False,
        include_closed_stores: bool = False,
        *,
        deadline: RequestDeadline | None = None,
    ) -> YearHistoryResponse:
        _firma = normalize_filter(firma)
        _regional = normalize_filter(regional)
        _asm = normalize_filter(asm)
        _site_code = site_code
        _agent = normalize_filter(agent)

        start_month = f"{year}-01"
        end_month = f"{year}-12"

        rep_params: list[Any] = [start_month, end_month]
        rep_clauses: list[str] = []
        p = 3
        has_site_scope = _site_code is not None
        for val, col in [
            (None if has_site_scope else _firma, "s.firma" if current_scope else "agg.firma"),
            (None if has_site_scope else _regional, "s.regional" if current_scope else "agg.regional"),
            (None if has_site_scope else _asm, "s.asm" if current_scope else "agg.asm"),
            (_site_code, "agg.site_code"),
            (_agent, "agg.agent"),
        ]:
            if val is not None:
                rep_clauses.append(f"{col} = ANY(string_to_array(${p}::TEXT, ','))")
                rep_params.append(val)
                p += 1

        if current_scope:
            rep_positions: dict[str, int] = {}
            offset = 3
            for key, val in [
                ("firma", None if has_site_scope else _firma),
                ("regional", None if has_site_scope else _regional),
                ("asm", None if has_site_scope else _asm),
                ("site_code", _site_code),
                ("agent", _agent),
            ]:
                if val is not None:
                    rep_positions[key] = offset
                    offset += 1
            rep_clauses = _expand_current_manager_scope(rep_clauses, rep_positions)

        if current_scope and not include_closed_stores:
            rep_clauses.append("s.is_active = TRUE")

        rows = await self.repo.fetch_year_history_monthly(rep_clauses, rep_params, pool=self._pool_for(deadline))
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
            p = 2
            has_site_scope = _site_code is not None
            for val, col in [
                (None if has_site_scope else _firma, "s.firma" if current_scope else "has.firma"),
                (None if has_site_scope else _regional, "s.regional"),
                (None if has_site_scope else _asm, "s.asm"),
                (_site_code, "has.site_code"),
            ]:
                if val is not None:
                    hist_clauses.append(f"{col} = ANY(string_to_array(${p}::TEXT, ','))")
                    hist_params.append(val)
                    p += 1

            if current_scope:
                hist_positions: dict[str, int] = {}
                offset = 2
                for key, val in [
                    ("firma", None if has_site_scope else _firma),
                    ("regional", None if has_site_scope else _regional),
                    ("asm", None if has_site_scope else _asm),
                    ("site_code", _site_code),
                ]:
                    if val is not None:
                        hist_positions[key] = offset
                        offset += 1
                hist_clauses = _expand_current_manager_scope(hist_clauses, hist_positions)

            if current_scope and not include_closed_stores:
                hist_clauses.append("s.is_active = TRUE")

            aggregate_row = await self.repo.fetch_year_history_agg(
                year, hist_clauses, hist_params, pool=self._pool_for(deadline)
            )

        return YearHistoryResponse(
            points=project_year_history(year, [dict(row) for row in rows], aggregate_row)
        )

    async def get_performance_detail(
        self,
        month: str,
        level: Literal["regional", "store", "agent"],
        key: str | None,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = True,
        include_closed_stores: bool = False,
        *,
        deadline: RequestDeadline | None = None,
    ) -> PerformanceDetailResponse:
        del regional, asm, agent
        if level != "store" and key is not None:
            key = key.strip()
        if not key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cheia entitatii lipseste.")

        effective_firma = normalize_filter(firma)
        effective_regional: str | None = None
        effective_site_code: str | None = None
        effective_agent: str | None = None
        title = key
        subtitle: str | None = None
        peer_rows: list[PerformancePeerRow] = []
        context_summary: DashboardSummary | None = None
        selected_agent_stats: AgentStats | None = None

        async with self._pool_for(deadline).acquire() as conn:
            if level == "regional":
                effective_regional = key
                regional_rows = await _fetch_regional_stats(
                    conn,
                    month=month,
                    firma=effective_firma,
                    regional=None,
                    asm=None,
                    site_code=None,
                    agent=None,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                peers = [RegionalStats(**dict(row)) for row in regional_rows]
                selected = next((row for row in peers if row.regional == key), None)
                if selected is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RM-ul nu are date in luna selectata.")
                peer_rows = self._regional_peer_rows(peers, key)
            elif level == "store":
                effective_site_code = key
                store_rows = await _fetch_store_stats_rows(
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
                stores = [StoreStats(**dict(row)) for row in store_rows]
                selected_store = stores[0] if stores else None
                if selected_store is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Magazinul nu are date in luna selectata.")
                title = selected_store.locatie
                subtitle = f"{selected_store.site_code} · {selected_store.firma} · {selected_store.regional}"
                peer_source = await _fetch_store_stats_rows(
                    conn,
                    month=month,
                    firma=selected_store.firma,
                    regional=selected_store.regional,
                    asm=None,
                    site_code=None,
                    agent=None,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                peer_rows = self._store_peer_rows([StoreStats(**dict(row)) for row in peer_source], key)
            elif level == "agent":
                effective_site_code = site_code
                effective_agent = key
                agent_rows = await _fetch_agent_stats_rows(
                    conn,
                    month=month,
                    firma=None,
                    regional=None,
                    asm=None,
                    site_code=effective_site_code,
                    agent=key,
                    current_scope=current_scope,
                    include_closed_stores=True,
                )
                agents = [AgentStats(**dict(row)) for row in agent_rows]
                selected_agent = agents[0] if agents else None
                if selected_agent is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agentul nu are date in luna selectata.")
                selected_agent_stats = selected_agent
                effective_site_code = selected_agent.site_code
                title = selected_agent.agent
                subtitle = f"{selected_agent.locatie} · {selected_agent.firma}"
                peer_source = await _fetch_agent_stats_rows(
                    conn,
                    month=month,
                    firma=None,
                    regional=None,
                    asm=None,
                    site_code=selected_agent.site_code,
                    agent=None,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                peer_rows = self._agent_peer_rows([AgentStats(**dict(row)) for row in peer_source], selected_agent.agent, selected_agent.site_code)
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nivel invalid.")

        summary, history_response, daily = await _gather_cancel_on_error(
            self.get_summary(
                month,
                effective_firma if level == "regional" else None,
                effective_regional,
                None,
                effective_site_code,
                effective_agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            ),
            self.get_monthly_history(
                month,
                14,
                effective_firma if level == "regional" else None,
                effective_regional,
                None,
                effective_site_code,
                effective_agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            ),
            self.get_daily_sales(
                month,
                effective_firma if level == "regional" else None,
                effective_regional,
                None,
                effective_site_code,
                effective_agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            ),
            task_name="dashboard:performance-detail",
        )

        if level == "agent" and effective_site_code and selected_agent_stats is not None:
            summary = self._apply_agent_target_summary(summary, selected_agent_stats)
            context_summary = await self.get_summary(
                month,
                None,
                None,
                None,
                effective_site_code,
                None,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            )

        score_breakdown = self._performance_score_breakdown(summary)
        score = self._performance_score(score_breakdown)
        score_label = self._score_label(score)
        strengths, risks = self._performance_signals(summary, history_response.history, level)
        note = self._performance_note(summary, history_response.history, score_label, peer_rows, level)

        return PerformanceDetailResponse(
            level=level,
            key=key,
            title=title,
            subtitle=subtitle,
            month=month,
            summary=summary,
            history=history_response.history,
            daily=daily,
            score=score,
            score_breakdown=score_breakdown,
            score_label=score_label,
            note=note,
            strengths=strengths,
            risks=risks,
            peer_rows=peer_rows,
            context_summary=context_summary,
        )

    def _apply_agent_target_summary(self, summary: DashboardSummary, agent_stats: AgentStats) -> DashboardSummary:
        target = agent_stats.target or Decimal(0)
        target_progress_pct = (
            (summary.total_sales * Decimal(100) / target).quantize(_MONEY)
            if target > 0
            else None
        )
        forecast_target_progress_pct = (
            (summary.forecast_sales * Decimal(100) / target).quantize(_MONEY)
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

    def _performance_score_breakdown(self, summary: DashboardSummary) -> PerformanceScoreBreakdown:
        return score_breakdown(summary)

    def _performance_score(self, breakdown: PerformanceScoreBreakdown) -> int:
        return score_total(breakdown)

    def _bon2acc_score(self, value: Decimal) -> Decimal:
        return score_bon2acc(value)

    def _focus_score(self, value: Decimal) -> Decimal:
        return score_focus(value)

    def _performance_trend_sales(self, summary: DashboardSummary) -> Decimal:
        return trend_sales(summary)

    def _score_label(self, score: int) -> str:
        return score_label(score)

    def _performance_signals(
        self,
        summary: DashboardSummary,
        history: list[MonthlyHistoryPoint],
        level: Literal["regional", "store", "agent"],
    ) -> tuple[list[str], list[str]]:
        strengths: list[str] = []
        risks: list[str] = []
        target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct
        if target_pct is not None and target_pct >= 100:
            strengths.append("Ritmul proiectat acopera targetul lunii.")
        elif target_pct is not None and target_pct < 85:
            risks.append("Ritmul proiectat este sub 85% din target.")

        if summary.proc_bon2acc is not None and summary.proc_bon2acc > 35:
            strengths.append("Bon2Acc este foarte bine, peste 35%.")
        elif summary.proc_bon2acc is not None and summary.proc_bon2acc < 20:
            risks.append("Bon2Acc este critic scazut, sub 20%.")
        elif summary.proc_bon2acc is not None and summary.proc_bon2acc < 30:
            risks.append("Bon2Acc este scazut, sub 30%.")

        if summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty > 8:
            strengths.append("Focus-ul este bun, peste 8%.")
        elif summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty < 6:
            risks.append("Focus-ul este scazut, sub 6%.")

        previous = [point for point in history if point.month < summary.month and point.total_sales > 0][-3:]
        if previous:
            avg_previous = sum((point.total_sales for point in previous), Decimal(0)) / Decimal(len(previous))
            if avg_previous > 0:
                trend_sales = self._performance_trend_sales(summary)
                delta_pct = (trend_sales - avg_previous) * Decimal(100) / avg_previous
                entity_label = "agentul" if level == "agent" else "zona"
                if delta_pct >= 10:
                    strengths.append(f"{entity_label.capitalize()} este peste media ultimelor 3 luni.")
                elif delta_pct <= -10:
                    risks.append(f"{entity_label.capitalize()} este sub media ultimelor 3 luni.")

        return strengths[:3], risks[:3]

    def _performance_note(
        self,
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
                trend_sales = self._performance_trend_sales(summary)
                delta_pct = (trend_sales - avg_previous) * Decimal(100) / avg_previous
                trend_text = f"{delta_pct:+.1f}% vs media ultimelor 3 luni"
        selected_peer = next((peer for peer in peer_rows if peer.is_selected), None)
        peer_text = f"rank {selected_peer.rank} in grupul comparabil" if selected_peer else "fara comparatie peer"
        label = {"regional": "RM-ul", "store": "Magazinul", "agent": "Agentul"}[level]
        return f"{label} este in zona {score_label.lower()}: proiectie target {target_text}, {trend_text}, {peer_text}."

    def _regional_peer_rows(self, rows: list[RegionalStats], selected_key: str) -> list[PerformancePeerRow]:
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
        return self._compact_peer_rows(peers)

    def _store_peer_rows(self, rows: list[StoreStats], selected_site_code: str) -> list[PerformancePeerRow]:
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
        return self._compact_peer_rows(peers)

    def _agent_peer_rows(self, rows: list[AgentStats], selected_agent: str, selected_site_code: str) -> list[PerformancePeerRow]:
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
        return self._compact_peer_rows(peers)

    def _compact_peer_rows(self, peers: list[PerformancePeerRow]) -> list[PerformancePeerRow]:
        selected = next((row for row in peers if row.is_selected), None)
        compact = peers[:12]
        if selected is not None and all(row.rank != selected.rank for row in compact):
            compact = compact[:11] + [selected]
        return compact

    async def get_dashboard_all(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = False,
        include_closed_stores: bool = False,
        *,
        _history_projection: bool = False,
        deadline: RequestDeadline | None = None,
    ) -> DashboardAllResponse:
        async def load_campaign_context():
            async with self._pool_for(deadline).acquire() as conn:
                return await _load_dashboard_campaign_context(
                    conn,
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        # Campaign context is a dependency of several components.  It must be
        # scheduled through the same bounded/global gate as every other DB
        # component; starting a task here would let it acquire a pool
        # connection before the scheduler has admitted it.
        campaign_context: Any | None = None
        if not _history_projection:
            context_results = await gather_dashboard_phase(
                {
                    "campaign_context": observe_dashboard_component(
                        "campaign_context",
                        load_campaign_context(),
                    )
                },
                component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
                global_limit=self.dashboard_global_component_concurrency,
            )
            campaign_context = context_results["campaign_context"]

        async def get_agents_data() -> list[AgentStats]:
            async with self._pool_for(deadline).acquire() as conn:
                rows = await _fetch_agent_stats_rows(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
            row_dicts = [dict(row) for row in rows]
            if campaign_context is not None:
                apply_current_promo_metrics(
                    row_dicts,
                    campaign_context,
                    level="agent",
                )
            return [AgentStats(**row) for row in row_dicts]

        async def get_stores_data() -> list[StoreStats]:
            async with self._pool_for(deadline).acquire() as conn:
                rows = await _fetch_store_stats_rows(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                enriched_dicts = await _enrich_store_stats_with_campaign(
                    conn,
                    [dict(row) for row in rows],
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                if campaign_context is not None:
                    apply_current_promo_metrics(
                        enriched_dicts,
                        campaign_context,
                        level="store",
                    )
                return [StoreStats(**d) for d in enriched_dicts]

        async def get_daily_data() -> list[DailySalesPoint]:
            return await self.get_daily_sales(
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            )

        async def get_daily_last_year_data() -> list[DailySalesPoint]:
            async with self._pool_for(deadline).acquire() as conn:
                rows = await _fetch_daily_last_year_for_current_cohort(
                    conn,
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
            return [DailySalesPoint(**dict(row)) for row in rows]

        async def get_period_comparison_data(
            target_metric: str = "sales",
        ) -> PeriodComparisonPayload:
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_period_comparison(
                    conn,
                    target_metric=target_metric,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        async def get_category_mix_data() -> list[CategoryMixItem]:
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_category_mix(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        async def get_receipt_bucket_mix_data() -> list[ReceiptBucketItem]:
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_receipt_bucket_mix(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        async def get_focus_subcategory_mix_data() -> list[CategoryMixItem]:
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_focus_subcategory_mix(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        async def get_brand_mix_data() -> list[BrandMixItem]:
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_brand_mix(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )

        async def get_promo_incentive_data() -> PromoIncentiveSummary:
            assert campaign_context is not None
            async with self._pool_for(deadline).acquire() as conn:
                return await _fetch_promo_incentive_summary(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                    campaign_context=campaign_context,
                )

        async def get_special_cards_data(
            promo_incentive_summary: Awaitable[PromoIncentiveSummary],
        ) -> list[DashboardSpecialCard]:
            assert campaign_context is not None
            return await _get_special_cards_data(
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
                campaign_context=campaign_context,
                promo_incentive_summary=promo_incentive_summary,
                pool=self._pool_for(deadline),
            )

        async def get_premium_glass_data() -> PremiumGlassAnalysis:
            return await self.get_premium_glass(
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=True,
                include_closed_stores=include_closed_stores,
                deadline=deadline,
            )

        async def get_regional_data() -> list[RegionalStats]:
            async with self._pool_for(deadline).acquire() as conn:
                rows = await _fetch_regional_stats(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
                row_dicts = [dict(row) for row in rows]
                if campaign_context is not None:
                    promo_sites = sorted(
                        {
                            key[0]
                            for key in campaign_context.promo_excluded_units
                        }
                    )
                    site_regionals: dict[str, str] = {}
                    if promo_sites:
                        if current_scope:
                            mapping_rows = await conn.fetch(
                                """
                                SELECT site_code, regional
                                FROM stores
                                WHERE site_code = ANY($1::TEXT[])
                                """,
                                promo_sites,
                            )
                        else:
                            mapping_rows = await conn.fetch(
                                """
                                SELECT DISTINCT ON (site_code) site_code, regional
                                FROM reporting_agent_month
                                WHERE import_month = $1
                                  AND site_code = ANY($2::TEXT[])
                                ORDER BY site_code, regional
                                """,
                                month,
                                promo_sites,
                            )
                        site_regionals = {
                            str(row["site_code"]): str(row["regional"])
                            for row in mapping_rows
                        }
                    apply_current_promo_metrics(
                        row_dicts,
                        campaign_context,
                        level="regional",
                        site_regionals=site_regionals,
                    )
            return [RegionalStats(**row) for row in row_dicts]

        async def get_asm_data() -> list[AsmStats]:
            async with self._pool_for(deadline).acquire() as conn:
                rows = await _fetch_asm_stats(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                )
            return [AsmStats(**r) for r in rows]

        components: dict[str, Awaitable[Any]] = {
            "summary": observe_dashboard_component(
                "summary",
                self.get_summary(
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                    current_scope=current_scope,
                    include_closed_stores=include_closed_stores,
                    deadline=deadline,
                ),
            ),
            "agents": observe_dashboard_component("agents", get_agents_data()),
            "stores": observe_dashboard_component("stores", get_stores_data()),
            "daily": observe_dashboard_component("daily", get_daily_data()),
            "period_comparison": observe_dashboard_component(
                "period_comparison", get_period_comparison_data()
            ),
            "category_mix": observe_dashboard_component("category_mix", get_category_mix_data()),
            "receipt_bucket_mix": observe_dashboard_component(
                "receipt_bucket_mix", get_receipt_bucket_mix_data()
            ),
            "focus_subcategory_mix": observe_dashboard_component(
                "focus_subcategory_mix", get_focus_subcategory_mix_data()
            ),
            "brand_mix": observe_dashboard_component("brand_mix", get_brand_mix_data()),
            "regionals": observe_dashboard_component("regionals", get_regional_data()),
            "asms": observe_dashboard_component("asms", get_asm_data()),
        }
        if not _history_projection:
            components.update(
                promo_incentive=observe_dashboard_component(
                    "promo_incentive", get_promo_incentive_data()
                ),
                premium_glass=observe_dashboard_component(
                    "premium_glass", get_premium_glass_data()
                ),
                daily_last_year=observe_dashboard_component(
                    "daily_last_year", get_daily_last_year_data()
                ),
            )
        component_results = await gather_dashboard_phase(
            components,
            component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
            global_limit=self.dashboard_global_component_concurrency,
        )
        if not _history_projection:
            # Special cards consume the already materialized summary.  Keep
            # this as a second scheduled phase instead of letting a component
            # occupy a global slot while awaiting another component.
            promo_incentive = cast(
                PromoIncentiveSummary, component_results["promo_incentive"]
            )
            resolved_promo: asyncio.Future[PromoIncentiveSummary] = (
                asyncio.get_running_loop().create_future()
            )
            resolved_promo.set_result(promo_incentive)
            dependent_results = await gather_dashboard_phase(
                {
                    "special_cards": observe_dashboard_component(
                        "special_cards", get_special_cards_data(resolved_promo)
                    )
                },
                component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
                global_limit=self.dashboard_global_component_concurrency,
            )
            component_results.update(dependent_results)
        summary = cast(DashboardSummary, component_results["summary"])
        agents_stats = cast(list[AgentStats], component_results["agents"])
        stores_stats = cast(list[StoreStats], component_results["stores"])
        daily_sales = cast(list[DailySalesPoint], component_results["daily"])
        period_comparison = cast(
            PeriodComparisonPayload | None,
            component_results["period_comparison"],
        )
        category_mix = cast(list[CategoryMixItem], component_results["category_mix"])
        receipt_bucket_mix = cast(
            list[ReceiptBucketItem], component_results["receipt_bucket_mix"]
        )
        focus_subcategory_mix = cast(
            list[CategoryMixItem], component_results["focus_subcategory_mix"]
        )
        brand_mix = cast(list[BrandMixItem], component_results["brand_mix"])
        regional_stats = cast(list[RegionalStats], component_results["regionals"])
        asm_stats = cast(list[AsmStats], component_results["asms"])
        promo_incentive = PromoIncentiveSummary()
        special_cards: list[DashboardSpecialCard] = []
        premium_glass: PremiumGlassAnalysis | None = None
        daily_last_year: list[DailySalesPoint] = []
        if not _history_projection:
            promo_incentive = cast(
                PromoIncentiveSummary, component_results["promo_incentive"]
            )
            special_cards = cast(
                list[DashboardSpecialCard], component_results["special_cards"]
            )
            premium_glass = cast(
                PremiumGlassAnalysis, component_results["premium_glass"]
            )
            daily_last_year = cast(
                list[DailySalesPoint], component_results["daily_last_year"]
            )
            special_cards = [*special_cards, build_premium_glass_card(premium_glass)]

        return DashboardAllResponse(
            summary=summary,
            agents=agents_stats,
            stores=stores_stats,
            daily=daily_sales,
            special_cards=special_cards,
            period_comparison=period_comparison,
            category_mix=category_mix,
            receipt_bucket_mix=receipt_bucket_mix,
            focus_subcategory_mix=focus_subcategory_mix,
            brand_mix=brand_mix,
            promo_incentive=promo_incentive,
            premium_glass=premium_glass,
            regionals=regional_stats,
            asms=asm_stats,
            daily_last_year=daily_last_year,
        )

    async def get_dashboard_all_batch(
        self,
        queries: list[DashboardAllQuery],
        *,
        deadline: RequestDeadline | None = None,
    ) -> DashboardAllBatchResponse:
        return await load_dashboard_all_batch(self, queries, deadline=deadline)

    async def get_dashboard_history_details_batch(
        self,
        queries: list[DashboardAllQuery],
        *,
        deadline: RequestDeadline | None = None,
    ) -> DashboardAllBatchResponse:
        return await load_dashboard_history_details_batch(self, queries, deadline=deadline)
