from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from services.premium_glass import get_premium_glass_analysis


class FakeConn:
    def __init__(self, rows: list[dict[str, Any]], target_model_count: int) -> None:
        self.rows = rows
        self.target_model_count = target_model_count

    async def fetch(self, *_args: Any) -> list[dict[str, Any]]:
        return self.rows

    async def fetchval(self, *_args: Any) -> int:
        return self.target_model_count


@pytest.mark.asyncio
async def test_premium_glass_deduplicates_multi_model_lines_for_non_model_stats() -> None:
    rows = [
        {
            "id": 1,
            "item_code": "P1",
            "item_name": "Premium A",
            "site_code": "S1",
            "locatie": "Store 1",
            "firma": "MobiUp",
            "manager": "Manager 1",
            "agent": "Agent 1",
            "is_premium": True,
            "model_key": "iphone-pro",
            "model_label": "iPhone Pro",
            "qty": 2,
            "sales": Decimal("20"),
        },
        {
            "id": 1,
            "item_code": "P1",
            "item_name": "Premium A",
            "site_code": "S1",
            "locatie": "Store 1",
            "firma": "MobiUp",
            "manager": "Manager 1",
            "agent": "Agent 1",
            "is_premium": True,
            "model_key": "iphone-pro-max",
            "model_label": "iPhone Pro Max",
            "qty": 2,
            "sales": Decimal("20"),
        },
        {
            "id": 2,
            "item_code": "R1",
            "item_name": "Regular A",
            "site_code": "S1",
            "locatie": "Store 1",
            "firma": "MobiUp",
            "manager": "Manager 1",
            "agent": "Agent 2",
            "is_premium": False,
            "model_key": "iphone-pro",
            "model_label": "iPhone Pro",
            "qty": 3,
            "sales": Decimal("15"),
        },
        {
            "id": 3,
            "item_code": "P2",
            "item_name": "Premium B",
            "site_code": "S2",
            "locatie": "Store 2",
            "firma": "MobiUp",
            "manager": "Manager 2",
            "agent": "Agent 3",
            "is_premium": True,
            "model_key": "iphone-pro-max",
            "model_label": "iPhone Pro Max",
            "qty": 1,
            "sales": Decimal("12"),
        },
    ]

    analysis = await get_premium_glass_analysis(
        FakeConn(rows, target_model_count=2),
        "2026-06",
        None,
        None,
        None,
        None,
        None,
    )

    assert analysis.summary.total_qty == 6
    assert analysis.summary.premium_qty == 3
    assert analysis.summary.regular_qty == 3
    assert analysis.summary.active_stores == 2
    assert analysis.summary.active_agents == 3

    models = {row.model_label: row for row in analysis.models}
    assert models["iPhone Pro"].total_qty == 5
    assert models["iPhone Pro"].regular_qty == 3
    assert models["iPhone Pro Max"].total_qty == 3
    assert models["iPhone Pro Max"].regular_qty == 0

    products = {row.item_code: row for row in analysis.products}
    assert products["P1"].qty == 2
    assert products["P1"].model_labels == ["iPhone Pro", "iPhone Pro Max"]
