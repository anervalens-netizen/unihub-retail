from __future__ import annotations
import pytest


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


def test_stores_coverage_response_shape():
    """StoreCoverageItem and StoreCoverageResponse include has_changes and modified_stores_count."""
    from models import StoreCoverageItem, StoreCoverageResponse

    item = StoreCoverageItem(
        site_code="TEST",
        locatie="Test Store",
        firma="TestFirma",
        regional="TestRegion",
        asm="TestAsm",
        status="covered",
        agent_count=2,
        has_changes=True,
    )
    assert item.has_changes is True

    response = StoreCoverageResponse(
        active_stores_count=10,
        uncovered_stores_count=2,
        closed_stores_count=3,
        modified_stores_count=4,
        items=[item],
    )
    assert response.modified_stores_count == 4
    assert response.items[0].has_changes is True


@pytest.mark.anyio
async def test_stores_coverage_endpoint_returns_has_changes():
    """The /stores-coverage endpoint returns has_changes on each item and modified_stores_count in root."""
    import httpx

    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        try:
            login = await client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "9999"},
            )
        except httpx.ConnectError:
            pytest.skip("Backend not running")
        if login.status_code != 200:
            pytest.skip("Backend credentials wrong")
        token = login.json()["access_token"]

        resp = await client.get(
            "/api/agents/stores-coverage",
            params={"selected_month": "2025-04"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "modified_stores_count" in data
        assert isinstance(data["modified_stores_count"], int)
        assert "items" in data
        if data["items"]:
            first = data["items"][0]
            assert "has_changes" in first
            assert isinstance(first["has_changes"], bool)
