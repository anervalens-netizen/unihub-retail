"""Batch projection boundaries for Dashboard history and all-data routes."""

from __future__ import annotations

import asyncio
from typing import Any

from schemas.dashboard import DashboardAllBatchResponse, DashboardAllQuery, DashboardAllResponse
from services.request_deadline import RequestDeadline
from services.dashboard.scheduler import _gather_cancel_on_error


async def load_dashboard_all_batch(
    service: Any,
    queries: list[DashboardAllQuery],
    *,
    deadline: RequestDeadline | None = None,
) -> DashboardAllBatchResponse:
    semaphore = asyncio.Semaphore(2)

    async def load(query: DashboardAllQuery) -> DashboardAllResponse:
        async with semaphore:
            return await service.get_dashboard_all(**query.model_dump(), deadline=deadline)

    results = await _gather_cancel_on_error(
        *(load(query) for query in queries),
        task_name="dashboard:all-batch",
    )
    return DashboardAllBatchResponse(results=results)


async def load_dashboard_history_details_batch(
    service: Any,
    queries: list[DashboardAllQuery],
    *,
    deadline: RequestDeadline | None = None,
) -> DashboardAllBatchResponse:
    """Load only the components consumed by the multi-month History UI."""
    semaphore = asyncio.Semaphore(2)

    async def load(query: DashboardAllQuery) -> DashboardAllResponse:
        async with semaphore:
            return await service.get_dashboard_all(
                **query.model_dump(),
                _history_projection=True,
                deadline=deadline,
            )

    results = await _gather_cancel_on_error(
        *(load(query) for query in queries),
        task_name="dashboard:all-batch",
    )
    return DashboardAllBatchResponse(results=results)
