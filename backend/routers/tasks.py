from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from db.connection import get_pool
from repositories.tasks import TasksRepository
from services.tasks import TasksService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str = "deschis"
    source: str = "manual"
    source_meta: dict | None = None


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str | None = None


async def get_tasks_service() -> TasksService:
    pool = await get_pool()
    repo = TasksRepository(pool)
    return TasksService(repo)


@router.get("")
async def get_tasks(
    status: str | None = Query(None),
    assignee: str | None = Query(None),
    site_code: str | None = Query(None),
    svc: TasksService = Depends(get_tasks_service),
):
    return await svc.list_tasks(status, assignee, site_code)


@router.post("")
async def post_task(
    body: TaskCreate,
    svc: TasksService = Depends(get_tasks_service),
):
    return await svc.create_task(body.model_dump())


@router.patch("/{task_id}")
async def patch_task(
    task_id: int, 
    body: TaskUpdate,
    svc: TasksService = Depends(get_tasks_service),
):
    return await svc.update_task(task_id, body.model_dump(exclude_none=True))


@router.delete("/{task_id}")
async def remove_task(
    task_id: int,
    svc: TasksService = Depends(get_tasks_service),
):
    await svc.delete_task(task_id)
    return {"ok": True}
