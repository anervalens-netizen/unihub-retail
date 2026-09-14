"""Persistence helpers for the fenced Grile V2 Sheets writer."""
from typing import Any


async def list_exports(conn) -> list[dict[str, Any]]:
    return [dict(row) for row in await conn.fetch(
        "SELECT * FROM grile_v2_sheet_exports ORDER BY run_month,site_code",
    )]


async def mark_source_unavailable(conn, month: str) -> None:
    await conn.execute(
        "UPDATE grile_v2_sheet_exports SET status='failed',last_error_at=now(),"
        "last_error_code='source_unavailable',last_error_message='Datele sursă nu au putut fi citite; ultima grilă validă se păstrează.',updated_at=now() WHERE run_month=$1",
        month,
    )


async def mark_running(conn, row_id: int, digest: str) -> None:
    await conn.execute(
        "UPDATE grile_v2_sheet_exports SET source_hash=$2,status='running',last_attempt_at=now(),updated_at=now() WHERE id=$1",
        row_id, digest,
    )


async def mark_succeeded(conn, row_id: int, digest: str) -> None:
    await conn.execute(
        "UPDATE grile_v2_sheet_exports SET published_hash=$2,status='succeeded',last_success_at=now(),last_error_code=NULL,last_error_message=NULL,updated_at=now() WHERE id=$1 AND source_hash=$2",
        row_id, digest,
    )


async def mark_failed(conn, row_id: int, code: str) -> None:
    await conn.execute(
        "UPDATE grile_v2_sheet_exports SET status='failed',last_error_at=now(),last_error_code=$2,last_error_message='Publicare nereușită; se reîncearcă automat.',updated_at=now() WHERE id=$1",
        row_id, code,
    )


async def mark_unchanged_succeeded(conn, row_id: int) -> None:
    await conn.execute(
        "UPDATE grile_v2_sheet_exports SET status='succeeded',last_error_code=NULL,last_error_message=NULL,updated_at=now() WHERE id=$1",
        row_id,
    )


async def read_store_catalog(pool, sites: list[str]) -> dict[str, dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT site_code,locatie,firma,regional FROM stores WHERE site_code=ANY($1::text[])',
            sites,
        )
    return {row['site_code']: dict(row) for row in rows}


async def fence_alive(conn) -> None:
    await conn.fetchval("SELECT 1")


async def try_lock(conn, key: int) -> bool:
    return bool(await conn.fetchval("SELECT pg_try_advisory_lock($1)", key))


async def unlock(conn, key: int) -> None:
    await conn.execute("SELECT pg_advisory_unlock($1)", key)


async def run_fenced(pool, key: int, callback):
    async with pool.acquire() as fence:
        if not await try_lock(fence, key):
            return {'skipped': 'writer_active'}
        try:
            return await callback(fence)
        finally:
            await unlock(fence, key)
