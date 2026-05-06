from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import asyncpg

from models import (
    DashboardSummary,
    DashboardAllResponse,
    DailySalesPoint,
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
)
from services.dashboard.specials_data import _get_special_cards_data
from services.dashboard.utils import _build_scoped_params
from services.filters import normalize_filter, scoped_clauses


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
    ) -> DashboardSummary:
        params, positions = _build_scoped_params(
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
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
        )

        row = await self.repo.fetch_summary(clauses, params)
        if row is None:
            return DashboardSummary(
                month=month,
                total_sales=0,
                total_target=0,
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
    ) -> list[DailySalesPoint]:
        params, positions = _build_scoped_params(
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
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
        )

        rows = await self.repo.fetch_daily_sales(clauses, params)
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
        return DashboardSpecialCardsResponse(cards=cards)

    async def get_monthly_history(
        self,
        month: str,
        months_back: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> DashboardHistoryResponse:
        params: list[Any] = [month, months_back]
        positions: dict[str, int] = {}
        for key, value in [
            ("firma", normalize_filter(firma)),
            ("regional", normalize_filter(regional)),
            ("asm", normalize_filter(asm)),
            ("site_code", normalize_filter(site_code)),
            ("agent", normalize_filter(agent)),
        ]:
            if value is not None:
                params.append(value)
                positions[key] = len(params)

        sales_clauses: list[str] = []
        sales_clauses.extend(
            scoped_clauses(
                positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
                month_alias=None,
            )
        )

        rows = await self.repo.fetch_monthly_history(sales_clauses, params)
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
    ) -> YearHistoryResponse:
        _firma = normalize_filter(firma)
        _regional = normalize_filter(regional)
        _asm = normalize_filter(asm)
        _site_code = normalize_filter(site_code)
        _agent = normalize_filter(agent)

        points: list[YearHistoryPoint] = []

        if year <= 2023 and _agent is None:
            hist_params: list[Any] = [year]
            hist_clauses: list[str] = []
            if year == 2023:
                hist_clauses.append("has.is_partial_year = TRUE")
            p = 2
            for val, col in [
                (_firma, "has.firma"),
                (_regional, "s.regional"),
                (_asm, "s.asm"),
                (_site_code, "has.site_code"),
            ]:
                if val is not None:
                    hist_clauses.append(f"{col} = ${p}")
                    hist_params.append(val)
                    p += 1

            row = await self.repo.fetch_year_history_agg(year, hist_clauses, hist_params)
            if row and row["total_sales"] > 0:
                points.append(
                    YearHistoryPoint(
                        label="Ian–Aug" if year == 2023 else "2022",
                        sort_key=f"{year}-00",
                        total_sales=row["total_sales"],
                        total_target=Decimal(0),
                        total_quantity=row["total_quantity"],
                        is_aggregate=True,
                    )
                )

        start_month = f"{year}-09" if year == 2023 else f"{year}-01"
        end_month = f"{year}-12"

        rep_params: list[Any] = [start_month, end_month]
        rep_clauses: list[str] = []
        p = 3
        for val, col in [
            (_firma, "agg.firma"),
            (_regional, "agg.regional"),
            (_asm, "agg.asm"),
            (_site_code, "agg.site_code"),
            (_agent, "agg.agent"),
        ]:
            if val is not None:
                rep_clauses.append(f"{col} = ${p}")
                rep_params.append(val)
                p += 1

        rows = await self.repo.fetch_year_history_monthly(rep_clauses, rep_params)

        for r in rows:
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
    ) -> DashboardAllResponse:
        
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
                    agent
                )
                return [StoreStats(**d) for d in enriched_dicts]

        async def get_daily_data() -> list[DailySalesPoint]:
            return await self.get_daily_sales(
                month, firma, regional, asm, site_code, agent
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
                )

        async def get_promo_incentive_data() -> PromoIncentiveSummary:
            async with self.pool.acquire() as conn:
                return await _fetch_promo_incentive_summary(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )

        async def get_regional_data() -> list[RegionalStats]:
            async with self.pool.acquire() as conn:
                return await _fetch_regional_stats(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )

        async def get_asm_data() -> list[AsmStats]:
            async with self.pool.acquire() as conn:
                return await _fetch_asm_stats(
                    conn,
                    month=month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )

        (
            summary,
            agents_stats,
            stores_stats,
            daily_sales,
            period_comparison,
            category_mix,
            receipt_bucket_mix,
            focus_subcategory_mix,
            brand_mix,
            promo_incentive,
            regional_stats,
            asm_stats,
            special_cards,
        ) = await asyncio.gather(
            self.get_summary(month, firma, regional, asm, site_code, agent),
            get_agents_data(),
            get_stores_data(),
            get_daily_data(),
            get_period_comparison_data(),
            get_category_mix_data(),
            get_receipt_bucket_mix_data(),
            get_focus_subcategory_mix_data(),
            get_brand_mix_data(),
            get_promo_incentive_data(),
            get_regional_data(),
            get_asm_data(),
            _get_special_cards_data(month, firma, regional, asm, site_code, agent),
        )

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
            regionals=regional_stats,
            asms=asm_stats,
        )
