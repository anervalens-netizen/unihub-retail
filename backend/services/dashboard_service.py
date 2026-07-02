from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Literal

import asyncpg
from fastapi import HTTPException, status

from models import (
    DashboardSummary,
    DashboardAllResponse,
    DailySalesPoint,
    DashboardSpecialCard,
    DashboardSpecialCardsResponse,
    DashboardHistoryResponse,
    MonthlyHistoryPoint,
    YearHistoryResponse,
    YearHistoryPoint,
    AgentStats,
    StoreStats,
    PeriodComparisonPayload,
    CategoryMixItem,
    ReceiptBucketItem,
    BrandMixItem,
    PromoIncentiveSummary,
    PremiumGlassAnalysis,
    PerformanceDetailResponse,
    PerformancePeerRow,
    RegionalStats,
    AsmStats,
)
from repositories.dashboard import DashboardRepository
from services.dashboard.queries import (
    _enrich_store_stats_with_campaign,
    _fetch_agent_stats_rows,
    _fetch_asm_stats,
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_focus_subcategory_mix,
    _fetch_period_comparison,
    _fetch_promo_incentive_summary,
    _fetch_receipt_bucket_mix,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
    _load_dashboard_campaign_context,
)
from services.dashboard.specials_data import _get_special_cards_data
from services.dashboard.metrics import observe_dashboard_component
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, normalize_filter, scoped_clauses
from services.premium_glass import build_premium_glass_card, get_premium_glass_analysis


_RO_MONTHS = {
    1: "Ian", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Iun",
    7: "Iul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


class DashboardService:
    def __init__(self, repo: DashboardRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

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

        row = await self.repo.fetch_summary(clauses, params, cartela_clauses, current_scope)
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

        rows = await self.repo.fetch_daily_sales(clauses, params, current_scope)
        return [DailySalesPoint(**dict(row)) for row in rows]

    async def get_special_cards(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> DashboardSpecialCardsResponse:
        cards = await _get_special_cards_data(
            month, firma, regional, asm, site_code, agent
        )
        async with self.pool.acquire() as conn:
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
    ) -> PremiumGlassAnalysis:
        async with self.pool.acquire() as conn:
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

        rows = await self.repo.fetch_monthly_history(sales_clauses, params, current_scope)
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
    ) -> YearHistoryResponse:
        _firma = normalize_filter(firma)
        _regional = normalize_filter(regional)
        _asm = normalize_filter(asm)
        _site_code = normalize_filter(site_code)
        _agent = normalize_filter(agent)

        points: list[YearHistoryPoint] = []

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

        rows = await self.repo.fetch_year_history_monthly(rep_clauses, rep_params)
        visible_rows = [
            r
            for r in rows
            if r["total_sales"] > 0 or r["total_target"] > 0 or r["total_quantity"] > 0
        ]
        has_monthly_sales = any(r["total_sales"] > 0 or r["total_quantity"] > 0 for r in visible_rows)

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

            row = await self.repo.fetch_year_history_agg(year, hist_clauses, hist_params)
            if row and row["total_sales"] > 0:
                points.append(
                    YearHistoryPoint(
                        label="Ian-Aug" if year == 2023 else str(year),
                        sort_key=f"{year}-00",
                        total_sales=row["total_sales"],
                        total_target=Decimal(0),
                        total_quantity=row["total_quantity"],
                        is_aggregate=True,
                    )
                )

        for r in visible_rows:
            month_num = int(r["import_month"][5:7])
            points.append(
                YearHistoryPoint(
                    label=_RO_MONTHS[month_num],
                    sort_key=r["import_month"],
                    total_sales=r["total_sales"],
                    total_target=r["total_target"],
                    total_quantity=r["total_quantity"],
                    is_aggregate=False,
                )
            )

        return YearHistoryResponse(points=points)

    async def get_performance_detail(
        self,
        month: str,
        level: Literal["regional", "store", "agent"],
        key: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
        current_scope: bool = True,
        include_closed_stores: bool = False,
    ) -> PerformanceDetailResponse:
        del regional, asm, agent
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

        async with self.pool.acquire() as conn:
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
                effective_site_code = normalize_filter(site_code)
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

        summary, history_response, daily = await asyncio.gather(
            self.get_summary(
                month,
                effective_firma if level == "regional" else None,
                effective_regional,
                None,
                effective_site_code,
                effective_agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
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
            ),
        )

        if level == "agent" and effective_site_code:
            context_summary = await self.get_summary(
                month,
                None,
                None,
                None,
                effective_site_code,
                None,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )

        score = self._performance_score(summary)
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
            score_label=score_label,
            note=note,
            strengths=strengths,
            risks=risks,
            peer_rows=peer_rows,
            context_summary=context_summary,
        )

    def _performance_score(self, summary: DashboardSummary) -> int:
        target_pct = summary.forecast_target_progress_pct or summary.target_progress_pct or Decimal(0)
        bon_pct = summary.proc_bon2acc or Decimal(0)
        focus_pct = summary.prc_focus_acc_qty or Decimal(0)
        target_score = min(max(float(target_pct), 0.0), 120.0) / 120.0 * 60.0
        bon_score = min(max(float(bon_pct), 0.0), 60.0) / 60.0 * 20.0
        focus_score = min(max(float(focus_pct), 0.0), 35.0) / 35.0 * 20.0
        return max(0, min(100, round(target_score + bon_score + focus_score)))

    def _score_label(self, score: int) -> str:
        if score >= 85:
            return "Foarte bine"
        if score >= 70:
            return "Bun"
        if score >= 55:
            return "De urmarit"
        return "Necesita interventie"

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

        if summary.proc_bon2acc is not None and summary.proc_bon2acc >= 40:
            strengths.append("Bon2Acc este peste pragul operational de 40%.")
        elif summary.proc_bon2acc is not None and summary.proc_bon2acc < 25:
            risks.append("Bon2Acc este sub 25%, merita urmarit in coaching.")

        if summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty >= 25:
            strengths.append("Mixul de focus este sanatos fata de cantitatea totala.")
        elif summary.prc_focus_acc_qty is not None and summary.prc_focus_acc_qty < 15:
            risks.append("Focus-ul este redus in mixul de accesorii.")

        previous = [point for point in history if point.month < summary.month and point.total_sales > 0][-3:]
        if previous:
            avg_previous = sum((point.total_sales for point in previous), Decimal(0)) / Decimal(len(previous))
            if avg_previous > 0:
                delta_pct = (summary.total_sales - avg_previous) * Decimal(100) / avg_previous
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
                delta_pct = (summary.total_sales - avg_previous) * Decimal(100) / avg_previous
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
    ) -> DashboardAllResponse:
        async def load_campaign_context():
            async with self.pool.acquire() as conn:
                return await _load_dashboard_campaign_context(
                    conn,
                    month,
                    firma,
                    regional,
                    asm,
                    site_code,
                    agent,
                )

        campaign_context_task = asyncio.create_task(
            observe_dashboard_component(
                "campaign_context",
                load_campaign_context(),
            )
        )

        async def get_agents_data() -> list[AgentStats]:
            async with self.pool.acquire() as conn:
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
            return [AgentStats(**dict(row)) for row in rows]

        async def get_stores_data() -> list[StoreStats]:
            async with self.pool.acquire() as conn:
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
                stats = [StoreStats(**dict(row)) for row in rows]
                # convert back to dict for the enrich function since it expects list[dict]
                # wait, _enrich_store_stats_with_campaign returns list[dict] and takes list[dict]
                # let's look at the type signature of StoreStats, we should return list[StoreStats]
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
            )

        async def get_daily_last_year_data() -> list[DailySalesPoint]:
            year, mon = month.split("-")
            last_year_month = f"{int(year) - 1}-{mon}"
            return await self.get_daily_sales(
                last_year_month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                current_scope=current_scope,
                include_closed_stores=include_closed_stores,
            )

        async def get_period_comparison_data(
            target_metric: str = "sales",
        ) -> PeriodComparisonPayload:
            async with self.pool.acquire() as conn:
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
            async with self.pool.acquire() as conn:
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
            async with self.pool.acquire() as conn:
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
            async with self.pool.acquire() as conn:
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
            async with self.pool.acquire() as conn:
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
            campaign_context = await campaign_context_task
            async with self.pool.acquire() as conn:
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

        async def get_special_cards_data() -> list[DashboardSpecialCard]:
            campaign_context = await campaign_context_task
            return await _get_special_cards_data(
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
                campaign_context=campaign_context,
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
            )

        async def get_regional_data() -> list[RegionalStats]:
            async with self.pool.acquire() as conn:
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
            return [RegionalStats(**r) for r in rows]

        async def get_asm_data() -> list[AsmStats]:
            async with self.pool.acquire() as conn:
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

        results = await asyncio.gather(
            observe_dashboard_component(
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
                ),
            ),
            observe_dashboard_component("agents", get_agents_data()),
            observe_dashboard_component("stores", get_stores_data()),
            observe_dashboard_component("daily", get_daily_data()),
            observe_dashboard_component(
                "period_comparison", get_period_comparison_data()
            ),
            observe_dashboard_component("category_mix", get_category_mix_data()),
            observe_dashboard_component(
                "receipt_bucket_mix", get_receipt_bucket_mix_data()
            ),
            observe_dashboard_component(
                "focus_subcategory_mix", get_focus_subcategory_mix_data()
            ),
            observe_dashboard_component("brand_mix", get_brand_mix_data()),
            observe_dashboard_component(
                "promo_incentive", get_promo_incentive_data()
            ),
            observe_dashboard_component("regionals", get_regional_data()),
            observe_dashboard_component("asms", get_asm_data()),
            observe_dashboard_component("special_cards", get_special_cards_data()),
            observe_dashboard_component("premium_glass", get_premium_glass_data()),
            observe_dashboard_component(
                "daily_last_year", get_daily_last_year_data()
            ),
        )
        summary: DashboardSummary = results[0]  # type: ignore[assignment]
        agents_stats: list[AgentStats] = results[1]  # type: ignore[assignment]
        stores_stats: list[StoreStats] = results[2]  # type: ignore[assignment]
        daily_sales: list[DailySalesPoint] = results[3]  # type: ignore[assignment]
        period_comparison: PeriodComparisonPayload | None = results[4]  # type: ignore[assignment]
        category_mix: list[CategoryMixItem] = results[5]  # type: ignore[assignment]
        receipt_bucket_mix: list[ReceiptBucketItem] = results[6]  # type: ignore[assignment]
        focus_subcategory_mix: list[CategoryMixItem] = results[7]  # type: ignore[assignment]
        brand_mix: list[BrandMixItem] = results[8]  # type: ignore[assignment]
        promo_incentive: PromoIncentiveSummary = results[9]  # type: ignore[assignment]
        regional_stats: list[RegionalStats] = results[10]  # type: ignore[assignment]
        asm_stats: list[AsmStats] = results[11]  # type: ignore[assignment]
        special_cards: list[DashboardSpecialCard] = results[12]  # type: ignore[assignment]
        premium_glass: PremiumGlassAnalysis = results[13]  # type: ignore[assignment]
        daily_last_year: list[DailySalesPoint] = results[14]  # type: ignore[assignment]
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
