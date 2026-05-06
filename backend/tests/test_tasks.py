from __future__ import annotations
import pytest
from db.connection import get_pool
from repositories.tasks import TasksRepository
from services.tasks import TasksService


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_and_list_task():
    pool = await get_pool()
    repo = TasksRepository(pool)
    svc = TasksService(repo)
    task = await svc.create_task({
        "title": "Test task",
        "assignee": "Test Agent",
    })
    assert task["title"] == "Test task"
    assert task["status"] == "deschis"

    # Cleanup in case something else was left
    import asyncio
    await asyncio.sleep(0)  # yield control
    
    # Make sure we can list tasks
    tasks = await svc.list_tasks(status=None, assignee=None, site_code=None)
    assert isinstance(tasks, list)

    # Clean up
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM tasks WHERE id = $1", task["id"])


@pytest.mark.anyio
async def test_update_task_status():
    pool = await get_pool()
    repo = TasksRepository(pool)
    svc = TasksService(repo)
    task = await svc.create_task({
        "title": "Update test",
        "assignee": "Test Agent",
    })
    updated = await svc.update_task(task["id"], {"status": "in_lucru"})
    assert updated["status"] == "in_lucru"

    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM tasks WHERE id = $1", task["id"])


@pytest.mark.anyio
async def test_delete_task():
    pool = await get_pool()
    repo = TasksRepository(pool)
    svc = TasksService(repo)
    task = await svc.create_task({
        "title": "Delete test",
        "assignee": "Test Agent",
    })
    deleted = await svc.delete_task(task["id"])
    assert deleted is True
