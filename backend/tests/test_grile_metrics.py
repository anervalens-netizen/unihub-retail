from __future__ import annotations

import pytest

from services import grile_metrics


def test_grile_refresh_timings_emit_fixed_phases_once(monkeypatch) -> None:
    observed: list[tuple[str, float]] = []
    monkeypatch.setattr(
        grile_metrics,
        "observe_grile_store_refresh_phase",
        lambda phase, seconds: observed.append((phase, seconds)),
    )

    timings = grile_metrics.GrileStoreRefreshTimings()
    with timings.db():
        pass
    timings.queue_wait(2.0)
    timings.provider(0.5)
    timings.finish()
    timings.finish()

    assert [phase for phase, _seconds in observed] == [
        "queue_wait",
        "provider",
        "db",
        "total",
    ]
    assert observed[0] == ("queue_wait", 2.0)
    assert observed[1] == ("provider", 0.5)
    assert observed[2][1] >= 0
    assert observed[3][1] >= 2.0


def test_grile_refresh_metrics_reject_unknown_phase() -> None:
    with pytest.raises(ValueError, match="Unknown Grile refresh phase"):
        grile_metrics.observe_grile_store_refresh_phase("site_code", 1.0)


def test_grile_refresh_outcome_metric_has_fixed_cardinality(monkeypatch) -> None:
    from services import grile_metrics

    observed: list[str] = []

    class Labels:
        def inc(self) -> None:
            return None

    class Counter:
        def labels(self, outcome: str) -> Labels:
            observed.append(outcome)
            return Labels()

    monkeypatch.setattr(grile_metrics, "GRILE_STORE_REFRESH_OUTCOMES_TOTAL", Counter())
    grile_metrics.observe_grile_store_refresh_outcome("completed")
    grile_metrics.observe_grile_store_refresh_outcome("unbounded-provider-detail")
    assert observed == ["completed", "not_claimed"]
