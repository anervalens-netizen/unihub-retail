from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.connection import get_pool
from permissions import require_business_write_access
from repositories.tasks import TasksRepository
from services.tasks import TasksService

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _bounded_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _valid_date(value: str | None) -> str | None:
    if value is not None:
        date.fromisoformat(value)
    return value


class TaskItem(BaseModel):
    id: int
    title: str
    assignee: str | None = None
    site_code: str | None = None
    deadline: str | None = None
    status: str
    source: str
    source_meta: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    assignee: str | None = Field(default=None, max_length=120)
    site_code: str | None = Field(default=None, max_length=64)
    deadline: str | None = Field(default=None, max_length=10)
    status: str = Field(default="deschis", min_length=1, max_length=32)
    source: str = Field(default="manual", min_length=1, max_length=64)
    source_meta: dict | None = None

    @field_validator("title", "assignee", "site_code", "status", "source")
    @classmethod
    def normalize_text(cls, value: str | None, info) -> str | None:
        return _bounded_text(value, field_name=info.field_name)

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: str | None) -> str | None:
        return _valid_date(value)


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    assignee: str | None = Field(default=None, max_length=120)
    site_code: str | None = Field(default=None, max_length=64)
    deadline: str | None = Field(default=None, max_length=10)
    status: str | None = Field(default=None, max_length=32)

    @field_validator("title", "assignee", "site_code", "status")
    @classmethod
    def normalize_text(cls, value: str | None, info) -> str | None:
        return _bounded_text(value, field_name=info.field_name)

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: str | None) -> str | None:
        return _valid_date(value)


async def get_tasks_service() -> TasksService:
    pool = await get_pool()
    repo = TasksRepository(pool)
    return TasksService(repo)


@router.get("", response_model=TaskListResponse)
async def get_tasks(
    status: str | None = Query(None, min_length=1, max_length=32),
    assignee: str | None = Query(None, min_length=1, max_length=120),
    site_code: str | None = Query(None, min_length=1, max_length=64),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    svc: TasksService = Depends(get_tasks_service),
):
    return await svc.list_tasks(status, assignee, site_code, limit=limit, offset=offset)


@router.post("")
async def post_task(
    body: TaskCreate,
    svc: TasksService = Depends(get_tasks_service),
    _claims=Depends(require_business_write_access),
):
    return await svc.create_task(body.model_dump())


@router.patch("/{task_id}")
async def patch_task(
    task_id: int,
    body: TaskUpdate,
    svc: TasksService = Depends(get_tasks_service),
    _claims=Depends(require_business_write_access),
):
    return await svc.update_task(task_id, body.model_dump(exclude_none=True))


@router.delete("/{task_id}")
async def remove_task(
    task_id: int,
    svc: TasksService = Depends(get_tasks_service),
    _claims=Depends(require_business_write_access),
):
    await svc.delete_task(task_id)
    return {"ok": True}
