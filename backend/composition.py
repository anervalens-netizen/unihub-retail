"""Application composition root.

Only this module wires concrete repositories/adapters into application
services. HTTP routers depend on these factories or on already-constructed
service instances; they never construct persistence adapters themselves.
"""
from __future__ import annotations

from typing import Any

from db.connection import get_pool
from repositories.agents import AgentsRepository
from repositories.ai_forecast import AiForecastRepository
from repositories.campaigns import CampaignsRepository
from repositories.contests import ContestsRepository
from repositories.crm import CrmRepository
from repositories.dashboard import DashboardRepository
from repositories.erp_reconciliation import ErpReconciliationRepository
from repositories.exports import ExportsRepository
from repositories.filters import FiltersRepository
from repositories.hr import HrRepository
from repositories.imports import ImportsRepository
from repositories.salarii import SalariiRepository
from repositories.store_pnl import StorePnlRepository
from repositories.stores import StoresRepository
from repositories.target_calculator import TargetCalculatorRepository
from repositories.tasks import TasksRepository
from repositories.visits_report_postgres import VisitsReportPostgresRepository
from services.agents import AgentsService
from services.ai_forecast import AiForecastService
from services.campaigns import CampaignsService
from services.contests import ContestsService
from services.crm import CrmService
from services.dashboard_service import DashboardService
from services.erp_reconciliation import ErpReconciliationService
from services.export_operations import ExportOperationsService
from services.exports import ExportsService
from services.filter_options import FilterOptionsService
from services.grile_queries import GrileQueryService
from services.hr import HrService
from services.imports import ImportsService
from services.salarii import SalariiService
from services.store_pnl import StorePnlService
from services.stores import StoresService
from services.target_calculator import TargetCalculatorService
from services.tasks import TasksService
from services.visits_report import VisitsReportService


async def build_agents_service() -> AgentsService:
    pool = await get_pool()
    return AgentsService(AgentsRepository(pool))


async def build_ai_forecast_service() -> AiForecastService:
    pool = await get_pool()
    return AiForecastService(AiForecastRepository(pool))


async def build_campaigns_service() -> CampaignsService:
    pool = await get_pool()
    return CampaignsService(CampaignsRepository(pool), pool)


async def build_contests_service() -> ContestsService:
    pool = await get_pool()
    return ContestsService(ContestsRepository(pool), pool)


async def build_crm_service() -> CrmService:
    pool = await get_pool()
    return CrmService(CrmRepository(pool), pool)


async def build_dashboard_service(runtime_config: Any) -> DashboardService:
    pool = await get_pool()
    return DashboardService(DashboardRepository(pool), pool, runtime_config)


async def build_exports_service() -> ExportsService:
    pool = await get_pool()
    return ExportsService(ExportsRepository(pool))


async def build_export_operations_service() -> ExportOperationsService:
    return ExportOperationsService(await get_pool())


async def build_filters_service() -> FilterOptionsService:
    pool = await get_pool()
    return FilterOptionsService(FiltersRepository(pool))


async def build_grile_query_service(*, pool: Any | None = None) -> GrileQueryService:
    return GrileQueryService(pool if pool is not None else await get_pool())


async def build_hr_service() -> HrService:
    pool = await get_pool()
    return HrService(HrRepository(pool))


async def build_imports_service() -> ImportsService:
    pool = await get_pool()
    return ImportsService(ImportsRepository(pool), pool)


async def build_erp_reconciliation_service() -> ErpReconciliationService:
    pool = await get_pool()
    return ErpReconciliationService(ErpReconciliationRepository(pool), pool)


async def build_salarii_service(
    *,
    person_id_key: str | None = None,
    pool: Any | None = None,
) -> SalariiService:
    resolved_pool = pool if pool is not None else await get_pool()
    return SalariiService(SalariiRepository(resolved_pool), person_id_key)


async def build_store_pnl_service() -> StorePnlService:
    pool = await get_pool()
    return StorePnlService(StorePnlRepository(pool))


async def build_stores_service() -> StoresService:
    pool = await get_pool()
    return StoresService(StoresRepository(pool), pool)


async def build_target_calculator_service() -> TargetCalculatorService:
    pool = await get_pool()
    return TargetCalculatorService(TargetCalculatorRepository(pool))


async def build_tasks_service() -> TasksService:
    pool = await get_pool()
    return TasksService(TasksRepository(pool))


async def build_visits_service() -> VisitsReportService:
    return VisitsReportService(VisitsReportPostgresRepository())
