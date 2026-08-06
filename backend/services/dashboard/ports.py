"""Structural service boundary consumed by Dashboard operation modules."""

from __future__ import annotations

from typing import Any, Protocol

from repositories.dashboard import DashboardRepository
from services.request_deadline import RequestDeadline


class DashboardServicePort(Protocol):
    repo: DashboardRepository
    dashboard_global_component_concurrency: int

    def _pool_for(self, deadline: RequestDeadline | None) -> Any: ...

    async def get_summary(self, *args: Any, **kwargs: Any) -> Any: ...

    async def get_daily_sales(self, *args: Any, **kwargs: Any) -> Any: ...

    async def get_monthly_history(self, *args: Any, **kwargs: Any) -> Any: ...

    async def get_premium_glass(self, *args: Any, **kwargs: Any) -> Any: ...

