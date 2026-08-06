"""Focused tests for bounded, cancellable Dashboard scheduling."""

from __future__ import annotations

import asyncio

import pytest

from services.dashboard.metrics import (
    DASHBOARD_COMPONENT_ACTIVE,
    DASHBOARD_COMPONENT_BUDGET_VIOLATION_TOTAL,
    DASHBOARD_COMPONENT_GLOBAL_LIMIT,
)
from services.dashboard.scheduler import (
    _dashboard_global_active,
    _gather_cancel_on_error,
    _gather_named,
)


@pytest.mark.asyncio
async def test_gather_named_bounds_component_concurrency() -> None:
    active = 0
    peak_active = 0

    async def component(value: int) -> int:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    result = await _gather_named(
        2,
        summary=component(1),
        agents=component(2),
        stores=component(3),
        daily=component(4),
    )

    assert result == {"summary": 1, "agents": 2, "stores": 3, "daily": 4}
    assert peak_active == 2


@pytest.mark.asyncio
async def test_two_dashboard_requests_share_the_process_global_budget() -> None:
    active = 0
    peak_active = 0
    release = asyncio.Event()
    two_started = asyncio.Event()

    async def component(value: int) -> int:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        if active == 2:
            two_started.set()
        await release.wait()
        active -= 1
        return value

    first = asyncio.create_task(
        _gather_named(
            4,
            global_component_concurrency=2,
            summary=component(1),
            agents=component(2),
        )
    )
    second = asyncio.create_task(
        _gather_named(
            4,
            global_component_concurrency=2,
            stores=component(3),
            daily=component(4),
        )
    )
    await asyncio.wait_for(two_started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert active == 2
    assert peak_active == 2
    assert DASHBOARD_COMPONENT_ACTIVE._value.get() == 2  # type: ignore[attr-defined]
    assert DASHBOARD_COMPONENT_GLOBAL_LIMIT._value.get() == 2  # type: ignore[attr-defined]
    assert DASHBOARD_COMPONENT_BUDGET_VIOLATION_TOTAL._value.get() == 0  # type: ignore[attr-defined]

    release.set()
    await asyncio.gather(first, second)
    assert DASHBOARD_COMPONENT_ACTIVE._value.get() == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_component_coroutines_do_not_enter_before_a_global_slot() -> None:
    entered: list[str] = []
    release = asyncio.Event()
    first_started = asyncio.Event()

    async def component(name: str) -> str:
        entered.append(name)
        if name == "summary":
            first_started.set()
        await release.wait()
        return name

    task = asyncio.create_task(
        _gather_named(
            2,
            global_component_concurrency=1,
            summary=component("summary"),
            campaign_context=component("campaign_context"),
            promo_incentive=component("promo_incentive"),
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    await asyncio.sleep(0)

    assert entered == ["summary"]
    release.set()
    result = await task
    assert result == {
        "summary": "summary",
        "campaign_context": "campaign_context",
        "promo_incentive": "promo_incentive",
    }


@pytest.mark.asyncio
async def test_global_active_accounting_handles_out_of_order_completion() -> None:
    first_release = asyncio.Event()
    remaining_release = asyncio.Event()
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    third_started = asyncio.Event()

    async def component(name: str) -> str:
        if name == "summary":
            first_started.set()
            await first_release.wait()
        elif name == "agents":
            second_started.set()
            await remaining_release.wait()
        else:
            third_started.set()
            await remaining_release.wait()
        return name

    task = asyncio.create_task(
        _gather_named(
            3,
            global_component_concurrency=2,
            summary=component("summary"),
            agents=component("agents"),
            stores=component("stores"),
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    await asyncio.wait_for(second_started.wait(), timeout=1)
    first_release.set()
    await asyncio.wait_for(third_started.wait(), timeout=1)
    loop = asyncio.get_running_loop()
    assert _dashboard_global_active[loop][2] == 2
    remaining_release.set()
    await task

    assert _dashboard_global_active[loop][2] == 0


@pytest.mark.asyncio
async def test_child_failure_cancels_and_reaps_every_dashboard_task() -> None:
    cancelled = asyncio.Event()

    async def fail() -> None:
        raise RuntimeError("boom")

    async def wait_forever() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    with pytest.raises(RuntimeError, match="boom"):
        await _gather_cancel_on_error(
            fail(),
            wait_forever(),
            task_name="dashboard:test",
        )

    assert cancelled.is_set()
