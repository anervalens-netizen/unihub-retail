from __future__ import annotations

import pytest

from services.grile_monthly_state import (
    operation_start_result,
    safe_persisted_result,
    terminal_operation_status,
)


@pytest.mark.parametrize(
    ("persisted_status", "expected"),
    [
        ("running", "already_running"),
        ("completed", "already_completed"),
        ("failed", "already_failed"),
        ("queued", "already_running"),
        ("unexpected", "already_running"),
    ],
)
def test_start_result_maps_every_persisted_state_fail_closed(
    persisted_status: str,
    expected: str,
) -> None:
    operation = {"id": 7, "status": persisted_status, "result": {"count": 1}}

    result = operation_start_result(
        operation_id=7,
        operation=operation,
        transition_claimed=False,
    )

    assert result.status == expected
    assert result.operation is operation
    assert result.result == {"count": 1}
    assert result.result is not operation["result"]


def test_start_result_distinguishes_claimed_and_missing_rows() -> None:
    operation = {"id": 7, "status": "running", "result": None}

    claimed = operation_start_result(
        operation_id=7,
        operation=operation,
        transition_claimed=True,
    )
    missing = operation_start_result(
        operation_id=8,
        operation=None,
        transition_claimed=False,
    )

    assert claimed.status == "started"
    assert missing.status == "not_found"
    assert missing.operation is None


@pytest.mark.parametrize("value", [None, "json", [], 1])
def test_safe_persisted_result_rejects_non_object_values(value: object) -> None:
    assert safe_persisted_result({"result": value}) is None


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "success"}, "completed"),
        ({"status": "failed"}, "failed"),
        ({}, "failed"),
    ],
)
def test_terminal_status_is_fail_closed(
    result: dict[str, object],
    expected: str,
) -> None:
    assert terminal_operation_status(result) == expected
