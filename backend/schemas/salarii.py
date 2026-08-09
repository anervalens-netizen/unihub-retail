"""Strict public contracts for the salary API boundary."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field
from schemas.common import StrictApiModel, MonthStr


SalaryPersonId = Annotated[str, Field(pattern=r"^sp1_[0-9a-f]{64}$")]


class _PublicModel(StrictApiModel):
    model_config = ConfigDict(extra="forbid")


class SalaryAgentSummaryPublic(_PublicModel):
    person_id: SalaryPersonId
    full_name: str
    company_name: str
    locatie: str | None
    month_count: int
    avg_month_count: int
    total_salary: float
    avg_salary: float


class SalaryAgentsSummaryResponse(_PublicModel):
    items: list[SalaryAgentSummaryPublic]
    total: int


class SalaryHistoryRecordPublic(_PublicModel):
    year: int
    month: int
    company_name: str
    total_salary: float
    site_code: str | None
    locatie: str | None


class AgentSalaryLinkPublic(_PublicModel):
    agent_code: str
    site_code: str
    salary_full_name: str | None
    person_id: SalaryPersonId | None
    match_status: Literal["confirmed", "unknown"]
    match_source: Literal["auto", "manual"]
    confidence: Literal["high", "medium", "low", "unknown"]
    effective_from_month: MonthStr | None
    note: str | None


class SalaryHistoryResponse(_PublicModel):
    link: AgentSalaryLinkPublic | None = None
    records: list[SalaryHistoryRecordPublic]
    total: float
    avg: float
    month_count: int
    avg_month_count: int


class SalaryRecordPublic(_PublicModel):
    id: int
    year: int
    month: int
    full_name: str
    person_id: SalaryPersonId
    total_salary: float
    company_name: str
    site_code: str | None
    locatie: str | None
