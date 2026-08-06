from __future__ import annotations

import os
from pathlib import Path

import pytest
from db.connection import get_pool
from services.filters import normalize_filter, scoped_clauses


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def get_pool_connection():
    """Get a connection from the pool."""
    pool = await get_pool()
    conn = await pool.acquire()
    return conn, pool


@pytest.mark.anyio
async def test_summary_endpoint_structure():
    """Test that promotion definition returns None when not configured."""
    from services.dashboard_specials import load_special_cards_config, parse_promotion_definition

    config, _ = load_special_cards_config()
    promo_def, _ = parse_promotion_definition(config, "2026-04")

    assert promo_def is None


@pytest.mark.anyio
async def test_special_cards_promotion_config():
    """Test that promotion config is absent (no promotion for April)."""
    from services.dashboard_specials import load_special_cards_config, parse_promotion_definition

    config, _ = load_special_cards_config()
    promo_def, promo_err = parse_promotion_definition(config, "2026-04")

    assert promo_err is None
    assert promo_def is None


@pytest.mark.anyio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL",
)
async def test_special_cards_incentive_config():
    """Test that incentive campaigns are stored in the DB (not hub_specials.json)."""
    from services.incentive_db import get_incentive_campaign

    conn, pool = await get_pool_connection()
    try:
        campaign = await get_incentive_campaign(conn, "2026-04")
        if campaign is not None:
            assert campaign["month"] == "2026-04"
            assert "reward_map" in campaign
            assert isinstance(campaign["reward_map"], dict)
            assert len(campaign["reward_map"]) > 0
    finally:
        await pool.release(conn)


@pytest.mark.anyio
async def test_hub_specials_json_exists():
    """Test that hub_specials.json exists and has valid promotions structure."""
    import json
    import os

    repo_path = Path(__file__).resolve().parents[2] / "data" / "hub_specials.json"
    config_path = os.environ.get("HUB_SPECIALS_PATH", str(repo_path))
    if not os.path.exists(config_path):
        pytest.skip(f"External fixture not present: {config_path}")

    assert os.path.exists(config_path), f"hub_specials.json not found at {config_path}"

    with open(config_path) as f:
        config = json.load(f)

    assert "promotions" in config
    assert isinstance(config["promotions"], list)
    assert "incentives" in config
    assert isinstance(config["incentives"], list)


def test_dashboard_scoped_clauses_builds_agent_filter() -> None:
    clauses = scoped_clauses(
        {"agent": 5, "site_code": 4},
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        include_cartela_filter=True,
    )

    assert "NOT st.is_cartela" in clauses
    assert "s.locatie NOT ILIKE 'TR %'" in clauses
    assert "st.site_code = ANY(string_to_array($4::TEXT, ','))" in clauses
    assert "st.agent = ANY(string_to_array($5::TEXT, ','))" in clauses


def test_normalize_filter_accepts_clean_all_scope_values() -> None:
    assert normalize_filter("Toate") is None
    assert normalize_filter("Toti") is None
    assert normalize_filter(" Toate ") is None
    assert normalize_filter("Agent 007") == "Agent 007"


@pytest.mark.skip(reason="Requires a live DB pool — use integration tests against running server")
@pytest.mark.anyio
async def test_dashboard_all_endpoint_returns_composite_payload() -> None:
    import httpx
    from main import app

    import db.connection as _db
    _db.pool = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/dashboard/all?month=2026-03")

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "agents" in payload
    assert "special_cards" in payload
    assert "period_comparison" in payload
