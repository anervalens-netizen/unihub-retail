from __future__ import annotations

import asyncio
from typing import Any
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from db.connection import get_pool
from routers.dashboard_filters import scoped_clauses
from routers.shared import normalize_filter


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def get_auth_token() -> str:
    """Get admin JWT token for testing."""
    from services.auth_service import create_access_token

    return create_access_token(user_id=1, username="admin", role="admin")


async def get_pool_connection():
    """Get a connection from the pool."""
    pool = await get_pool()
    conn = await pool.acquire()
    return conn, pool


@pytest.mark.anyio
async def test_summary_endpoint_structure():
    """Test that dashboard summary returns expected fields."""
    from services.dashboard_specials import load_special_cards_config, parse_promotion_definition

    config, _ = load_special_cards_config()
    promo_def, _ = parse_promotion_definition(config)

    # Verify config is loaded
    assert promo_def is not None
    assert "item_codes" in promo_def
    assert isinstance(promo_def["item_codes"], list)


@pytest.mark.anyio
async def test_special_cards_promotion_config():
    """Test that promotion card config has required fields."""
    from services.dashboard_specials import load_special_cards_config, parse_promotion_definition

    config, _ = load_special_cards_config()
    promo_def, promo_err = parse_promotion_definition(config)

    assert promo_err is None
    assert promo_def is not None
    assert promo_def["title"]
    assert promo_def["start_date"]
    assert promo_def["end_date"]


@pytest.mark.anyio
async def test_special_cards_incentive_config():
    """Test that incentive card config has required fields."""
    from services.dashboard_specials import (
        load_incentive_codes,
        load_special_cards_config,
        parse_incentive_definition,
    )

    config, _ = load_special_cards_config()
    incentive_def, incentive_err = parse_incentive_definition(config)

    assert incentive_err is None
    assert incentive_def is not None
    assert incentive_def["month"] == "2026-03"
    assert incentive_def["reward_per_unit"] == 5.0

    # Load codes
    codes, codes_err = load_incentive_codes(incentive_def)
    assert codes_err is None
    assert codes is not None
    assert len(codes) > 0


@pytest.mark.anyio
async def test_hub_specials_json_exists():
    """Test that hub_specials.json config file exists and is valid."""
    import os

    repo_path = Path(__file__).resolve().parents[2] / "data" / "hub_specials.json"
    config_path = os.environ.get("HUB_SPECIALS_PATH", str(repo_path))

    assert os.path.exists(config_path), f"hub_specials.json not found at {config_path}"

    import json

    with open(config_path) as f:
        config = json.load(f)

    assert "promotion" in config
    assert "incentive" in config


def test_dashboard_scoped_clauses_builds_agent_filter() -> None:
    clauses, scope_params = scoped_clauses(
        {"role": "admin", "id": 1},
        {"agent": 5, "site_code": 4},
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        include_cartela_filter=True,
        scope_base_alias="st",
    )

    assert "NOT st.is_cartela" in clauses
    assert "st.site_code = $4" in clauses
    assert "st.agent = $5" in clauses
    assert scope_params == []


def test_normalize_filter_accepts_clean_all_scope_values() -> None:
    assert normalize_filter("Toate") is None
    assert normalize_filter("Toti") is None
    assert normalize_filter(" Toate ") is None
    assert normalize_filter("Agent 007") == "Agent 007"


def test_dashboard_all_endpoint_returns_composite_payload() -> None:
    from main import app
    from services.auth_service import create_access_token

    token = create_access_token(user_id=1, username="admin", role="admin")
    with TestClient(app) as client:
        response = client.get(
            "/api/dashboard/all?month=2026-03",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "agents" in payload
    assert "special_cards" in payload
    assert "period_comparison" in payload
