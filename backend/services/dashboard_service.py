from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Literal

import asyncpg

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
