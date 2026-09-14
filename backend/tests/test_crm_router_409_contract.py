"""Lot 47 P1-A router contract: POST /api/crm/scores/recalculate.

When the requested month has no source data, the CRM recalculation
service raises ``CrmSourceDataUnavailable``. The router maps that to
HTTP 409 Conflict with a typed ``CrmApiErrorResponse`` body. The
previous projection is preserved untouched.

This module exercises the real FastAPI ASGI router with a real
CrmService backed by the isolated test database, overriding only the
authentication / rate-limit dependencies so the test does not need a
live OIDC verifier.
"""

from __future__ import annotations

import os
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from auth import AuthClaims, require_auth
from composition import build_crm_service
from db.connection import get_pool
from permissions import require_business_write_access
from routers import crm as crm_router
from routers.crm import (
    CrmApiErrorResponse,
    CrmRecalculateResponse,
)
from services.crm import CrmService, CrmSourceDataUnavailable


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL through the immutable manifest",
)


# Synthetic months / sites are namespaced so they cannot collide with
# other suites. The chosen MONTH values are far in the future to avoid
# any historical scoring rows from real import runs.
MONTH_OK = "2098-06"
MONTH_NO_SOURCE = "2098-07"
SITE_OK = "CRM-L47-ROUTER-OK"


async def _cleanup_pool(connection: Any) -> None:
    await connection.execute(
        "DELETE FROM store_scores WHERE site_code = ANY($1::text[])",
        [SITE_OK],
    )
    await connection.execute(
        "DELETE FROM store_targets WHERE site_code = ANY($1::text[])",
        [SITE_OK],
    )
    await connection.execute(
        "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
        [SITE_OK],
    )
    await connection.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::text[])",
        [SITE_OK],
    )
    for month in (MONTH_OK, MONTH_NO_SOURCE):
        await connection.execute(
            "DELETE FROM store_scores WHERE score_month = $1", month,
        )


async def _seed_ok(connection: Any) -> None:
    await connection.execute(
        """
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm,
            first_seen_month, last_seen_month, is_active
        ) VALUES (
            $1, 'CRM L47 router fixture', 'Mobicell',
            'L47 Region', 'L47 ASM', $2, $2, TRUE
        )
        """,
        SITE_OK, MONTH_OK,
    )
    await connection.execute(
        """
        INSERT INTO store_targets (
            site_code, import_month, target_value, source_file
        ) VALUES ($1, $2, 1000.00, 'l47-router.xlsx')
        """,
        SITE_OK, MONTH_OK,
    )
    await connection.execute(
        """
        INSERT INTO reporting_agent_month (
            import_month, site_code, locatie, firma, regional, asm,
            agent, total_sales, working_days
        ) VALUES (
            $1, $2, 'CRM L47 router fixture', 'Mobicell',
            'L47 Region', 'L47 ASM', 'agent-crm-router', 500.00, 30
        )
        """,
        MONTH_OK, SITE_OK,
    )


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app with the CRM router mounted and
    auth / rate-limit dependencies overridden for the test."""
    app = FastAPI()
    app.include_router(crm_router.router)

    def _fake_claims() -> AuthClaims:
        return AuthClaims(
            sub="l47-router-test",
            email="router@test.local",
            preferred_username="l47-router",
            groups=["unihub-manager"],
            iss="l47-test",
            aud="l47-test",
            iat=0,
            exp=9_999_999_999,
            raw={},
        )

    # Both require_auth (used by rate_limit and the inner chain of
    # require_business_write_access) and require_business_write_access
    # itself must be overridden so the test does not depend on a live
    # OIDC verifier or a populated cookie store.
    app.dependency_overrides[require_auth] = _fake_claims
    app.dependency_overrides[require_business_write_access] = _fake_claims
    # Use the real composition-provided service so we get a real DB-backed
    # CrmService without going through the production DI container.
    app.dependency_overrides[build_crm_service] = build_crm_service

    return app


@pytest.fixture
async def l47_router_client():
    pool = await get_pool()
    async with pool.acquire() as connection:
        await _cleanup_pool(connection)
        await _seed_ok(connection)
    app = _build_app()
    transport = httpx.ASGITransport(app=app)
    # The focused dev container may not have fieldops_visits; the
    # CRM service tolerates an empty visit map (zero visits, zero
    # completion), so we patch the query unconditionally.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test",
        ) as client:
            yield client
    async with pool.acquire() as connection:
        await _cleanup_pool(connection)


@pytest.mark.anyio
async def test_recalculate_with_source_returns_200_and_typed_body(
    l47_router_client,
) -> None:
    """Happy path: with valid source data, the recalculation succeeds
    with HTTP 200 and the typed ``CrmRecalculateResponse``."""
    response = await l47_router_client.post(
        "/api/crm/scores/recalculate",
        params={"month": MONTH_OK},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # Typed body: exactly the documented ``CrmRecalculateResponse``.
    CrmRecalculateResponse.model_validate(body)
    assert body["month"] == MONTH_OK
    assert body["recalculated"] == 1


@pytest.mark.anyio
async def test_recalculate_no_source_returns_409_typed_body(
    l47_router_client,
) -> None:
    """P1-A router contract: empty source returns HTTP 409 with a
    typed ``CrmApiErrorResponse`` body. The previous projection is
    preserved.

    Setup: MONTH_NO_SOURCE has no source data and no prior
    projection. A recalculate request must return 409 and create no
    store_scores rows (no implicit zero scores).
    """
    pool = await get_pool()
    # Make sure MONTH_NO_SOURCE starts truly empty.
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_scores WHERE score_month = $1",
            MONTH_NO_SOURCE,
        )

    response = await l47_router_client.post(
        "/api/crm/scores/recalculate",
        params={"month": MONTH_NO_SOURCE},
    )
    assert response.status_code == 409, (
        f"P1-A: empty-source recalc must return HTTP 409, got "
        f"{response.status_code}: {response.text}"
    )
    body = response.json()
    # Typed body: exactly the documented ``CrmApiErrorResponse``.
    CrmApiErrorResponse.model_validate(body)
    assert "detail" in body
    assert isinstance(body["detail"], str) and body["detail"]

    # After the rejected recalc, no store_scores row exists for the month.
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT site_code FROM store_scores WHERE score_month = $1",
            MONTH_NO_SOURCE,
        )
        assert rows == [], (
            "P1-A: a rejected empty recalc must NOT create implicit zero "
            f"scores. Got {[(r['site_code']) for r in rows]!r}."
        )


@pytest.mark.anyio
async def test_recalculate_no_source_preserves_existing_projection(
    l47_router_client,
) -> None:
    """P1-A: when a previous projection exists for the month, an
    empty-source recalculation must preserve it exactly. The 409 body
    is still the typed ``CrmApiErrorResponse``."""
    pool = await get_pool()
    # Seed a successful projection for the no-source month via the
    # service path (so the lock-aware cycle is exercised).
    repo_factory = build_crm_service
    svc = await repo_factory()

    # Seed a different month with valid source; then we'll wipe its
    # source and attempt recalc on it.
    month_with_prior = "2098-08"
    site_with_prior = "CRM-L47-ROUTER-PRIOR"
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_scores WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM store_targets WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month, is_active
            ) VALUES (
                $1, 'CRM L47 prior', 'Mobicell',
                'L47 Region', 'L47 ASM', $2, $2, TRUE
            )
            """,
            site_with_prior, month_with_prior,
        )
        await connection.execute(
            """
            INSERT INTO store_targets (
                site_code, import_month, target_value, source_file
            ) VALUES ($1, $2, 1000.00, 'l47-prior.xlsx')
            """,
            site_with_prior, month_with_prior,
        )
        await connection.execute(
            """
            INSERT INTO reporting_agent_month (
                import_month, site_code, locatie, firma, regional, asm,
                agent, total_sales, working_days
            ) VALUES (
                $1, $2, 'CRM L47 prior', 'Mobicell',
                'L47 Region', 'L47 ASM', 'agent-crm-prior', 500.00, 30
            )
            """,
            month_with_prior, site_with_prior,
        )

    # First recalc succeeds; persisted projection exists.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        first_count = await svc.recalculate_scores(month_with_prior)
    assert first_count == 1

    # Wipe source for the month.
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            site_with_prior,
        )

    # Recalc must return 409 and preserve the prior projection.
    response = await l47_router_client.post(
        "/api/crm/scores/recalculate",
        params={"month": month_with_prior},
    )
    assert response.status_code == 409, response.text
    body = response.json()
    CrmApiErrorResponse.model_validate(body)

    async with pool.acquire() as connection:
        persisted = await connection.fetch(
            "SELECT site_code, score FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            month_with_prior,
        )
    persisted_sites = {row["site_code"]: row["score"] for row in persisted}
    assert persisted_sites == {site_with_prior: 45}, (
        f"P1-A: prior projection must be preserved exactly. Got "
        f"{persisted_sites!r}."
    )

    # Cleanup
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_scores WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM store_targets WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            site_with_prior,
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code = $1",
            site_with_prior,
        )
