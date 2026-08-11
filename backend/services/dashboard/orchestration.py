"""Bounded orchestration for the composed Dashboard response."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

from schemas.campaigns import PromoIncentiveSummary
from schemas.dashboard import (
    AgentStats,
    AsmStats,
    BrandMixItem,
    CategoryMixItem,
    DashboardAllResponse,
    DashboardSpecialCard,
    DashboardSummary,
    DailySalesPoint,
    PeriodComparisonPayload,
    ReceiptBucketItem,
    RegionalStats,
    StoreStats,
)
from schemas.premium_glass import PremiumGlassAnalysis
from services.campaigns import fetch_promo_incentive_summary, load_campaign_context
from services.dashboard.metrics import observe_dashboard_component
from services.dashboard.ports import DashboardServicePort
from services.dashboard.projections import public_stats_row
from services.dashboard.queries import (
    _enrich_store_stats_with_campaign,
    _fetch_agent_stats_rows,
    _fetch_asm_stats,
    _fetch_brand_mix,
    _fetch_category_mix,
    _fetch_daily_last_year_for_current_cohort,
    _fetch_focus_subcategory_mix,
    _fetch_period_comparison,
    _fetch_receipt_bucket_mix,
    _fetch_regional_stats,
    _fetch_store_stats_rows,
    apply_current_promo_metrics,
)
from services.dashboard.scheduler import (
    DASHBOARD_COMPONENT_CONCURRENCY,
    _gather_named,
)
from services.dashboard.specials_data import _get_special_cards_data
from services.premium_glass import build_premium_glass_card
from services.request_deadline import RequestDeadline


async def gather_dashboard_phase(
    components: dict[str, Awaitable[Any]],
    *,
    component_limit: int,
    global_limit: int,
) -> dict[str, Any]:
    """Resolve one dependency phase through the shared Dashboard scheduler."""
    return await _gather_named(component_limit, global_limit, **components)


@dataclass
class DashboardAllLoader:
    service: DashboardServicePort
    month: str
    firma: str | None
    regional: str | None
    asm: str | None
    site_code: str | None
    agent: str | None
    current_scope: bool
    include_closed_stores: bool
    history_projection: bool
    deadline: RequestDeadline | None
    campaign_context: Any | None = None

    @property
    def query_kwargs(self) -> dict[str, Any]:
        return {
            "month": self.month, "firma": self.firma, "regional": self.regional,
            "asm": self.asm, "site_code": self.site_code, "agent": self.agent,
            "current_scope": self.current_scope,
            "include_closed_stores": self.include_closed_stores,
        }

    async def load_campaign(self) -> Any:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await load_campaign_context(
                conn, self.month, self.firma, self.regional, self.asm,
                self.site_code, self.agent, current_scope=self.current_scope,
                include_closed_stores=self.include_closed_stores,
            )

    async def agents_data(self) -> list[AgentStats]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            rows = await _fetch_agent_stats_rows(conn, **self.query_kwargs)
        result = [dict(row) for row in rows]
        if self.campaign_context is not None:
            apply_current_promo_metrics(result, self.campaign_context, level="agent")
        return [AgentStats(**row) for row in result]

    async def stores_data(self) -> list[StoreStats]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            rows = await _fetch_store_stats_rows(conn, **self.query_kwargs)
            result = await _enrich_store_stats_with_campaign(
                conn, [dict(row) for row in rows], self.month, self.firma, self.regional,
                self.asm, self.site_code, self.agent, current_scope=self.current_scope,
                include_closed_stores=self.include_closed_stores,
            )
            if self.campaign_context is not None:
                apply_current_promo_metrics(result, self.campaign_context, level="store")
        return [StoreStats(**row) for row in result]

    async def daily_data(self) -> list[DailySalesPoint]:
        return await self.service.get_daily_sales(
            self.month, self.firma, self.regional, self.asm, self.site_code, self.agent,
            current_scope=self.current_scope, include_closed_stores=self.include_closed_stores,
            deadline=self.deadline,
        )

    async def daily_last_year_data(self) -> list[DailySalesPoint]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            rows = await _fetch_daily_last_year_for_current_cohort(
                conn, self.month, self.firma, self.regional, self.asm, self.site_code, self.agent,
                current_scope=self.current_scope, include_closed_stores=self.include_closed_stores,
            )
        return [DailySalesPoint(**dict(row)) for row in rows]

    async def period_comparison_data(self) -> PeriodComparisonPayload:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await _fetch_period_comparison(conn, target_metric="sales", **self.query_kwargs)

    async def category_mix_data(self) -> list[CategoryMixItem]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await _fetch_category_mix(conn, **self.query_kwargs)

    async def receipt_bucket_mix_data(self) -> list[ReceiptBucketItem]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await _fetch_receipt_bucket_mix(conn, **self.query_kwargs)

    async def focus_subcategory_mix_data(self) -> list[CategoryMixItem]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await _fetch_focus_subcategory_mix(conn, **self.query_kwargs)

    async def brand_mix_data(self) -> list[BrandMixItem]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await _fetch_brand_mix(conn, **self.query_kwargs)

    async def promo_incentive_data(self) -> PromoIncentiveSummary:
        assert self.campaign_context is not None
        async with self.service._pool_for(self.deadline).acquire() as conn:
            return await fetch_promo_incentive_summary(
                conn, campaign_context=self.campaign_context, **self.query_kwargs,
            )

    async def special_cards_data(
        self, promo_summary: Awaitable[PromoIncentiveSummary],
    ) -> list[DashboardSpecialCard]:
        assert self.campaign_context is not None
        return await _get_special_cards_data(
            self.month, self.firma, self.regional, self.asm, self.site_code, self.agent,
            current_scope=self.current_scope, include_closed_stores=self.include_closed_stores,
            campaign_context=self.campaign_context, promo_incentive_summary=promo_summary,
            pool=self.service._pool_for(self.deadline),
        )

    async def premium_glass_data(self) -> PremiumGlassAnalysis:
        return await self.service.get_premium_glass(
            self.month, self.firma, self.regional, self.asm, self.site_code, self.agent,
            current_scope=True, include_closed_stores=self.include_closed_stores,
            deadline=self.deadline,
        )

    async def regional_data(self) -> list[RegionalStats]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            rows = await _fetch_regional_stats(conn, **self.query_kwargs)
            row_dicts = [dict(row) for row in rows]
            if self.campaign_context is not None:
                promo_sites = sorted({key[0] for key in self.campaign_context.promo_excluded_units})
                site_regionals: dict[str, str] = {}
                if promo_sites:
                    if self.current_scope:
                        mapping_rows = await conn.fetch(
                            "SELECT site_code, regional FROM stores WHERE site_code = ANY($1::TEXT[])",
                            promo_sites,
                        )
                    else:
                        mapping_rows = await conn.fetch(
                            """
                            SELECT DISTINCT ON (site_code) site_code, regional
                            FROM reporting_agent_month
                            WHERE import_month = $1 AND site_code = ANY($2::TEXT[])
                            ORDER BY site_code, regional
                            """,
                            self.month, promo_sites,
                        )
                    site_regionals = {
                        str(row["site_code"]): str(row["regional"]) for row in mapping_rows
                    }
                apply_current_promo_metrics(
                    row_dicts, self.campaign_context, level="regional",
                    site_regionals=site_regionals,
                )
        return [RegionalStats(**public_stats_row(row)) for row in row_dicts]

    async def asm_data(self) -> list[AsmStats]:
        async with self.service._pool_for(self.deadline).acquire() as conn:
            rows = await _fetch_asm_stats(conn, **self.query_kwargs)
        return [AsmStats(**public_stats_row(row)) for row in rows]

    def base_components(self) -> dict[str, Awaitable[Any]]:
        components: dict[str, Awaitable[Any]] = {
            "summary": observe_dashboard_component("summary", self.service.get_summary(
                self.month, self.firma, self.regional, self.asm, self.site_code, self.agent,
                current_scope=self.current_scope, include_closed_stores=self.include_closed_stores,
                deadline=self.deadline,
            )),
            "agents": observe_dashboard_component("agents", self.agents_data()),
            "stores": observe_dashboard_component("stores", self.stores_data()),
            "daily": observe_dashboard_component("daily", self.daily_data()),
            "period_comparison": observe_dashboard_component("period_comparison", self.period_comparison_data()),
            "category_mix": observe_dashboard_component("category_mix", self.category_mix_data()),
            "receipt_bucket_mix": observe_dashboard_component("receipt_bucket_mix", self.receipt_bucket_mix_data()),
            "focus_subcategory_mix": observe_dashboard_component("focus_subcategory_mix", self.focus_subcategory_mix_data()),
            "brand_mix": observe_dashboard_component("brand_mix", self.brand_mix_data()),
            "regionals": observe_dashboard_component("regionals", self.regional_data()),
            "asms": observe_dashboard_component("asms", self.asm_data()),
        }
        if not self.history_projection:
            components.update(
                promo_incentive=observe_dashboard_component("promo_incentive", self.promo_incentive_data()),
                premium_glass=observe_dashboard_component("premium_glass", self.premium_glass_data()),
                daily_last_year=observe_dashboard_component("daily_last_year", self.daily_last_year_data()),
            )
        return components

    async def run(self) -> DashboardAllResponse:
        if not self.history_projection:
            result = await gather_dashboard_phase(
                {"campaign_context": observe_dashboard_component("campaign_context", self.load_campaign())},
                component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
                global_limit=self.service.dashboard_global_component_concurrency,
            )
            self.campaign_context = result["campaign_context"]
        results = await gather_dashboard_phase(
            self.base_components(), component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
            global_limit=self.service.dashboard_global_component_concurrency,
        )
        if not self.history_projection:
            promo = cast(PromoIncentiveSummary, results["promo_incentive"])
            resolved: asyncio.Future[PromoIncentiveSummary] = asyncio.get_running_loop().create_future()
            resolved.set_result(promo)
            results.update(await gather_dashboard_phase(
                {"special_cards": observe_dashboard_component("special_cards", self.special_cards_data(resolved))},
                component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
                global_limit=self.service.dashboard_global_component_concurrency,
            ))
        return self.response(results)

    def response(self, results: dict[str, Any]) -> DashboardAllResponse:
        promo = PromoIncentiveSummary()
        special_cards: list[DashboardSpecialCard] = []
        premium: PremiumGlassAnalysis | None = None
        daily_last_year: list[DailySalesPoint] = []
        if not self.history_projection:
            promo = cast(PromoIncentiveSummary, results["promo_incentive"])
            special_cards = cast(list[DashboardSpecialCard], results["special_cards"])
            premium = cast(PremiumGlassAnalysis, results["premium_glass"])
            daily_last_year = cast(list[DailySalesPoint], results["daily_last_year"])
            special_cards = [*special_cards, build_premium_glass_card(premium)]
        return DashboardAllResponse(
            summary=cast(DashboardSummary, results["summary"]),
            agents=cast(list[AgentStats], results["agents"]),
            stores=cast(list[StoreStats], results["stores"]),
            daily=cast(list[DailySalesPoint], results["daily"]),
            special_cards=special_cards,
            period_comparison=cast(PeriodComparisonPayload | None, results["period_comparison"]),
            category_mix=cast(list[CategoryMixItem], results["category_mix"]),
            receipt_bucket_mix=cast(list[ReceiptBucketItem], results["receipt_bucket_mix"]),
            focus_subcategory_mix=cast(list[CategoryMixItem], results["focus_subcategory_mix"]),
            brand_mix=cast(list[BrandMixItem], results["brand_mix"]),
            promo_incentive=promo, premium_glass=premium,
            regionals=cast(list[RegionalStats], results["regionals"]),
            asms=cast(list[AsmStats], results["asms"]), daily_last_year=daily_last_year,
        )


async def load_dashboard_all(
    service: DashboardServicePort,
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
    return await DashboardAllLoader(
        service=service, month=month, firma=firma, regional=regional, asm=asm,
        site_code=site_code, agent=agent, current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        history_projection=_history_projection, deadline=deadline,
    ).run()
