"""Public API contracts for config-driven contest leaderboards."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from schemas.common import StrictApiModel, MonthStr



class ContestRuleInfo(StrictApiModel):
    type: str
    points: int
    label: str
    threshold: float | None = None


class ContestPrizeInfo(StrictApiModel):
    rank_from: int
    rank_to: int
    label: str


class ContestLeaderboardRow(StrictApiModel):
    rank: int
    agent: str
    site_code: str | None = None
    store_name: str | None = None
    firma: str | None = None
    focus_units: int = 0
    promo_bonuri: int = 0
    price_units: int = 0
    focus_points: int = 0
    promo_points: int = 0
    price_points: int = 0
    total_points: int = 0
    prize: str | None = None


class ContestResponse(StrictApiModel):
    key: str
    title: str
    subtitle: str = ""
    scope_label: str = ""
    month: MonthStr
    start_date: str
    end_date: str
    store_count: int = 0
    identity_policy: Literal["site_agent", "person_id"] = "site_agent"
    rules: list[ContestRuleInfo] = Field(default_factory=list)
    prizes: list[ContestPrizeInfo] = Field(default_factory=list)
    leaderboard: list[ContestLeaderboardRow] = Field(default_factory=list)
