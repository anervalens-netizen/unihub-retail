from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from grile.domain.completion import (
    COMPLETION_ALGORITHM_VERSION,
    completed_days_for_month,
)
from grile.domain.provider_health import build_provider_health
from routers.grile import _refresh_operation_payload


def test_completion_window_is_bound_to_requested_month() -> None:
    assert completed_days_for_month("2026-07", as_of=date(2026, 8, 7)) == 31
    assert completed_days_for_month("2026-08", as_of=date(2026, 8, 7)) == 6
    assert completed_days_for_month("2026-09", as_of=date(2026, 8, 7)) == 0
    assert COMPLETION_ALGORITHM_VERSION == 2


def test_provider_error_is_not_hidden_by_last_success() -> None:
    now = datetime(2026, 8, 7, 8, tzinfo=timezone.utc)
    health = build_provider_health(
        run_month="2026-08",
        last_success_at=now - timedelta(minutes=10),
        last_error_at=now - timedelta(minutes=1),
        last_error_code="provider_timeout",
        last_error_message="timeout",
        stale_after_seconds=3600,
        now=now,
        business_date=date(2026, 8, 7),
    )
    assert health.state == "error"
    assert health.last_attempt_at == now - timedelta(minutes=1)


def test_provider_staleness_applies_only_to_current_month() -> None:
    now = datetime(2026, 8, 7, 8, tzinfo=timezone.utc)
    current = build_provider_health(
        run_month="2026-08",
        last_success_at=now - timedelta(hours=2),
        last_error_at=None,
        last_error_code=None,
        last_error_message=None,
        stale_after_seconds=3600,
        now=now,
        business_date=date(2026, 8, 7),
    )
    historical = build_provider_health(
        run_month="2026-07",
        last_success_at=now - timedelta(days=10),
        last_error_at=None,
        last_error_code=None,
        last_error_message=None,
        stale_after_seconds=3600,
        now=now,
        business_date=date(2026, 8, 7),
    )
    assert current.state == "stale"
    assert historical.state == "fresh"


def test_stale_provider_error_cannot_overtake_newer_success_projection() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "repositories" / "grile_persistence.py"
    ).read_text(encoding="utf-8")
    start = source.index("async def _apply_error_projection")
    projection = source[start:]
    assert (
        "EXCLUDED.last_error_generation >= grile_store_current_status.generation"
        in projection
    )


def test_unrecognized_refresh_state_is_publicly_unknown_and_fail_closed() -> None:
    payload = _refresh_operation_payload(
        {
            "id": 17,
            "run_month": "2026-08",
            "site_code": "S001",
            "status": "future_state",
            "projection_applied": None,
            "created_at": datetime(2026, 8, 7, tzinfo=timezone.utc),
        }
    )
    assert payload["status"] == "unknown"
    assert payload["error_code"] == "operation_state_unknown"
    assert "nu trebuie relansată automat" in str(payload["error_message"])
