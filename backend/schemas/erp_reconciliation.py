from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import MonthStr


ReconciliationStatus = Literal["ok", "explained", "difference", "not_comparable"]


class ErpReconciliationMetric(BaseModel):
    key: str
    label: str
    report_value: Decimal | None = None
    retail_value: Decimal | None = None
    difference: Decimal | None = None
    unit: Literal["RON", "buc", "bonuri", "magazine", "agenti"]
    status: ReconciliationStatus
    note: str | None = None


class ErpReconciliationIssue(BaseModel):
    severity: Literal["warning", "error"]
    scope: Literal["report", "store", "agent"]
    site_code: str | None = None
    entity: str
    metric: str
    report_value: Decimal | None = None
    retail_value: Decimal | None = None
    difference: Decimal | None = None
    note: str


class ErpReconciliationAppMetric(BaseModel):
    key: str
    label: str
    value: Decimal | None = None
    unit: Literal["RON", "buc"]
    note: str


class ErpReconciliationResponse(BaseModel):
    status: Literal["ok", "differences"]
    import_month: MonthStr
    report_cutoff_date: date
    retail_cutoff_date: date | None
    cutoff_matches: bool
    filename: str
    file_digest: str
    report_store_count: int = Field(ge=0)
    retail_store_count: int = Field(ge=0)
    report_agent_count: int = Field(ge=0)
    retail_agent_count: int = Field(ge=0)
    metrics: list[ErpReconciliationMetric]
    app_only_metrics: list[ErpReconciliationAppMetric]
    issues: list[ErpReconciliationIssue]
    issue_count: int = Field(ge=0)
    omitted_issue_count: int = Field(ge=0)
    notes: list[str]
