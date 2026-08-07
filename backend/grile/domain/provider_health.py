from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from business_clock import business_today
from grile.domain.completion import parse_month

ProviderState = Literal["fresh", "stale", "error", "unknown"]


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    state: ProviderState
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    stale_age_seconds: int | None

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "last_error_at": self.last_error_at,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
            "stale_age_seconds": self.stale_age_seconds,
        }


def _age_seconds(value: datetime | None, *, now: datetime | None = None) -> int | None:
    if value is None:
        return None
    effective_now = now or datetime.now(tz=value.tzinfo)
    return max(0, int((effective_now - value).total_seconds()))


def build_provider_health(
    *,
    run_month: str,
    last_success_at: datetime | None,
    last_error_at: datetime | None,
    last_error_code: str | None,
    last_error_message: str | None,
    stale_after_seconds: int,
    now: datetime | None = None,
    business_date: date | None = None,
) -> ProviderHealth:
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be positive")

    last_attempt_at = max(
        (value for value in (last_success_at, last_error_at) if value is not None),
        default=None,
    )
    stale_age_seconds = _age_seconds(last_success_at, now=now)
    error_is_latest = (
        last_error_at is not None
        and (last_success_at is None or last_error_at >= last_success_at)
    )
    if error_is_latest:
        state: ProviderState = "error"
    elif last_success_at is None:
        state = "unknown"
    else:
        year, month_number = parse_month(run_month)
        today = business_date or business_today()
        is_current_month = (year, month_number) == (today.year, today.month)
        state = (
            "stale"
            if is_current_month
            and stale_age_seconds is not None
            and stale_age_seconds > stale_after_seconds
            else "fresh"
        )

    return ProviderHealth(
        state=state,
        last_attempt_at=last_attempt_at,
        last_success_at=last_success_at,
        last_error_at=last_error_at,
        last_error_code=last_error_code,
        last_error_message=last_error_message,
        stale_age_seconds=stale_age_seconds,
    )
