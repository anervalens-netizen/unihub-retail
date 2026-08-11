"""Strict public contracts for the salary API boundary."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from domain.filter_scope import normalize_filter_values
from schemas.common import StrictApiModel, MonthStr


SalaryPersonId = Annotated[str, Field(pattern=r"^sp1_[0-9a-f]{64}$")]
SalaryMoney = Annotated[Decimal, Field(allow_inf_nan=False)]
SalaryExportKind = Literal["store_summary", "monthly_trend", "agents"]


class _PublicModel(StrictApiModel):
    model_config = ConfigDict(extra="forbid")


class SalaryExportRequest(_PublicModel):
    """Canonical, server-owned request for a sensitive salary artifact."""

    export_kind: SalaryExportKind
    company_name: str | None = Field(default=None, max_length=120)
    site_code: list[str] = Field(default_factory=list, max_length=200)
    regional: str | None = Field(default=None, max_length=120)
    asm: str | None = Field(default=None, max_length=120)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    q: str | None = Field(default=None, max_length=160)

    @field_validator("company_name", "regional", "asm", "q", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @field_validator("site_code")
    @classmethod
    def canonicalize_site_codes(cls, value: list[str]) -> list[str]:
        return normalize_filter_values(value) or []

    @model_validator(mode="after")
    def validate_kind_scope(self) -> "SalaryExportRequest":
        if (self.year is None) != (self.month is None):
            raise ValueError("year and month must be provided together")
        if self.export_kind == "monthly_trend" and (
            self.year is not None or self.q is not None
        ):
            raise ValueError("monthly_trend does not accept period or search filters")
        if self.export_kind == "store_summary" and self.q is not None:
            raise ValueError("store_summary does not accept a search filter")
        if self.site_code:
            self.company_name = None
            self.regional = None
            self.asm = None
        return self


class SalaryAgentSummaryPublic(_PublicModel):
    person_id: SalaryPersonId
    full_name: str
    company_name: str
    locatie: str | None
    month_count: int
    avg_month_count: int
    total_salary: SalaryMoney
    avg_salary: SalaryMoney


class SalaryAgentsSummaryResponse(_PublicModel):
    items: list[SalaryAgentSummaryPublic]
    total: int


class SalaryHistoryRecordPublic(_PublicModel):
    year: int
    month: int
    company_name: str
    total_salary: SalaryMoney
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
    total: SalaryMoney
    avg: SalaryMoney
    month_count: int
    avg_month_count: int


class SalaryRecordPublic(_PublicModel):
    id: int
    year: int
    month: int
    full_name: str
    person_id: SalaryPersonId
    total_salary: SalaryMoney
    company_name: str
    site_code: str | None
    locatie: str | None
