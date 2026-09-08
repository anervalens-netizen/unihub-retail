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


class StoreHoursInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opens: str = Field(default="10:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    closes: str = Field(default="22:00", pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    break_minutes: int = Field(default=60, ge=0, le=720)
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_duration(self) -> StoreHoursInput:
        if self.net_minutes <= 0:
            raise ValueError("Closing must follow opening and leave positive worked time after the break")
        return self

    @property
    def net_minutes(self) -> int:
        def minutes(value: str) -> int:
            hour, minute = value.split(":")
            return int(hour) * 60 + int(minute)
        return minutes(self.closes) - minutes(self.opens) - self.break_minutes


class StoreHours(BaseModel):
    site_code: str
    opens: str = "10:00"
    closes: str = "22:00"
    break_minutes: int = 60
    revision: int = 0

    @property
    def net_minutes(self) -> int:
        return StoreHoursInput(opens=self.opens, closes=self.closes,
                               break_minutes=self.break_minutes, expected_revision=0).net_minutes


class AttendanceDay(BaseModel):
    work_date: date
    agent_code: str
    site_code: str
    status: Literal["work", "leave", "off"]
    worked_minutes: int
    opens: str | None = None
    closes: str | None = None
    break_minutes: int = 0


class CalendarAttendance(BaseModel):
    agent_code: str
    worked_minutes: int = 0
    work_days: int = 0
    leave_days: int = 0
    off_days: int = 0
    work_days_by_site: dict[str, int] = Field(default_factory=dict)


class CalendarMonth(BaseModel):
    month: str
    roster: list[RosterEntry]
    days: list[CalendarDay]
    attendance: list[CalendarAttendance]
    store_hours: list[StoreHours] = Field(default_factory=list)
    attendance_by_store: dict[str, list[CalendarAttendance]] = Field(default_factory=dict)
    attendance_days: list[AttendanceDay] = Field(default_factory=list)
    projection_revision: str = ""
