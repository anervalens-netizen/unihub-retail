"""Native scheduling inputs; sales transaction codes never assign attendance."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from schemas.common import MonthStr

Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def _valid_month(value: str) -> str:
    try:
        date.fromisoformat(value + "-01") - timedelta(days=1)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Calendar month must have a valid preceding month") from exc
    return value


CalendarMonthKey = Annotated[MonthStr, AfterValidator(_valid_month)]


class RosterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    home_site_code: Code
    active: bool = True
    expected_revision: int = Field(ge=0)


class CalendarDayInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    work_date: date
    agent_code: Code
    site_code: Code
    status: Literal["work", "leave", "off", "cancelled"]
    supplemental: bool = False
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_supplement(self) -> CalendarDayInput:
        if self.supplemental and self.status != "work":
            raise ValueError("Only a working day can be supplemental")
        return self


class CalendarChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    days: list[CalendarDayInput] = Field(min_length=1, max_length=93)

    @model_validator(mode="after")
    def validate_distinct_days(self) -> CalendarChanges:
        keys = {(day.work_date, day.agent_code) for day in self.days}
        if len(keys) != len(self.days):
            raise ValueError("An agent/date may occur only once in a change")
        return self


class RosterEntry(BaseModel):
    month: str
    agent_code: str
    home_site_code: str
    active: bool
    revision: int


class CalendarDay(BaseModel):
    work_date: date
    agent_code: str
    site_code: str
    status: Literal["work", "leave", "off", "cancelled"]
    supplemental: bool
    revision: int


class AgentCandidate(BaseModel):
    agent_code: str
    source_month: str
    site_codes: list[str]
    needs_active_confirmation: bool
    needs_home_confirmation: bool


class CalendarAttendance(BaseModel):
    agent_code: str
    work_days: int = 0
    leave_days: int = 0
    off_days: int = 0
    work_days_by_site: dict[str, int] = Field(default_factory=dict)


class CalendarMonth(BaseModel):
    month: str
    roster: list[RosterEntry]
    days: list[CalendarDay]
    attendance: list[CalendarAttendance]
