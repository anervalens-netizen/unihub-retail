from __future__ import annotations

from typing import Any, cast

import pytest

from repositories.hr import HrRepository
from services.hr import HrService


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeHrRepository:
    async def get_manager_overview_rows(self, month: str) -> list[dict[str, Any]]:
        assert month == "2026-07"
        return [{
            "asm": "Mihai Condorateanu",
            "regional": "Mihai Condorateanu",
            "reporting_available": True,
            "active_stores": 2,
            "active_agents": 3,
            "previous_active_agents": 4,
            "agents_added": 1,
            "agents_left": 2,
            "stores_without_agents": 1,
        }]

    async def get_manager_store_overview_rows(self, month: str) -> list[dict[str, Any]]:
        assert month == "2026-07"
        return [
            {
                "asm": "Mihai Condorateanu",
                "site_code": "STORE1",
                "locatie": "Magazin 1",
                "firma": "Mobiup",
                "active_agents": 3,
                "previous_active_agents": 2,
            },
            {
                "asm": "Mihai Condorateanu",
                "site_code": "STORE2",
                "locatie": "Magazin 2",
                "firma": "MobiCell",
                "active_agents": 0,
                "previous_active_agents": 2,
            },
        ]

    async def get_visits_snapshot(self, month: str) -> list[dict[str, Any]]:
        assert month == "2026-07"
        return [{
            "asm": "Mihai Condorateanu",
            "distinct_stores": 1,
            "total_visits": 3,
            "avg_completion": 88.5,
            "checklist_score": 96.0,
            "approved_pct": 100.0,
        }]


@pytest.mark.anyio
async def test_manager_overview_combines_team_stores_and_visits() -> None:
    repo = cast(HrRepository, FakeHrRepository())
    result = await HrService(repo).get_manager_overview("2026-07")

    assert result == [{
        "manager": "Mihai Condorateanu",
        "regional": "Mihai Condorateanu",
        "month": "2026-07",
        "reporting_available": True,
        "active_stores": 2,
        "active_agents": 3,
        "previous_active_agents": 4,
        "agent_delta": -1,
        "agents_added": 1,
        "agents_left": 2,
        "stores_without_agents": 1,
        "agents_per_store": 1.5,
        "visits_available": True,
        "total_visits": 3,
        "visited_stores": 1,
        "visit_coverage_pct": 50.0,
        "avg_visit_completion": 88.5,
        "checklist_score": 96.0,
        "approved_pct": 100.0,
        "stores": [
            {
                "site_code": "STORE1",
                "locatie": "Magazin 1",
                "firma": "Mobiup",
                "active_agents": 3,
                "previous_active_agents": 2,
                "agent_delta": 1,
            },
            {
                "site_code": "STORE2",
                "locatie": "Magazin 2",
                "firma": "MobiCell",
                "active_agents": 0,
                "previous_active_agents": 2,
                "agent_delta": -2,
            },
        ],
    }]
