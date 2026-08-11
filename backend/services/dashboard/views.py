"""Canonical loaders for Dashboard summary, daily data and special cards."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from domain.filter_scope import FilterInput
from schemas.dashboard import (
    DashboardSpecialCardsResponse,
    DashboardSummary,
    DailySalesPoint,
)
from schemas.premium_glass import PremiumGlassAnalysis
from services.dashboard.ports import DashboardServicePort
from services.dashboard.specials_data import _get_special_cards_data
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, scoped_clauses
from services.premium_glass import build_premium_glass_card, get_premium_glass_analysis
from services.request_deadline import RequestDeadline


async def load_summary(
    service: DashboardServicePort,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
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

    row = await service.repo.fetch_summary(clauses, params, cartela_clauses, current_scope, pool=service._pool_for(deadline))
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

async def load_daily_sales(
    service: DashboardServicePort,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
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

    rows = await service.repo.fetch_daily_sales(clauses, params, current_scope, pool=service._pool_for(deadline))
    return [DailySalesPoint(**dict(row)) for row in rows]

async def load_special_cards(
    service: DashboardServicePort,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
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
        pool=service._pool_for(deadline),
    )
    async with service._pool_for(deadline).acquire() as conn:
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

async def load_premium_glass(
    service: DashboardServicePort,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    surface: Literal["all", "screen", "camera"] = "all",
    current_scope: bool = True,
    include_closed_stores: bool = False,
    *,
    deadline: RequestDeadline | None = None,
) -> PremiumGlassAnalysis:
    async with service._pool_for(deadline).acquire() as conn:
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
