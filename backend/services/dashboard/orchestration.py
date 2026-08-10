"""Bounded orchestration for the composed Dashboard response."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
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
    async def get_campaign_context_data():
        async with service._pool_for(deadline).acquire() as conn:
            return await load_campaign_context(
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
                    get_campaign_context_data(),
                )
            },
            component_limit=DASHBOARD_COMPONENT_CONCURRENCY,
            global_limit=service.dashboard_global_component_concurrency,
        )
        campaign_context = context_results["campaign_context"]

    async def get_agents_data() -> list[AgentStats]:
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        return await service.get_daily_sales(
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
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
        async with service._pool_for(deadline).acquire() as conn:
            return await fetch_promo_incentive_summary(
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
            pool=service._pool_for(deadline),
        )

    async def get_premium_glass_data() -> PremiumGlassAnalysis:
        return await service.get_premium_glass(
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
        async with service._pool_for(deadline).acquire() as conn:
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
        return [RegionalStats(**public_stats_row(row)) for row in row_dicts]

    async def get_asm_data() -> list[AsmStats]:
        async with service._pool_for(deadline).acquire() as conn:
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
        return [AsmStats(**public_stats_row(r)) for r in rows]

    components: dict[str, Awaitable[Any]] = {
        "summary": observe_dashboard_component(
            "summary",
            service.get_summary(
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
        global_limit=service.dashboard_global_component_concurrency,
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
            global_limit=service.dashboard_global_component_concurrency,
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
