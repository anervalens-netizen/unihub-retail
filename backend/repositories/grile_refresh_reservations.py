from __future__ import annotations

import asyncpg


async def allocate_generation(
    conn: asyncpg.Connection,
    run_month: str,
    site_code: str,
) -> int:
    return int(
        await conn.fetchval(
            """
            INSERT INTO grile_store_projection_generations (
                run_month, site_code, next_generation
            )
            VALUES ($1, $2, 1)
            ON CONFLICT (run_month, site_code) DO UPDATE
            SET next_generation = grile_store_projection_generations.next_generation + 1
            RETURNING next_generation
            """,
            run_month,
            site_code,
        )
    )


async def reserve_store_refresh_on_connection(
    conn: asyncpg.Connection,
    *,
    run_month: str,
    site_code: str,
    requested_by_sub: str,
) -> int | None:
    """Serialize one store reservation before consuming its projection generation."""
    await conn.execute(
        """
        INSERT INTO grile_store_projection_generations (
            run_month, site_code, next_generation
        ) VALUES ($1, $2, 0)
        ON CONFLICT (run_month, site_code) DO NOTHING
        """,
        run_month,
        site_code,
    )
    await conn.fetchval(
        """
        SELECT next_generation
        FROM grile_store_projection_generations
        WHERE run_month = $1 AND site_code = $2
        FOR UPDATE
        """,
        run_month,
        site_code,
    )
    active_refresh_id = await conn.fetchval(
        """
        SELECT id
        FROM grile_store_refreshes
        WHERE run_month = $1 AND site_code = $2
          AND status IN ('queued', 'running')
        LIMIT 1
        """,
        run_month,
        site_code,
    )
    if active_refresh_id is not None:
        return None
    generation = await allocate_generation(conn, run_month, site_code)
    return await conn.fetchval(
        """
        INSERT INTO grile_store_refreshes (
            run_month, site_code, generation, requested_by_sub, heartbeat_at
        )
        VALUES ($1, $2, $3, $4, now())
        RETURNING id
        """,
        run_month,
        site_code,
        generation,
        requested_by_sub,
    )
