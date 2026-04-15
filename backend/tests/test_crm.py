from __future__ import annotations
import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_calculate_scores_returns_list():
    from routers.crm import calculate_scores_for_month
    pool = await get_pool()
    async with pool.acquire() as conn:
        scores = await calculate_scores_for_month(conn, "2026-03")
        assert isinstance(scores, list)
        if scores:
            score = scores[0]
            assert "site_code" in score
            assert "score" in score
            assert 0 <= score["score"] <= 100
            assert "breakdown" in score
            bd = score["breakdown"]
            for key in ("target_pct", "trend_pct", "kpi_pct", "kpi_bon2acc_score",
                        "kpi_focus_score", "visits_pct", "kpi_bon2acc", "kpi_focus",
                        "kpi_bon2acc_avg", "kpi_focus_avg", "nr_vizite", "avg_completion"):
                assert key in bd, f"breakdown missing key: {key}"


@pytest.mark.anyio
async def test_get_alerts_returns_list():
    from routers.crm import get_store_alerts
    pool = await get_pool()
    async with pool.acquire() as conn:
        alerts = await get_store_alerts(conn, "2026-03")
        assert isinstance(alerts, list)
        for alert in alerts:
            assert "site_code" in alert
            assert "reasons" in alert
            assert isinstance(alert["reasons"], list)


@pytest.mark.anyio
async def test_upsert_scores():
    from routers.crm import calculate_scores_for_month, upsert_scores
    pool = await get_pool()
    async with pool.acquire() as conn:
        scores = await calculate_scores_for_month(conn, "2026-03")
        if scores:
            await upsert_scores(conn, "2026-03", scores)
            rows = await conn.fetch(
                "SELECT site_code, score FROM store_scores WHERE score_month = '2026-03' LIMIT 5"
            )
            assert len(rows) > 0
