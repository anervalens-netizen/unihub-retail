from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import worker
from repositories.hr import HrRepository
from repositories.tasks import TasksRepository
from routers.hr import LeaveRequestCreate
from services.tasks import TasksService
from routers.tasks import TaskCreate, TaskUpdate


class _Acquire:
    def __init__(self, connection: AsyncMock) -> None:
        self.connection = connection

    async def __aenter__(self) -> AsyncMock:
        return self.connection

    async def __aexit__(self, *args: object) -> None:
        return None


@pytest.mark.asyncio
async def test_tasks_repository_uses_bounded_stable_pagination() -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = 12
    connection.fetch.return_value = [{"id": 7}]
    pool = MagicMock()
    pool.acquire.return_value = _Acquire(connection)

    rows, total = await TasksRepository(pool).list_tasks(
        status="deschis",
        assignee="Ana",
        site_code="S1",
        limit=3,
        offset=6,
    )

    assert rows == [{"id": 7}]
    assert total == 12
    count_sql, count_status, count_assignee, count_site = connection.fetchval.await_args.args
    assert "SELECT COUNT(*) FROM tasks" in count_sql
    assert (count_status, count_assignee, count_site) == ("deschis", "%Ana%", "S1")
    sql, status, assignee, site_code, limit, offset = connection.fetch.await_args.args
    assert "ORDER BY" in sql and "id ASC" in sql
    assert "LIMIT $4 OFFSET $5" in sql
    assert (status, assignee, site_code, limit, offset) == ("deschis", "%Ana%", "S1", 3, 6)


@pytest.mark.asyncio
async def test_task_repository_emits_only_supplied_patch_columns_including_null() -> None:
    connection = AsyncMock()
    connection.fetchrow.return_value = {"id": 7, "assignee": None}
    pool = MagicMock()
    pool.acquire.return_value = _Acquire(connection)

    await TasksRepository(pool).update_task(7, {"assignee": None})

    sql, assignee, task_id = connection.fetchrow.await_args.args
    assert "assignee = $1" in sql
    assert "site_code =" not in sql and "deadline =" not in sql and "status =" not in sql
    assert (assignee, task_id) == (None, 7)


@pytest.mark.asyncio
async def test_hr_repository_uses_bounded_stable_pagination() -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = 9
    connection.fetch.return_value = []
    pool = MagicMock()
    pool.acquire.return_value = _Acquire(connection)

    rows, total = await HrRepository(pool).list_leave_requests(
        status="pending",
        agent_name="Ana",
        limit=4,
        offset=8,
    )

    assert rows == []
    assert total == 9
    count_sql, count_status, count_agent = connection.fetchval.await_args.args
    assert "SELECT COUNT(*) FROM leave_requests" in count_sql
    assert (count_status, count_agent) == ("pending", "%Ana%")
    sql, status, agent_name, limit, offset = connection.fetch.await_args.args
    assert "ORDER BY created_at DESC, id DESC" in sql
    assert "LIMIT $3 OFFSET $4" in sql
    assert (status, agent_name, limit, offset) == ("pending", "%Ana%", 4, 8)


@pytest.mark.asyncio
async def test_task_service_rejects_null_for_non_nullable_fields() -> None:
    repo = MagicMock()
    with pytest.raises(HTTPException) as caught:
        await TasksService(repo).update_task(7, {"status": None})

    assert caught.value.status_code == 400
    repo.update_task.assert_not_called()


def test_task_patch_preserves_omitted_vs_explicit_null_fields() -> None:
    omitted = TaskUpdate.model_validate({}).model_dump(exclude_unset=True)
    explicit_null = TaskUpdate.model_validate({"assignee": None, "site_code": None, "deadline": None}).model_dump(exclude_unset=True)

    assert omitted == {}
    assert explicit_null == {"assignee": None, "site_code": None, "deadline": None}


def test_listing_inputs_are_typed_and_bounded() -> None:
    assert TaskCreate(title="  Follow up  ", deadline="2026-08-05").title == "Follow up"
    assert LeaveRequestCreate.model_validate({
        "agent_name": " Ana ",
        "start_date": "2026-08-05",
        "end_date": "2026-08-06",
        "leave_type": " odihna ",
    }).agent_name == "Ana"

    with pytest.raises(ValidationError):
        TaskCreate(title="x" * 201)
    with pytest.raises(ValidationError):
        TaskCreate(title="x", deadline="2026-99-99")
    with pytest.raises(ValidationError):
        LeaveRequestCreate.model_validate({
            "agent_name": "Ana",
            "start_date": "2026-08-05",
            "end_date": "not-a-date",
            "leave_type": "odihna",
        })


@pytest.mark.asyncio
async def test_workers_reject_legacy_payloads() -> None:
    with pytest.raises(ValueError, match="durable spool"):
        await worker.import_sales_background(
            {}, b"legacy-bytes", "legacy.xlsx", 12, "legacy.xlsx"  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="persisted"):
        await worker.grile_monthly_background({}, 0)
    with pytest.raises(ValueError, match="persisted"):
        await worker.grile_monthly_background({}, "51")  # type: ignore[arg-type]
