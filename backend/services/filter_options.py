from __future__ import annotations

import time

from models import AgentOption, FilterOptions, StoreOption
from repositories.filters import FiltersRepository
from services.filters import normalize_filter


class FilterOptionsService:
    _cache: dict[str, tuple[FilterOptions, float]] = {}
    _CACHE_TTL_SECONDS = 300

    def __init__(self, repo: FiltersRepository):
        self.repo = repo

    @classmethod
    def _get_cached(cls, month: str) -> FilterOptions | None:
        if month in cls._cache:
            result, timestamp = cls._cache[month]
            if time.time() - timestamp < cls._CACHE_TTL_SECONDS:
                return result
        return None

    @classmethod
    def _set_cached(cls, month: str, result: FilterOptions) -> None:
        cls._cache[month] = (result, time.time())

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()

    async def get_options(self, month: str) -> FilterOptions:
        cached = self._get_cached(month)
        if cached is not None:
            return cached

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
        
        result = FilterOptions(
            firme=firme,
            regionali=regionali,
            asmi=asmi,
            magazine=magazine,
            agenti=agenti,
        )
        self._set_cached(month, result)
        return result

    async def get_available_months(self) -> list[str]:
        return await self.repo.get_available_months()
