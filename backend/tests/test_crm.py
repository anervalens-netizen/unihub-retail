from __future__ import annotations
import pytest
from db.connection import get_pool
from repositories.crm import CrmRepository
from services.crm import CrmService


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_calculate_scores_returns_list(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("services.crm.get_visits_read_source", lambda: "sqlite")
    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    result = await svc.calculate_scores_for_month("2026-03")
    assert isinstance(result, list)
    if result:
        row = result[0]
        assert "site_code" in row
        assert "score" in row
        assert "breakdown" in row
        assert row["breakdown"]["target_pct"] >= 0


@pytest.mark.anyio
async def test_get_alerts_returns_list():
    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    result = await svc.get_alerts("2026-03")
    assert isinstance(result, list)


@pytest.mark.anyio
async def test_upsert_scores():
    pool = await get_pool()
    repo = CrmRepository(pool)
    svc = CrmService(repo, pool)
    test_scores = [{
        "site_code": "TEST99",
        "score": 75,
        "breakdown": {
            "target_pct": 30.0,
            "trend_pct": 20.0,
            "kpi_pct": 15.0,
            "visits_pct": 10.0,
            "total": 75,
        },
    }]
    await repo.upsert_scores("2026-01", test_scores)
    scores = await svc.get_scores("2026-01")
    test_score = next((s for s in scores if s["site_code"] == "TEST99"), None)
    if test_score:
        assert test_score["score"] == 75
