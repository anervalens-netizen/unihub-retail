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
