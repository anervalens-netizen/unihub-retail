from decimal import Decimal
from pydantic import BaseModel

class PerformanceMetrics(BaseModel):
    target: Decimal | None = None
    sales: Decimal | None = None
    progress: Decimal | None = None
    average: Decimal | None = None
    forecast: Decimal | None = None
    forecast_progress: Decimal | None = None
    scheduled_days: int = 0
    worked_days: int = 0
    leave_days: int = 0
    supplemental_days: int = 0
    daily_80: Decimal | None = None
    daily_90: Decimal | None = None
    daily_100: Decimal | None = None
    daily_120: Decimal | None = None

class SalaryMetrics(BaseModel):
    sim_pay: Decimal | None = None
    epay_pay: Decimal | None = None
    commission_total: Decimal | None = None
    current_total: Decimal | None = None
    forecast_total: Decimal | None = None
    potential_120: Decimal | None = None
