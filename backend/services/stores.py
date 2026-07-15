from __future__ import annotations

from typing import Any

import asyncpg
from fastapi import HTTPException, status

from models import StoreActivityChangeResponse, StoreOption
from repositories.stores import StoresRepository
from services.importer import upsert_store_targets


class StoresService:
    def __init__(self, repo: StoresRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def get_active_stores(self) -> list[StoreOption]:
        rows = await self.repo.get_active_stores()
        return [StoreOption(**dict(row)) for row in rows]

    async def save_targets(self, targets: list[dict[str, Any]]) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                inserted = await upsert_store_targets(
                    conn,
                    targets,
                    source_file="manual-api",
                )
        return inserted

    async def change_activity(
        self,
        *,
        site_code: str,
        expected_is_active: bool,
        new_is_active: bool,
        reason: str,
        requested_by_sub: str,
    ) -> StoreActivityChangeResponse:
        try:
            row = await self.repo.change_activity(
                site_code=site_code,
                expected_is_active=expected_is_active,
                new_is_active=new_is_active,
                reason=reason,
                requested_by_sub=requested_by_sub,
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Starea magazinului s-a modificat; reîncarcă înainte de confirmare.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Magazinul are deja starea solicitată.",
            ) from exc
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Magazinul nu există.",
            )
        return StoreActivityChangeResponse(
            site_code=str(row["site_code"]),
            previous_is_active=bool(row["previous_is_active"]),
            is_active=bool(row["new_is_active"]),
            event_id=int(row["id"]),
        )
