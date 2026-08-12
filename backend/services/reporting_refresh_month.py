from __future__ import annotations

import asyncpg

from services.reporting_refresh_premium import (
    _BRAND_GROUP_SQL,
    _RETAIL_TRANSACTION_EXCLUSIONS_SQL,
    refresh_premium_glass_indicators,
)

_REPORTING_MONTH_SQL_1 = """
        INSERT INTO reporting_cartela_day (
            import_month,
            sale_date,
            site_code,
            agent,
            total_quantity
        )
        SELECT
            st.import_month,
            st.sale_date,
            st.site_code,
            st.agent,
            COALESCE(SUM(st.quantity), 0)::INT AS total_quantity
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND st.is_cartela = true
          AND s.locatie NOT ILIKE 'TR %'
        GROUP BY st.import_month, st.sale_date, st.site_code, st.agent
        """

_REPORTING_MONTH_SQL_2 = """
        CREATE TEMP TABLE tmp_reporting_receipts (
            import_month TEXT NOT NULL,
            sale_date DATE NOT NULL,
            site_code TEXT NOT NULL,
            agent TEXT NOT NULL,
            bon_nr TEXT NOT NULL,
            net_quantity INTEGER NOT NULL
        )
        """

_REPORTING_MONTH_SQL_3 = f"""
        INSERT INTO tmp_reporting_receipts (
            import_month,
            sale_date,
            site_code,
            agent,
            bon_nr,
            net_quantity
        )
        SELECT
            st.import_month,
            st.sale_date,
            st.site_code,
            st.agent,
            st.bon_nr,
            COALESCE(SUM(st.quantity), 0)::INT AS net_quantity
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND {_RETAIL_TRANSACTION_EXCLUSIONS_SQL}
        GROUP BY st.import_month, st.sale_date, st.site_code, st.agent, st.bon_nr
        """

_REPORTING_MONTH_SQL_4 = """
        CREATE INDEX idx_tmp_reporting_receipts_keys
            ON tmp_reporting_receipts (import_month, sale_date, site_code, agent, bon_nr)
        """

_REPORTING_MONTH_SQL_5 = f"""
        INSERT INTO reporting_agent_day (
            import_month,
            sale_date,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            total_sales,
            total_quantity,
            focus_quantity,
            receipt_count,
            receipt_2plus_count,
            receipt_1_count,
            receipt_2_count,
            receipt_3_count,
            receipt_4plus_count
        )
        SELECT
            st.import_month,
            st.sale_date,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            COALESCE(SUM(st.total_value), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(st.quantity), 0)::INT AS total_quantity,
            COALESCE(
                SUM(CASE WHEN fp.item_code IS NOT NULL THEN st.quantity ELSE 0 END),
                0
            )::INT AS focus_quantity,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity > 0)::INT AS receipt_count,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity >= 2)::INT AS receipt_2plus_count,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity = 1)::INT AS receipt_1_count,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity = 2)::INT AS receipt_2_count,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity = 3)::INT AS receipt_3_count,
            COUNT(DISTINCT st.bon_nr) FILTER (WHERE tr.net_quantity >= 4)::INT AS receipt_4plus_count
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        LEFT JOIN focus_products fp ON fp.item_code = st.item_code
        LEFT JOIN tmp_reporting_receipts tr
            ON tr.import_month = st.import_month
            AND tr.sale_date = st.sale_date
            AND tr.site_code = st.site_code
            AND tr.agent = st.agent
            AND tr.bon_nr = st.bon_nr
        WHERE st.import_month = $1
          AND {_RETAIL_TRANSACTION_EXCLUSIONS_SQL}
        GROUP BY
            st.import_month,
            st.sale_date,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent
        """

_REPORTING_MONTH_SQL_6 = f"""
        INSERT INTO reporting_agent_month (
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            total_sales,
            total_quantity,
            focus_quantity,
            receipt_count,
            receipt_2plus_count,
            receipt_1_count,
            receipt_2_count,
            receipt_3_count,
            receipt_4plus_count,
            working_days
        )
        SELECT
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            COALESCE(SUM(total_sales), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
            COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
            COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
            COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
            COALESCE(SUM(receipt_1_count), 0)::INT AS receipt_1_count,
            COALESCE(SUM(receipt_2_count), 0)::INT AS receipt_2_count,
            COALESCE(SUM(receipt_3_count), 0)::INT AS receipt_3_count,
            COALESCE(SUM(receipt_4plus_count), 0)::INT AS receipt_4plus_count,
            COUNT(*)::INT AS working_days
        FROM reporting_agent_day
        WHERE import_month = $1
        GROUP BY import_month, site_code, locatie, firma, regional, asm, agent
        """

_REPORTING_MONTH_SQL_7 = f"""
        INSERT INTO reporting_item_day (
            import_month,
            sale_date,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            item_code,
            item_name,
            total_sales,
            net_quantity,
            positive_quantity,
            return_quantity,
            receipt_count
        )
        SELECT
            st.import_month,
            st.sale_date,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            st.item_code,
            COALESCE(MAX(st.item_name), st.item_code) AS item_name,
            COALESCE(SUM(st.total_value), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(st.quantity), 0)::INT AS net_quantity,
            COALESCE(SUM(CASE WHEN st.quantity > 0 THEN st.quantity ELSE 0 END), 0)::INT AS positive_quantity,
            COALESCE(SUM(CASE WHEN st.quantity < 0 THEN st.quantity ELSE 0 END), 0)::INT AS return_quantity,
            COUNT(DISTINCT st.bon_nr)
                FILTER (WHERE NOT st.is_return AND st.quantity > 0)::INT
                AS receipt_count
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND {_RETAIL_TRANSACTION_EXCLUSIONS_SQL}
        GROUP BY
            st.import_month,
            st.sale_date,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            st.item_code
        """

_REPORTING_MONTH_SQL_8 = f"""
        INSERT INTO reporting_focus_item_month (
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            item_code,
            item_name,
            focus_subcategory,
            total_sales,
            total_quantity
        )
        SELECT
            st.import_month,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            st.item_code,
            COALESCE(MAX(fp.item_name), MAX(st.item_name), st.item_code) AS item_name,
            COALESCE(
                NULLIF(TRIM(MAX(st.subcategory)), ''),
                NULLIF(TRIM(MAX(st.category)), ''),
                'Necategorizat'
            ) AS focus_subcategory,
            COALESCE(SUM(st.total_value), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(st.quantity), 0)::INT AS total_quantity
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        JOIN focus_products fp ON fp.item_code = st.item_code
        WHERE st.import_month = $1
          AND {_RETAIL_TRANSACTION_EXCLUSIONS_SQL}
        GROUP BY
            st.import_month,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            st.item_code
        """

_REPORTING_MONTH_SQL_9 = """
        INSERT INTO reporting_item_month (
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            item_code,
            item_name,
            total_sales,
            net_quantity,
            positive_quantity,
            return_quantity,
            receipt_count
        )
        SELECT
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            item_code,
            MAX(item_name) AS item_name,
            COALESCE(SUM(total_sales), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(net_quantity), 0)::INT AS net_quantity,
            COALESCE(SUM(positive_quantity), 0)::INT AS positive_quantity,
            COALESCE(SUM(return_quantity), 0)::INT AS return_quantity,
            COALESCE(SUM(receipt_count), 0)::INT AS receipt_count
        FROM reporting_item_day
        WHERE import_month = $1
        GROUP BY
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            item_code
        """

_REPORTING_MONTH_SQL_10 = f"""
        INSERT INTO reporting_category_month (
            import_month,
            site_code,
            locatie,
            firma,
            regional,
            asm,
            agent,
            category,
            subcategory,
            brand_group,
            total_sales,
            total_quantity
        )
        SELECT
            st.import_month,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            COALESCE(NULLIF(TRIM(st.category), ''), 'Necategorizat') AS category,
            COALESCE(
                NULLIF(TRIM(st.subcategory), ''),
                NULLIF(TRIM(st.category), ''),
                'Necategorizat'
            ) AS subcategory,
            {_BRAND_GROUP_SQL} AS brand_group,
            COALESCE(SUM(st.total_value), 0)::NUMERIC(12, 2) AS total_sales,
            COALESCE(SUM(st.quantity), 0)::INT AS total_quantity
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND {_RETAIL_TRANSACTION_EXCLUSIONS_SQL}
        GROUP BY
            st.import_month,
            st.site_code,
            s.locatie,
            s.firma,
            s.regional,
            s.asm,
            st.agent,
            COALESCE(NULLIF(TRIM(st.category), ''), 'Necategorizat'),
            COALESCE(
                NULLIF(TRIM(st.subcategory), ''),
                NULLIF(TRIM(st.category), ''),
                'Necategorizat'
            ),
            {_BRAND_GROUP_SQL}
        """

async def rebuild_reporting_cartela_month(
    conn: asyncpg.Connection,
    import_month: str,
) -> None:
    await conn.execute(
        "DELETE FROM reporting_cartela_day WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        _REPORTING_MONTH_SQL_1,
        import_month,
    )
    await conn.execute("ANALYZE reporting_cartela_day")


async def rebuild_reporting_month(
    conn: asyncpg.Connection,
    import_month: str,
) -> None:
    await conn.execute("DROP TABLE IF EXISTS tmp_reporting_receipts")
    await conn.execute(
        "DELETE FROM reporting_category_month WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        "DELETE FROM reporting_focus_item_month WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        "DELETE FROM reporting_agent_month WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        "DELETE FROM reporting_item_day WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        "DELETE FROM reporting_item_month WHERE import_month = $1",
        import_month,
    )
    await conn.execute(
        "DELETE FROM reporting_agent_day WHERE import_month = $1",
        import_month,
    )
    await rebuild_reporting_cartela_month(conn, import_month)

    await conn.execute(
        _REPORTING_MONTH_SQL_2
    )
    await conn.execute(
        _REPORTING_MONTH_SQL_3,
        import_month,
    )
    await conn.execute(
        _REPORTING_MONTH_SQL_4
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_5,
        import_month,
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_6,
        import_month,
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_7,
        import_month,
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_8,
        import_month,
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_9,
        import_month,
    )

    await conn.execute(
        _REPORTING_MONTH_SQL_10,
        import_month,
    )

    await conn.execute("ANALYZE reporting_agent_day")
    await conn.execute("ANALYZE reporting_agent_month")
    await conn.execute("ANALYZE reporting_item_day")
    await conn.execute("ANALYZE reporting_item_month")
    await conn.execute("ANALYZE reporting_focus_item_month")
    await conn.execute("ANALYZE reporting_category_month")
    await refresh_premium_glass_indicators(conn)
    await conn.execute("DROP TABLE IF EXISTS tmp_reporting_receipts")
