from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.filter_options import FilterOptionsService


def _row(agent: str) -> dict[str, str]:
    return {
        "firma": "MobiUp",
        "regional": "Manager",
        "asm": "ASM",
        "site_code": "S01",
        "locatie": "Magazin",
        "agent": agent,
    }


@pytest.mark.asyncio
async def test_options_cache_is_invalidated_by_completed_snapshot_version() -> None:
    FilterOptionsService.clear_cache()
    repo = AsyncMock()
    repo.get_options_version.side_effect = [10, 10, 11]
    repo.get_raw_options.side_effect = [[_row("Agent vechi")], [_row("Agent nou")]]
    service = FilterOptionsService(repo)

    first = await service.get_options("2026-07")
    cached = await service.get_options("2026-07")
    refreshed = await service.get_options("2026-07")

    assert first.agenti[0].agent == "Agent vechi"
    assert cached.agenti[0].agent == "Agent vechi"
    assert refreshed.agenti[0].agent == "Agent nou"
    assert repo.get_raw_options.await_count == 2
    FilterOptionsService.clear_cache()


@pytest.mark.asyncio
async def test_options_cache_coalesces_concurrent_cold_loads() -> None:
    FilterOptionsService.clear_cache()
    repo = AsyncMock()
    repo.get_options_version.return_value = 12

    async def load(_month: str) -> list[dict[str, str]]:
        await asyncio.sleep(0)
        return [_row("Agent")]

    repo.get_raw_options.side_effect = load
    service = FilterOptionsService(repo)

    left, right = await asyncio.gather(
        service.get_options("2026-07"),
        service.get_options("2026-07"),
    )

    assert left == right
    assert repo.get_raw_options.await_count == 1
    FilterOptionsService.clear_cache()
