from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import models
from schemas.agents import AgentEvaluationV2Row, AgentsOverviewResponse
from schemas.ai_forecast import AiForecastResponse, AiForecastRunInfo, AiForecastSummary
from schemas.campaigns import CampaignSnapshot
from schemas.contests import ContestResponse, ContestRuleInfo
from schemas.premium_glass import PremiumGlassAnalysis


def test_legacy_model_imports_reexport_domain_classes() -> None:
    assert models.AiForecastResponse is AiForecastResponse
    assert models.AiForecastRunInfo is AiForecastRunInfo
    assert models.ContestResponse is ContestResponse
    assert models.ContestRuleInfo is ContestRuleInfo
    assert models.AgentsOverviewResponse is AgentsOverviewResponse
    assert models.AgentEvaluationV2Row is AgentEvaluationV2Row
    assert models.CampaignSnapshot is CampaignSnapshot
    assert models.PremiumGlassAnalysis is PremiumGlassAnalysis


def test_ai_forecast_serialization_contract_is_preserved() -> None:
    response = AiForecastResponse(
        run=AiForecastRunInfo(
            id=7,
            forecast_month="2026-08",
            source_month="2026-07",
            model_name="chronos",
            model_mode="remote",
            variant="v3",
            generated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        ),
        summary=AiForecastSummary(
            forecast_month="2026-08",
            source_month="2026-07",
            days_in_month=31,
            store_count=10,
            forecast_sales=Decimal("1000.00"),
            expected_sales_to_date=Decimal("200.00"),
            actual_sales=Decimal("210.00"),
            delta_sales=Decimal("10.00"),
        ),
    )

    payload = response.model_dump(mode="json")
    assert payload["run"]["metric"] == "sales_value"
    assert payload["run"]["horizon"] == "current_month"
    assert payload["summary"]["forecast_sales"] == "1000.00"
    assert payload["managers"] == []
    assert payload["stores"] == []
    assert payload["daily"] == []


def test_contest_serialization_contract_is_preserved() -> None:
    response = ContestResponse(
        key="iulie",
        title="Concurs iulie",
        month="2026-07",
        start_date="2026-07-01",
        end_date="2026-07-31",
        rules=[ContestRuleInfo(type="focus", points=2, label="Focus")],
    )

    assert response.model_dump() == {
        "key": "iulie",
        "title": "Concurs iulie",
        "subtitle": "",
        "scope_label": "",
        "month": "2026-07",
        "start_date": "2026-07-01",
        "end_date": "2026-07-31",
        "store_count": 0,
        "rules": [{"type": "focus", "points": 2, "label": "Focus", "threshold": None}],
        "prizes": [],
        "leaderboard": [],
    }
