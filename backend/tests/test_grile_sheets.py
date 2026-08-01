from __future__ import annotations

from datetime import datetime

from services.grile_sheets import GRILA_RANGES, GRILA_RANGES_V3, analyze_grila


def _ranges(
    *,
    target: float = 1000,
    sales: float = 250,
    agent1_days: dict[int, float] | None = None,
    agent2_days: dict[int, float] | None = None,
    supl_days: list[int | None] | None = None,
) -> list[dict[str, list[list[object]]]]:
    agent1_days = agent1_days or {}
    agent2_days = agent2_days or {}
    supl_days = supl_days or []
    a1: list[list[object]] = [[agent1_days[d]] if d in agent1_days else [] for d in range(1, 32)]
    a2: list[list[object]] = [[agent2_days[d]] if d in agent2_days else [] for d in range(1, 32)]
    supl: list[list[object]] = [[None, None, d] for d in supl_days]
    supl.extend([] for _ in range(15 - len(supl)))
    return [
        {"values": [[target]]},
        {"values": [[sales]]},
        {"values": a1},
        {"values": a2},
        {"values": supl},
    ]


def test_analyze_grila_excludes_current_day_from_elapsed_days() -> None:
    reading = analyze_grila(
        _ranges(agent1_days={1: 100}, supl_days=[2]),
        as_of=datetime(2026, 6, 3, 12, 0),
    )

    assert reading.days_elapsed == 2
    assert reading.missing_days == []
    assert reading.completion_pct == 100.0


def test_analyze_grila_missing_days_stop_at_yesterday() -> None:
    reading = analyze_grila(
        _ranges(agent1_days={1: 100}),
        as_of=datetime(2026, 6, 3, 12, 0),
    )

    assert reading.days_elapsed == 2
    assert reading.missing_days == [2]
    assert reading.completion_pct == 50.0


def test_analyze_grila_first_day_has_no_elapsed_days() -> None:
    reading = analyze_grila(_ranges(), as_of=datetime(2026, 6, 1, 12, 0))

    assert reading.days_elapsed == 0
    assert reading.missing_days == []
    assert reading.completion_pct is None


def test_grila_ranges_include_all_fifteen_suplimentar_rows() -> None:
    assert "Grila!B32:G46" in GRILA_RANGES
    assert "Grila!B32:G37" not in GRILA_RANGES


def test_analyze_grila_counts_suplimentar_day_from_last_extended_row() -> None:
    reading = analyze_grila(
        _ranges(supl_days=[None] * 14 + [2]),
        as_of=datetime(2026, 6, 3, 12, 0),
    )

    assert reading.missing_days == [1]
    assert reading.completion_pct == 50.0


def test_v3_completion_counts_agent3_and_shifted_supplemental_range() -> None:
    assert "Grila!Z5:Z35" in GRILA_RANGES_V3
    assert "Grila!B46:G60" in GRILA_RANGES_V3
    reading = analyze_grila(
        [
            {"values": [[100]]},
            {"values": [[50]]},
            {"values": []},
            {"values": []},
            {"values": [[10], [20]]},
            {"values": []},
        ],
        as_of=datetime(2026, 8, 3),
    )
    assert reading.completion_pct == 100.0
    assert reading.missing_days == []
