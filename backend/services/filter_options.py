from __future__ import annotations

import asyncio
import time

from models import AgentOption, FilterOptions, StoreOption
from repositories.filters import FiltersRepository
from services.filters import normalize_filter


class FilterOptionsService:
    _cache: dict[tuple[str, int], tuple[FilterOptions, float]] = {}
    _inflight: dict[tuple[str, int], asyncio.Task[FilterOptions]] = {}
    _generation = 0
    _CACHE_TTL_SECONDS = 300

    def __init__(self, repo: FiltersRepository):
        self.repo = repo

    @classmethod
    def _get_cached(cls, key: tuple[str, int]) -> FilterOptions | None:
        if key in cls._cache:
            result, timestamp = cls._cache[key]
            if time.time() - timestamp < cls._CACHE_TTL_SECONDS:
                return result
            cls._cache.pop(key, None)
        return None

    @classmethod
    def _set_cached(cls, key: tuple[str, int], result: FilterOptions) -> None:
        month, _version = key
        cls._cache = {
            cached_key: cached_value
            for cached_key, cached_value in cls._cache.items()
            if cached_key[0] != month
        }
        cls._cache[key] = (result, time.time())

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
        cls._generation += 1

    async def _build_options(self, month: str) -> FilterOptions:
        rows = await self.repo.get_raw_options(month)

        firme = sorted({row["firma"] for row in rows if normalize_filter(row["firma"])})
        regionali = sorted({row["regional"] for row in rows if normalize_filter(row["regional"])})
        asmi = sorted({row["asm"] for row in rows if normalize_filter(row["asm"])})
        magazine = list(
            {
                item["site_code"]: StoreOption(
                    site_code=item["site_code"],
                    locatie=item["locatie"],
                    firma=item["firma"],
                    regional=item["regional"],
                    asm=item["asm"],
                )
                for item in [dict(row) for row in rows]
            }.values()
        )
        magazine.sort(key=lambda item: item.locatie)
        agenti = list(
            {
                (item["agent"], item["site_code"]): AgentOption(
                    agent=item["agent"],
                    site_code=item["site_code"],
                    locatie=item["locatie"],
                    firma=item["firma"],
                    regional=item["regional"],
                    asm=item["asm"],
                )
                for item in [dict(row) for row in rows]
                if normalize_filter(item["agent"])
            }.values()
        )
        agenti.sort(key=lambda item: (item.agent, item.locatie))
        
        return FilterOptions(
            firme=firme,
            regionali=regionali,
            asmi=asmi,
            magazine=magazine,
            agenti=agenti,
        )

    async def get_options(self, month: str) -> FilterOptions:
        version = await self.repo.get_options_version(month)
        key = (month, version)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        generation = type(self)._generation
        task = type(self)._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._build_options(month))
            type(self)._inflight[key] = task
        try:
            result = await asyncio.shield(task)
        finally:
            if task.done() and type(self)._inflight.get(key) is task:
                type(self)._inflight.pop(key, None)

        if generation == type(self)._generation:
            self._set_cached(key, result)
        return result

    async def get_available_months(self) -> list[str]:
        return await self.repo.get_available_months()
