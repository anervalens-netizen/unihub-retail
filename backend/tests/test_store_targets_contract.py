from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from models import StoreTargetInput, StoreTargetsSaveResponse
from routers.stores import save_targets


@pytest.mark.asyncio
async def test_store_targets_returns_documented_response_model() -> None:
    service = AsyncMock()
    service.save_targets.return_value = 2

    result = await save_targets(
        payload=[StoreTargetInput(site_code="SYNTHETIC-SITE", import_month="2026-08", target_value=100)],
        _claims=None,
        _rate_limit=None,
        svc=service,
    )

    assert result == StoreTargetsSaveResponse(inserted=2)
    service.save_targets.assert_awaited_once_with([
        {"site_code": "SYNTHETIC-SITE", "import_month": "2026-08", "target_value": 100},
    ])


def test_store_targets_openapi_uses_response_model() -> None:
    from main import app

    response = app.openapi()["paths"]["/api/stores/targets"]["post"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"]["$ref"].endswith("/StoreTargetsSaveResponse")
