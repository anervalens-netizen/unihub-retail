from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_and_list_task():
    from routers.tasks import create_task, list_tasks
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Creează task
        task = await create_task(conn, {
            "title": "Test task",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        assert task["title"] == "Test task"
        assert task["status"] == "deschis"
        task_id = task["id"]

        # Listare
        tasks = await list_tasks(conn, status=None, assignee=None, site_code=None)
        ids = [t["id"] for t in tasks]
        assert task_id in ids

        # Cleanup
        await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)


@pytest.mark.anyio
async def test_update_task_status():
    from routers.tasks import create_task, update_task
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await create_task(conn, {
            "title": "Update test",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        updated = await update_task(conn, task["id"], {"status": "inchis"})
        assert updated["status"] == "inchis"
        await conn.execute("DELETE FROM tasks WHERE id = $1", task["id"])


@pytest.mark.anyio
async def test_delete_task():
    from routers.tasks import create_task, delete_task
    pool = await get_pool()
    async with pool.acquire() as conn:
        task = await create_task(conn, {
            "title": "Delete test",
            "assignee": None,
            "site_code": None,
            "deadline": None,
            "status": "deschis",
            "source": "manual",
            "source_meta": None,
        })
        result = await delete_task(conn, task["id"])
        assert result is True
