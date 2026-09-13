"""Lot 46 F04 characterization: ``stores.regional`` NOT NULL invariant.

The authoritative schema declares ``stores.regional TEXT NOT NULL``. Because
that constraint is enforced at the column level, the P&L "Nealocat" scope
divergence between ``COALESCE(s.regional, 'Nealocat')`` and the raw
``s.regional = $regional`` predicate cannot be reproduced without first
relaxing the schema. F04 is therefore a ``FALSE POSITIVE`` against the
current authoritative schema; no production change is warranted.

This module pins the invariant that explains the disposition. It does NOT
alter the schema and it does NOT insert impossible NULL-regional store data.

Three bounded checks:

1. ``pg_catalog`` reports ``stores.regional`` as ``attnotnull = true``.
2. The same invariant is reported after the focused Lot 46 suite ran.
3. A ``SAVEPOINT``-bounded attempt to insert a NULL-regional store row is
   rejected by PostgreSQL with the standard NOT NULL violation (rolled back).

Plus a tiny sanity regression on the named-regional path so that, if a future
change ever relaxes the constraint, we still have a positive anchor to read.
"""

from __future__ import annotations

import os

import pytest

from db.connection import get_pool

NAMED_REGIONAL_SITE = "PNL-L46-NAMEDREG"
FIRMA = "Mobicell"
REGIONAL = "L46 Named Region"

pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated test database",
)


async def _stores_regional_is_not_null(connection) -> bool:
    return bool(
        await connection.fetchval(
            """
            SELECT attnotnull
            FROM pg_attribute
            WHERE attrelid = 'stores'::regclass
              AND attname = 'regional'
            """
        )
    )


async def _delete_named_regional_site() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM stores WHERE site_code = $1",
            NAMED_REGIONAL_SITE,
        )


async def _seed_named_regional_site() -> None:
    pool = await get_pool()
    async with pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm,
                first_seen_month, last_seen_month, is_active
            ) VALUES (
                $1, 'P&L L46 named regional', $2, $3, 'L46 ASM',
                '2097-07', '2097-07', TRUE
            )
            """,
            NAMED_REGIONAL_SITE, FIRMA, REGIONAL,
        )


@pytest.mark.anyio
async def test_f04_stores_regional_is_not_null_in_pg_catalog() -> None:
    """Invariant: ``stores.regional`` carries the NOT NULL constraint."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        assert await _stores_regional_is_not_null(connection), (
            "Authoritative schema invariant broken: stores.regional must be "
            "declared NOT NULL. Re-evaluate the F04 disposition before "
            "introducing any production delta."
        )


@pytest.mark.anyio
async def test_f04_null_regional_insert_is_rejected() -> None:
    """A NULL ``regional`` insert must be rejected by PostgreSQL.

    The insert runs inside a SAVEPOINT so the test transaction is left
    unchanged if the rejection ever stops happening.
    """
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            await connection.execute("SAVEPOINT f04_null_probe")
            with pytest.raises(Exception) as exc_info:
                await connection.execute(
                    """
                    INSERT INTO stores (
                        site_code, locatie, firma, regional, asm,
                        first_seen_month, last_seen_month, is_active
                    ) VALUES (
                        'PNL-L46-NULLPROBE', 'P&L L46 null probe', $1,
                        NULL, 'L46 ASM', '2097-07', '2097-07', TRUE
                    )
                    """,
                    FIRMA,
                )
            message = str(exc_info.value)
            assert "regional" in message or "not-null" in message.lower() or \
                "23502" in message, (
                "Expected the standard NOT NULL violation on stores.regional, "
                f"got: {message!r}"
            )
            await connection.execute("ROLLBACK TO SAVEPOINT f04_null_probe")
            await connection.execute("RELEASE SAVEPOINT f04_null_probe")
        assert await _stores_regional_is_not_null(connection), (
            "Schema invariant must still hold after the probe."
        )


@pytest.mark.anyio
async def test_f04_named_regional_round_trip() -> None:
    """Positive anchor: a valid named-regional store inserts and reads back."""
    await _delete_named_regional_site()
    try:
        await _seed_named_regional_site()
        pool = await get_pool()
        async with pool.acquire() as connection:
            regional = await connection.fetchval(
                "SELECT regional FROM stores WHERE site_code = $1",
                NAMED_REGIONAL_SITE,
            )
            firma = await connection.fetchval(
                "SELECT firma FROM stores WHERE site_code = $1",
                NAMED_REGIONAL_SITE,
            )
        assert regional == REGIONAL
        assert firma == FIRMA
    finally:
        await _delete_named_regional_site()
