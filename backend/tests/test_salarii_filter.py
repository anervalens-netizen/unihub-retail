from __future__ import annotations
import pytest


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _get_token(client):
    import httpx
    try:
        login = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "9999"},
        )
    except httpx.ConnectError:
        pytest.skip("Backend not running")
    if login.status_code != 200:
        pytest.skip("Backend credentials wrong")
    return login.json()["access_token"]


@pytest.mark.anyio
async def test_salarii_overview_accepts_regional_asm():
    """GET /salarii/overview with regional+asm returns 200 with correct shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        # Baseline — no filter
        r1 = await client.get("/salarii/overview", headers=headers)
        assert r1.status_code == 200
        data = r1.json()
        for key in ("total", "by_company", "record_count", "agent_count", "months_span"):
            assert key in data, f"Missing key: {key}"

        # With regional + asm (may return 0-data, must not 500)
        r2 = await client.get(
            "/salarii/overview",
            params={"regional": "NonExistentRegion", "asm": "NonExistentAsm"},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        for key in ("total", "by_company", "record_count", "agent_count", "months_span"):
            assert key in data2, f"Missing key after filter: {key}"
        # Filtered total must be <= unfiltered total
        assert data2["total"] <= data["total"]


@pytest.mark.anyio
async def test_salarii_agents_summary_accepts_regional_asm():
    """GET /salarii/agents/summary with regional+asm returns 200 with items+total shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.get("/salarii/agents/summary", params={"limit": 1}, headers=headers)
        assert r1.status_code == 200
        assert "total" in r1.json()

        r2 = await client.get(
            "/salarii/agents/summary",
            params={"regional": "NonExistentRegion", "limit": 1},
            headers=headers,
        )
        assert r2.status_code == 200
        data2 = r2.json()
        assert "items" in data2 and "total" in data2
        assert data2["total"] <= r1.json()["total"]


@pytest.mark.anyio
async def test_salarii_summary_accepts_regional_asm():
    """GET /salarii/summary with regional+asm returns 200 with month+items shape."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/salarii/summary",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert "month" in data and "items" in data


@pytest.mark.anyio
async def test_salarii_trend_accepts_regional_asm():
    """GET /salarii/trend with regional+asm returns 200 (list response)."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/salarii/trend",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)


@pytest.mark.anyio
async def test_salarii_evolution_accepts_regional_asm():
    """GET /salarii/evolution with regional+asm returns 200 (list response)."""
    import httpx
    async with httpx.AsyncClient(base_url="http://localhost:9898") as client:
        token = await _get_token(client)
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.get(
            "/salarii/evolution",
            params={"regional": "NonExistentRegion"},
            headers=headers,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)
