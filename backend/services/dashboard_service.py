"""Stable Dashboard service facade delegating to domain operation modules."""

from __future__ import annotations

from typing import Any, Literal

import asyncpg

from config import RuntimeConfig
from repositories.dashboard import DashboardRepository
from schemas.dashboard import (
    DashboardAllBatchResponse,
    DashboardAllQuery,
    DashboardAllResponse,
    DashboardHistoryResponse,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    DailySalesPoint,
    PerformanceDetailResponse,
    YearHistoryResponse,
)
from schemas.premium_glass import PremiumGlassAnalysis
from services.dashboard.batch import (
    load_dashboard_all_batch,
    load_dashboard_history_details_batch,
)
from services.dashboard.history import load_history_by_year, load_monthly_history
from services.dashboard.orchestration import load_dashboard_all
from services.dashboard.performance import load_performance_detail
from services.dashboard.scheduler import DEFAULT_DASHBOARD_GLOBAL_COMPONENT_CONCURRENCY
from services.dashboard.views import (
    load_daily_sales,
    load_premium_glass,
    load_special_cards,
    load_summary,
)
from services.request_deadline import RequestDeadline


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
        return await load_summary(
            self, month, firma, regional, asm, site_code, agent,
            current_scope, include_closed_stores, deadline=deadline,
        )

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
        return await load_daily_sales(
            self, month, firma, regional, asm, site_code, agent,
            current_scope, include_closed_stores, deadline=deadline,
        )

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
        return await load_special_cards(
            self, month, firma, regional, asm, site_code, agent, deadline=deadline,
        )

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
        return await load_premium_glass(
            self,
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            surface,
            current_scope,
            include_closed_stores,
            deadline=deadline,
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
        return await load_monthly_history(
            self,
            month,
            months_back,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
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
        return await load_history_by_year(
            self,
            year,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
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
        return await load_performance_detail(
            self,
            month,
            level,
            key,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            deadline=deadline,
        )

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
        return await load_dashboard_all(
            self,
            month,
            firma,
            regional,
            asm,
            site_code,
            agent,
            current_scope,
            include_closed_stores,
            _history_projection=_history_projection,
            deadline=deadline,
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
