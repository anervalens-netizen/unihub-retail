from __future__ import annotations

import asyncpg

from services.reporting_refresh_premium import _MONTH_INDEX_SQL

_LIFECYCLE_MONTH_SQL = """
        INSERT INTO reporting_agent_lifecycle_month (
            import_month,
            agent,
            total_sales,
            total_quantity,
            receipt_count,
            working_days,
            active_store_count,
            active_firma_count,
            active_regional_count,
            active_asm_count,
            first_seen_month,
            prev_active_month,
            gap_since_prev_active_months,
            is_new,
            is_reactivated,
            is_active
        )
        WITH base AS (
            SELECT
                import_month,
                agent,
                COALESCE(SUM(total_sales), 0)::NUMERIC(12, 2) AS total_sales,
                COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
                COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
                COALESCE(SUM(working_days), 0)::INT AS working_days,
                COUNT(DISTINCT site_code)::INT AS active_store_count,
                COUNT(DISTINCT firma)::INT AS active_firma_count,
                COUNT(DISTINCT regional)::INT AS active_regional_count,
                COUNT(DISTINCT asm)::INT AS active_asm_count
            FROM reporting_agent_month
            GROUP BY import_month, agent
        ),
        sequenced AS (
            SELECT
                base.*,
                MIN(import_month) OVER (PARTITION BY agent) AS first_seen_month,
                LAG(import_month) OVER (PARTITION BY agent ORDER BY import_month) AS prev_active_month
            FROM base
        )
        SELECT
            import_month,
            agent,
            total_sales,
            total_quantity,
            receipt_count,
            working_days,
            active_store_count,
            active_firma_count,
            active_regional_count,
            active_asm_count,
            first_seen_month,
            prev_active_month,
            CASE
                WHEN prev_active_month IS NULL THEN 0
                ELSE GREATEST({month_index} - ({prev_month_index}) - 1, 0)
            END::INT AS gap_since_prev_active_months,
            (prev_active_month IS NULL) AS is_new,
            (
                prev_active_month IS NOT NULL
                AND GREATEST({month_index} - ({prev_month_index}) - 1, 0) >= 2
            ) AS is_reactivated,
            true AS is_active
        FROM sequenced
        """

_AGENT_PROFILE_SQL = """
        INSERT INTO reporting_agent_profile (
            agent,
            first_seen_month,
            last_seen_month,
            active_months_count,
            distinct_store_count,
            distinct_firma_count,
            distinct_regional_count,
            distinct_asm_count,
            months_since_last_seen,
            reactivation_count,
            longest_active_streak,
            career_total_sales,
            career_total_quantity,
            avg_monthly_sales,
            best_month,
            best_month_sales,
            current_status
        )
        WITH lifecycle AS (
            SELECT
                agent,
                import_month,
                total_sales,
                total_quantity,
                first_seen_month,
                is_reactivated,
                ROW_NUMBER() OVER (PARTITION BY agent ORDER BY import_month) AS row_num,
                {month_index} AS month_index
            FROM reporting_agent_lifecycle_month
        ),
        streaks AS (
            SELECT
                agent,
                COUNT(*)::INT AS streak_length
            FROM (
                SELECT
                    agent,
                    month_index - row_num AS streak_group
                FROM lifecycle
            ) grouped
            GROUP BY agent, streak_group
        ),
        best_months AS (
            SELECT DISTINCT ON (agent)
                agent,
                import_month AS best_month,
                total_sales AS best_month_sales
            FROM reporting_agent_lifecycle_month
            ORDER BY agent, total_sales DESC, import_month DESC
        ),
        store_scope AS (
            SELECT
                agent,
                COUNT(DISTINCT site_code)::INT AS distinct_store_count,
                COUNT(DISTINCT firma)::INT AS distinct_firma_count,
                COUNT(DISTINCT regional)::INT AS distinct_regional_count,
                COUNT(DISTINCT asm)::INT AS distinct_asm_count
            FROM reporting_agent_month
            GROUP BY agent
        ),
        latest_month AS (
            SELECT MAX(import_month) AS latest_month
            FROM reporting_agent_lifecycle_month
        )
        SELECT
            lc.agent,
            MIN(lc.first_seen_month) AS first_seen_month,
            MAX(lc.import_month) AS last_seen_month,
            COUNT(*)::INT AS active_months_count,
            COALESCE(MAX(ss.distinct_store_count), 0)::INT AS distinct_store_count,
            COALESCE(MAX(ss.distinct_firma_count), 0)::INT AS distinct_firma_count,
            COALESCE(MAX(ss.distinct_regional_count), 0)::INT AS distinct_regional_count,
            COALESCE(MAX(ss.distinct_asm_count), 0)::INT AS distinct_asm_count,
            GREATEST(
                ({latest_month_index}) - ({max_month_index}),
                0
            )::INT AS months_since_last_seen,
            COUNT(*) FILTER (WHERE lc.is_reactivated)::INT AS reactivation_count,
            COALESCE(MAX(st.streak_length), 0)::INT AS longest_active_streak,
            COALESCE(SUM(lc.total_sales), 0)::NUMERIC(12, 2) AS career_total_sales,
            COALESCE(SUM(lc.total_quantity), 0)::INT AS career_total_quantity,
            CASE
                WHEN COUNT(*) > 0 THEN ROUND(COALESCE(SUM(lc.total_sales), 0) / COUNT(*), 2)
                ELSE 0
            END::NUMERIC(12, 2) AS avg_monthly_sales,
            MAX(bm.best_month) AS best_month,
            COALESCE(MAX(bm.best_month_sales), 0)::NUMERIC(12, 2) AS best_month_sales,
            CASE
                WHEN GREATEST(
                    ({latest_month_index}) - ({max_month_index}),
                    0
                ) >= 2
                THEN 'churned'
                WHEN GREATEST(
                    ({latest_month_index}) - ({max_month_index}),
                    0
                ) = 1
                THEN 'inactive_recent'
                ELSE 'active'
            END AS current_status
        FROM lifecycle lc
        CROSS JOIN latest_month lm
        LEFT JOIN streaks st
            ON st.agent = lc.agent
        LEFT JOIN best_months bm
            ON bm.agent = lc.agent
        LEFT JOIN store_scope ss
            ON ss.agent = lc.agent
        GROUP BY lc.agent, lm.latest_month
        """

async def rebuild_agent_lifecycle_reporting(conn: asyncpg.Connection) -> None:
    month_index = _MONTH_INDEX_SQL.format(alias="import_month")
    prev_month_index = _MONTH_INDEX_SQL.format(alias="prev_active_month")
    latest_month_index = _MONTH_INDEX_SQL.format(alias="lm.latest_month")
    max_month_index = _MONTH_INDEX_SQL.format(alias="MAX(lc.import_month)")

    await conn.execute("DELETE FROM reporting_agent_lifecycle_month")
    await conn.execute("DELETE FROM reporting_agent_profile")

    await conn.execute(
        _LIFECYCLE_MONTH_SQL.format(
            month_index=month_index,
            prev_month_index=prev_month_index,
        )
    )

    await conn.execute(
        _AGENT_PROFILE_SQL.format(
            month_index=_MONTH_INDEX_SQL.format(alias="import_month"),
            latest_month_index=latest_month_index,
            max_month_index=max_month_index,
        )
    )

    await conn.execute("ANALYZE reporting_agent_lifecycle_month")
    await conn.execute("ANALYZE reporting_agent_profile")


async def list_completed_import_months(conn: asyncpg.Connection) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT import_month
        FROM import_snapshots
        WHERE status = 'completed'
        ORDER BY import_month ASC
        """
    )
    return [str(row["import_month"]) for row in rows]
