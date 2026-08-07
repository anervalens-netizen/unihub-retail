"""Public API contracts for current-month and rolling AI forecasts."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import MonthStr


class AiForecastRunInfo(BaseModel):
    id: int
    forecast_month: MonthStr
    source_month: MonthStr
    metric: Literal["sales_value", "units"] = "sales_value"
    horizon: Literal["current_month", "rolling_12m"] = "current_month"
    model_name: str
    model_mode: str
    variant: str
    generated_at: datetime
    metadata: dict = Field(default_factory=dict)


class AiForecastSummary(BaseModel):
    forecast_month: MonthStr
    source_month: MonthStr
    actual_last_date: date | None = None
    days_elapsed: int = 0
    days_in_month: int
    store_count: int
    forecast_sales: Decimal
    expected_sales_to_date: Decimal
    actual_sales: Decimal
    delta_sales: Decimal
    delta_pct: Decimal | None = None


class AiForecastManagerRow(BaseModel):
    manager: str
    store_count: int
    forecast_sales: Decimal
    expected_sales_to_date: Decimal
    actual_sales: Decimal
    delta_sales: Decimal
    delta_pct: Decimal | None = None


class AiForecastStoreRow(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    forecast_sales: Decimal
    expected_sales_to_date: Decimal
    actual_sales: Decimal
    delta_sales: Decimal
    delta_pct: Decimal | None = None


class AiForecastDailyPoint(BaseModel):
    forecast_date: date
    forecast_sales: Decimal
    actual_sales: Decimal
    has_actual: bool
    cumulative_forecast: Decimal
    cumulative_actual: Decimal


class AiForecastResponse(BaseModel):
    run: AiForecastRunInfo
    summary: AiForecastSummary
    managers: list[AiForecastManagerRow] = Field(default_factory=list)
    stores: list[AiForecastStoreRow] = Field(default_factory=list)
    daily: list[AiForecastDailyPoint] = Field(default_factory=list)


class AiForecastRollingSummary(BaseModel):
    source_month: MonthStr
    start_month: MonthStr
    end_month: MonthStr
    month_count: int
    store_count: int
    forecast_sales: Decimal
    actual_sales: Decimal | None = None
    delta_sales: Decimal | None = None
    delta_pct: Decimal | None = None


class AiForecastRollingMonthlyPoint(BaseModel):
    forecast_month: MonthStr
    store_count: int
    forecast_sales: Decimal
    actual_sales: Decimal | None = None
    delta_sales: Decimal | None = None
    delta_pct: Decimal | None = None


class AiForecastRollingManagerRow(BaseModel):
    manager: str
    store_count: int
    forecast_sales: Decimal
    actual_sales: Decimal | None = None
    delta_sales: Decimal | None = None
    delta_pct: Decimal | None = None


class AiForecastRollingStoreRow(BaseModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    forecast_sales: Decimal
    actual_sales: Decimal | None = None
    delta_sales: Decimal | None = None
    delta_pct: Decimal | None = None


class AiForecastRollingResponse(BaseModel):
    runs: list[AiForecastRunInfo] = Field(default_factory=list)
    summary: AiForecastRollingSummary
    months: list[AiForecastRollingMonthlyPoint] = Field(default_factory=list)
    managers: list[AiForecastRollingManagerRow] = Field(default_factory=list)
    stores: list[AiForecastRollingStoreRow] = Field(default_factory=list)
