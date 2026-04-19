from __future__ import annotations

import pytest
from db.connection import get_pool


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_insert_and_list_error_log():
    from routers.errors import insert_error_log, list_error_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await insert_error_log(conn, {
            "source": "backend",
            "level": "error",
            "message": "test error",
            "traceback": "Traceback...",
            "path": "/api/test",
            "extra": None,
        })
        assert row["message"] == "test error"
        assert row["seen"] is False
        log_id = row["id"]

        rows = await list_error_logs(conn, source=None, level=None, seen=None,
                                     from_date=None, to_date=None, page=1, page_size=50)
        ids = [r["id"] for r in rows]
        assert log_id in ids

        await conn.execute("DELETE FROM error_logs WHERE id = $1", log_id)


@pytest.mark.anyio
async def test_mark_all_seen():
    from routers.errors import insert_error_log, mark_all_seen, get_unseen_count
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await insert_error_log(conn, {
            "source": "frontend", "level": "error",
            "message": "js crash", "traceback": None,
            "path": "/app", "extra": None,
        })
        log_id = row["id"]

        count_before = await get_unseen_count(conn)
        assert count_before >= 1

        await mark_all_seen(conn)
        count_after = await get_unseen_count(conn)
        assert count_after == 0

        await conn.execute("DELETE FROM error_logs WHERE id = $1", log_id)


@pytest.mark.anyio
async def test_delete_old_logs():
    from routers.errors import insert_error_log, delete_old_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO error_logs (source, level, message, ts)
            VALUES ('backend', 'error', 'old error', now() - interval '31 days')
            RETURNING id
            """
        )
        old_id = row["id"]

        deleted = await delete_old_logs(conn, days=30)
        assert deleted >= 1

        remaining = await conn.fetchval(
            "SELECT COUNT(*) FROM error_logs WHERE id = $1", old_id
        )
        assert remaining == 0


@pytest.mark.anyio
async def test_rate_limiter():
    from routers.errors import RateLimiter
    limiter = RateLimiter(limit=3, window=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False  # al 4-lea respins
    assert limiter.allow("5.6.7.8") is True   # alt IP — ok


@pytest.mark.anyio
async def test_list_filter_by_source():
    from routers.errors import insert_error_log, list_error_logs
    pool = await get_pool()
    async with pool.acquire() as conn:
        r1 = await insert_error_log(conn, {
            "source": "backend", "level": "error", "message": "be err",
            "traceback": None, "path": None, "extra": None,
        })
        r2 = await insert_error_log(conn, {
            "source": "frontend", "level": "error", "message": "fe err",
            "traceback": None, "path": None, "extra": None,
        })

        be_rows = await list_error_logs(conn, source="backend", level=None,
                                        seen=None, from_date=None, to_date=None,
                                        page=1, page_size=50)
        sources = {r["source"] for r in be_rows}
        assert sources == {"backend"}

        await conn.execute("DELETE FROM error_logs WHERE id = ANY($1)", [r1["id"], r2["id"]])
