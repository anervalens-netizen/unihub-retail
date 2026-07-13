"""Public API contracts for config-driven contest leaderboards."""
from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.common import MonthStr


class ContestRuleInfo(BaseModel):
    type: str
    points: int
    label: str
    threshold: float | None = None


class ContestPrizeInfo(BaseModel):
    rank_from: int
    rank_to: int
    label: str


class ContestLeaderboardRow(BaseModel):
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


class ContestResponse(BaseModel):
    key: str
    title: str
    subtitle: str = ""
    scope_label: str = ""
    month: MonthStr
    start_date: str
    end_date: str
    store_count: int = 0
    rules: list[ContestRuleInfo] = Field(default_factory=list)
    prizes: list[ContestPrizeInfo] = Field(default_factory=list)
    leaderboard: list[ContestLeaderboardRow] = Field(default_factory=list)
