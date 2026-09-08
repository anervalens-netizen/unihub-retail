"""Provisional earnings components, never an official salary or payout."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EarningsDay(BaseModel):
    work_date: date
    site_code: str
    agent_code: str
    supplemental: bool
    away: bool
    sales: Decimal | None
    daily_target: Decimal | None
    commission: Decimal | None = None
    supplemental_pay: Decimal | None = Decimal(0)
    issue: str | None = None


class AgentEarnings(BaseModel):
    agent_code: str
    home_site_code: str
    home_work_days: int
    home_target: Decimal | None
    home_sales: Decimal | None
    home_commission: Decimal | None
    away_commission: Decimal | None
    supplemental_pay: Decimal | None
    known_earnings: Decimal | None
    days: list[EarningsDay]
    issues: list[str] = Field(default_factory=list)


class UnassignedSales(BaseModel):
    site_code: str
    sale_date: date
    sales: Decimal


class EarningsMonth(BaseModel):
    month: str
    status: Literal["provisional"] = "provisional"
    projection_revision: str
    calendar_revision: str
    source_snapshot_id: int | None
    source_revision: int | None
    cutoff: date | None
    selling_days: dict[str, int]
    agents: list[AgentEarnings]
    unassigned_sales: list[UnassignedSales] = Field(default_factory=list)
    unavailable_components: list[str] = Field(default_factory=lambda: [
        "salary_base", "vouchers", "sim", "epay", "manual_incentives",
    ])
