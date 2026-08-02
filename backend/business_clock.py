from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

BUSINESS_TIMEZONE_NAME = "Europe/Bucharest"
BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)


class BusinessClock(Protocol):
    def now(self) -> datetime:
        """Return the current timezone-aware business datetime."""


@dataclass(frozen=True)
class SystemBusinessClock:
    timezone: ZoneInfo = BUSINESS_TIMEZONE

    def now(self) -> datetime:
        return datetime.now(self.timezone)

    def today(self) -> date:
        return self.now().date()


_DEFAULT_CLOCK: BusinessClock = SystemBusinessClock()


def get_business_clock() -> BusinessClock:
    return _DEFAULT_CLOCK


def _normalize_business_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("BusinessClock.now() must return a timezone-aware datetime")
    return value.astimezone(BUSINESS_TIMEZONE)


def business_now(clock: BusinessClock | None = None) -> datetime:
    return _normalize_business_datetime((clock or _DEFAULT_CLOCK).now())


def business_today(clock: BusinessClock | None = None) -> date:
    return business_now(clock).date()
