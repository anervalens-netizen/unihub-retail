"""Tests for incentive_db, filters, and other utility services."""
from __future__ import annotations
import pytest


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_incentive_db_list_campaigns():
    from services.incentive_db import list_incentive_campaigns
    from db.connection import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        campaigns = await list_incentive_campaigns(conn)
        assert isinstance(campaigns, list)


@pytest.mark.anyio
async def test_hr_agent_performance():
    from services.hr import HrService
    from repositories.hr import HrRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    result = await svc.get_agent_performance("Test Agent")
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_hr_asm_performance():
    from services.hr import HrService
    from repositories.hr import HrRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    result = await svc.get_asm_performance("2026-03", None)
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_salarii_service_overview():
    from services.salarii import SalariiService
    from repositories.salarii import SalariiRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = SalariiRepository(pool)
    svc = SalariiService(repo)
    result = await svc.get_overview(None, None, None, None)
    assert isinstance(result, dict)
    assert "total" in result


@pytest.mark.anyio
async def test_salarii_service_summary():
    from services.salarii import SalariiService
    from repositories.salarii import SalariiRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = SalariiRepository(pool)
    svc = SalariiService(repo)
    result = await svc.get_summary(None, None, None, None, None, None)
    assert isinstance(result, dict)


@pytest.mark.anyio
async def test_stores_get_active():
    from services.stores import StoresService
    from repositories.stores import StoresRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = StoresRepository(pool)
    svc = StoresService(repo, pool)
    stores = await svc.get_active_stores()
    assert isinstance(stores, list)


@pytest.mark.anyio
async def test_crm_service_scores(monkeypatch: pytest.MonkeyPatch):
    from services.crm import CrmService
    from repositories.crm import CrmRepository
    from db.connection import get_pool

    monkeypatch.setattr("services.crm.get_visits_read_source", lambda: "sqlite")
    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    scores = await svc.calculate_scores_for_month("2026-03")
    assert isinstance(scores, list)


@pytest.mark.anyio
async def test_crm_service_alerts():
    from services.crm import CrmService
    from repositories.crm import CrmRepository
    from db.connection import get_pool

    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    alerts = await svc.get_alerts("2026-03")
    assert isinstance(alerts, list)
