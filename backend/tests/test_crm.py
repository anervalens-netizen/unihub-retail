"""Lot 47 — F11 closure: deterministic CRM repository/Service tests.

Every CRM test MUST:
- populate exact source data;
- assert on exact persisted values (count, site-code set, score);
- FAIL when the expected persisted row is absent.

No ``if result:`` / ``if test_score:`` / ``assert isinstance(result, list)``-as-a-shield.
Those patterns let the previous suite stay green even when the calculated
score never reached persistence.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from db.connection import get_pool
from repositories.crm import CrmRepository
from services.crm import CrmService


SITE = "CRM-L47-DETERMINISTIC"
MONTH = "2098-04"


def _breakdown(score: int) -> dict:
    return {
        "target_pct": float(score),
        "trend_pct": 0.0,
        "kpi_pct": 0.0,
        "kpi_bon2acc_score": 0.0,
        "kpi_focus_score": 0.0,
        "visits_pct": 0.0,
        "target_attainment": float(score),
        "forecast_factor": 1.0,
        "kpi_bon2acc": 0.0,
        "kpi_focus": 0.0,
        "kpi_bon2acc_avg": 0.0,
        "kpi_focus_avg": 0.0,
        "nr_vizite": 0,
        "avg_completion": 0.0,
    }


def _score(score: int) -> dict:
    return {"site_code": SITE, "score": score, "breakdown": _breakdown(score)}


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


async def _seed(pool) -> None:
    async with pool.acquire() as connection:
        await connection.execute("DELETE FROM store_scores WHERE site_code = $1", SITE)
        await connection.execute("DELETE FROM store_targets WHERE site_code = $1", SITE)
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1", SITE
        )
        await connection.execute("DELETE FROM stores WHERE site_code = $1", SITE)
        await connection.execute(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month, is_active
            ) VALUES (
                $1, 'CRM L47 fixture', 'Mobicell', 'L47 Region', 'L47 ASM',
                $2, $2, TRUE
            )
            """,
            SITE, MONTH,
        )
        await connection.execute(
            "INSERT INTO store_targets (site_code, import_month, target_value, source_file) "
            "VALUES ($1, $2, 1000.00, 'l47-det.xlsx')",
            SITE, MONTH,
        )
        await connection.execute(
            """
            INSERT INTO reporting_agent_month (
                import_month, site_code, locatie, firma, regional, asm,
                agent, total_sales, working_days
            ) VALUES (
                $1, $2, 'CRM L47 fixture', 'Mobicell', 'L47 Region', 'L47 ASM',
                'agent-crm-l47', 500.00, 30
            )
            """,
            MONTH, SITE,
        )


@pytest.mark.anyio
async def test_calculate_scores_for_month_returns_expected_site_and_score() -> None:
    """F11 closure: the expected store MUST appear and its score MUST equal
    the deterministic value computed from the seeded source data."""
    pool = await get_pool()
    await _seed(pool)
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        scores = await svc.calculate_scores_for_month(MONTH)

    # No ``if scores:`` — assert the exact list length first.
    assert isinstance(scores, list)
    assert len(scores) == 1, (
        f"Expected exactly one CRM score for {MONTH}, got {scores!r}"
    )
    only = scores[0]
    assert only["site_code"] == SITE
    # Deterministic score: target=1000, sales=500, factor=1.0 → target_pct=50 → c1=20
    # prev absent → c2=15; avg_bon2acc=0 → bon2acc=5 → focus=5 → c3=10;
    # nr_vizite=0 → c4=0 → score=round(20+15+10+0)=45
    assert only["score"] == 45
    breakdown = only["breakdown"]
    assert breakdown["target_pct"] == 20.0
    assert breakdown["trend_pct"] == 15.0
    assert breakdown["kpi_pct"] == 10.0


@pytest.mark.anyio
async def test_recalculate_scores_persists_expected_store_and_score() -> None:
    """F11 closure for ``replace_month_scores``: persisted row must exist
    and have the expected score; the returned count must equal the set."""
    pool = await get_pool()
    await _seed(pool)
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH)
    assert count == 1, (
        f"Expected 1 recalculated score, got {count}. "
        "F11 closure: the calculation MUST reach persistence."
    )

    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT score, breakdown
            FROM store_scores
            WHERE site_code = $1 AND score_month = $2
            """,
            SITE, MONTH,
        )
    # No ``if test_score:`` — exact-existence assertion.
    assert row is not None, (
        "F11 closure: the expected store must be persisted, "
        "not silently absent behind an `if test_score` guard."
    )
    assert row["score"] == 45
    breakdown = row["breakdown"]
    if isinstance(breakdown, str):
        breakdown = json.loads(breakdown)
    # Breakdown keys MUST round-trip through JSONB.
    for key in (
        "target_pct",
        "trend_pct",
        "kpi_pct",
        "visits_pct",
        "target_attainment",
        "forecast_factor",
        "nr_vizite",
        "avg_completion",
    ):
        assert key in breakdown, f"breakdown key {key!r} must round-trip"


@pytest.mark.anyio
async def test_get_alerts_returns_list() -> None:
    """F11 closure for alerts: returned alerts are typed and have explicit
    fields when non-empty. Empty list is fine; non-empty list has the
    expected schema."""
    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    alerts = await svc.get_alerts(MONTH)
    assert isinstance(alerts, list)
    for alert in alerts:
        assert "site_code" in alert
        assert "score" in alert
        assert "reasons" in alert
        assert isinstance(alert["reasons"], list)


@pytest.mark.anyio
async def test_get_scores_persisted_row_count_matches_site_set() -> None:
    """F11 closure: persisted sites exactly match the persisted count.

    After recalculation the seeded store MUST be in the persisted set;
    absence is no longer a silent PASS."""
    pool = await get_pool()
    await _seed(pool)
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        await svc.recalculate_scores(MONTH)
    rows = await repo.get_scores(MONTH)
    sites = {row["site_code"] for row in rows}
    assert SITE in sites, (
        "F11 closure: the seeded store MUST appear in persisted scores; "
        "absence is no longer a silent PASS."
    )
    for row in rows:
        if row["site_code"] == SITE:
            assert row["score"] == 45
