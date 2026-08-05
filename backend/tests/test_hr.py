from __future__ import annotations
import pytest
from db.connection import get_pool
from repositories.hr import HrRepository
from services.hr import HrService


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_leave_request():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    req = await svc.create_leave_request({
        "agent_name": "Test Agent",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
        "leave_type": "odihna",
        "notes": None,
    })
    assert req["agent_name"] == "Test Agent"
    assert req["status"] == "pending"
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_approve_leave_request():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    req = await svc.create_leave_request({
        "agent_name": "Test Agent",
        "start_date": "2026-05-10",
        "end_date": "2026-05-12",
        "leave_type": "medical",
        "notes": None,
    })
    updated = await svc.update_leave_status(req["id"], "approved")
    assert updated["status"] == "approved"
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_list_leave_requests():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    page = await svc.list_leave_requests(status=None, agent_name=None, limit=10, offset=0)
    assert page["limit"] == 10
    assert page["offset"] == 0
    assert isinstance(page["items"], list)
    if page["items"]:
        row = page["items"][0]
        assert "agent_name" in row
        assert "status" in row
        assert "start_date" in row
        assert "leave_type" in row


@pytest.mark.anyio
async def test_performance_returns_list():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    result = await svc.get_agent_performance("NonexistentAgent")
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_asm_performance_returns_list():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    result = await svc.get_asm_performance("2026-03", regional=None)
    assert isinstance(result, list)
    if result:
        row = result[0]
        assert "asm" in row
        assert "total_sales" in row
        assert "total_visits" in row
        assert "target_pct" in row


@pytest.mark.anyio
async def test_manager_overview_returns_team_and_portfolio_data():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    result = await svc.get_manager_overview("2026-07")
    assert isinstance(result, list)
    if result:
        row = result[0]
        assert "manager" in row
        assert "active_stores" in row
        assert "active_agents" in row
        assert "agents_added" in row
        assert "agents_left" in row
        assert "stores_without_agents" in row
        assert "visit_coverage_pct" in row
        assert isinstance(row["stores"], list)
        if row["stores"]:
            store = row["stores"][0]
            assert "site_code" in store
            assert "active_agents" in store
            assert "previous_active_agents" in store
            assert store["agent_delta"] == store["active_agents"] - store["previous_active_agents"]


@pytest.mark.anyio
async def test_asm_performance_history_returns_list():
    pool = await get_pool()
    repo = HrRepository(pool)
    svc = HrService(repo)
    perf = await svc.get_asm_performance("2026-03", regional=None)
    asm_name = perf[0]["asm"] if perf else "NonexistentASM"
    result = await svc.get_asm_performance_history(asm_name, months=6)
    assert isinstance(result, list)
    if result:
        row = result[0]
        assert "month" in row
        assert "total_sales" in row
        assert "total_target" in row
