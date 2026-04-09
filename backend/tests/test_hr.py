from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_leave_request():
    from routers.hr import create_leave_request
    pool = await get_pool()
    async with pool.acquire() as conn:
        req = await create_leave_request(conn, {
            "agent_name": "Test Agent",
            "start_date": "2026-05-01",
            "end_date": "2026-05-05",
            "leave_type": "odihna",
            "notes": None,
        })
        assert req["agent_name"] == "Test Agent"
        assert req["status"] == "pending"
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_approve_leave_request():
    from routers.hr import create_leave_request, update_leave_status
    pool = await get_pool()
    async with pool.acquire() as conn:
        req = await create_leave_request(conn, {
            "agent_name": "Test Agent",
            "start_date": "2026-05-10",
            "end_date": "2026-05-12",
            "leave_type": "medical",
            "notes": None,
        })
        updated = await update_leave_status(conn, req["id"], "approved")
        assert updated["status"] == "approved"
        await conn.execute("DELETE FROM leave_requests WHERE id = $1", req["id"])


@pytest.mark.anyio
async def test_list_leave_requests():
    from routers.hr import list_leave_requests
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await list_leave_requests(conn, status=None, agent_name=None)
        assert isinstance(rows, list)


@pytest.mark.anyio
async def test_performance_returns_list():
    from routers.hr import get_agent_performance
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_agent_performance(conn, "NonexistentAgent")
        assert isinstance(result, list)


@pytest.mark.anyio
async def test_asm_performance_returns_list():
    from routers.hr import get_asm_performance
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_asm_performance(conn, "2026-03", regional=None)
        assert isinstance(result, list)
        if result:
            row = result[0]
            assert "asm" in row
            assert "total_sales" in row
            assert "total_visits" in row
            assert "target_pct" in row


@pytest.mark.anyio
async def test_asm_performance_history_returns_list():
    from routers.hr import get_asm_performance_history
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await get_asm_performance_history(conn, "Andreea Vladascau", months=6)
        assert isinstance(result, list)
