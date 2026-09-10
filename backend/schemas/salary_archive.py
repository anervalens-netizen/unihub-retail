from __future__ import annotations
from decimal import Decimal
from pydantic import Field
from schemas.common import StrictApiModel

class SalaryArchiveItem(StrictApiModel):
    period: str | None
    company_name: str | None
    full_name: str
    site_code: str | None
    location: str | None
    total_amount: Decimal | None
    identity_status: str
    review_reasons: list[str] = Field(default_factory=list)
    candidate_person_id: str | None
    source_file: str
    source_sheet: str
    source_row: int
    selected: bool
    pnl_eligible: bool
    already_recorded: bool

class SalaryArchiveResponse(StrictApiModel):
    items: list[SalaryArchiveItem]
    total_rows: int


class SalaryArchiveMonth(StrictApiModel):
    period: str
    company_name: str
    rows: int
    total: Decimal

class SalaryArchiveStore(StrictApiModel):
    site_code: str | None
    location: str
    company_name: str
    rows: int
    months: int
    total: Decimal

class SalaryArchiveAgent(StrictApiModel):
    full_name: str
    company_name: str
    total: Decimal
    months: int
    rows: int
    avg_salary: Decimal

class SalaryArchiveSummary(StrictApiModel):
    total: Decimal
    rows: int
    months: int
    excluded_rows: int
    monthly: list[SalaryArchiveMonth]
    stores: list[SalaryArchiveStore]
    agents: list[SalaryArchiveAgent]
