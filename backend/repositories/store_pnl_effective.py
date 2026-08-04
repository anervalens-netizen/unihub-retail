from __future__ import annotations

from datetime import date

import asyncpg

from repositories.store_pnl import StorePnlRepository


class StorePnlEffectiveRepository(StorePnlRepository):
    """P&L reader that resolves actual-vs-estimated per canonical store-month.

    Finance is authoritative only for the store-months present in its source.
    Missing stores in the same company-month may therefore continue to use the
    estimated reconstruction without being hidden by another store's actual row.
    """

    async def rows(
        self,
        start: date,
        end: date,
        company: str | None,
        site_code: str | None = None,
        site_company: str | None = None,
        regional: str | None = None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                WITH normalized AS (
                    SELECT
                        p.company_name,
                        p.period,
                        p.source_site_code,
                        p.source_location_name,
                        p.category_code,
                        p.amount,
                        p.data_kind,
                        COALESCE(l.site_code, p.source_site_code) AS site_code,
                        COALESCE(s.regional, 'Nealocat') AS regional
                    FROM store_pnl_monthly p
                    LEFT JOIN store_pnl_site_links l
                      ON l.company_name = p.company_name
                     AND l.source_site_code = p.source_site_code
                    LEFT JOIN stores s
                      ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                    WHERE p.period BETWEEN $1 AND $2
                ),
                preferred_kind AS (
                    SELECT
                        company_name,
                        period,
                        site_code,
                        CASE
                            WHEN BOOL_OR(data_kind = 'actual') THEN 'actual'
                            ELSE 'estimated'
                        END AS data_kind
                    FROM normalized
                    GROUP BY company_name, period, site_code
                ),
                preferred_rows AS (
                    SELECT n.*
                    FROM normalized n
                    JOIN preferred_kind k
                      ON k.company_name = n.company_name
                     AND k.period = n.period
                     AND k.site_code = n.site_code
                     AND k.data_kind = n.data_kind
                    WHERE (
                        (
                            $4::text IS NULL
                            AND ($3::text IS NULL OR n.company_name = $3)
                        )
                        OR (
                            n.site_code = $4
                            AND (
                                COALESCE($5::text, $3::text) IS NULL
                                OR n.company_name = COALESCE($5::text, $3::text)
                            )
                        )
                    )
                      AND ($6::text IS NULL OR n.regional = $6)
                )
                SELECT
                    company_name,
                    period,
                    source_site_code,
                    source_location_name,
                    category_code,
                    amount,
                    data_kind,
                    site_code,
                    regional
                FROM preferred_rows
                ORDER BY period, company_name, source_location_name, category_code
                """,
                start,
                end,
                company,
                site_code,
                site_company,
                regional,
            )

    async def annual_rows(
        self,
        company: str | None,
        site_code: str | None,
        site_company: str | None = None,
        regional: str | None = None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                WITH normalized AS (
                    SELECT
                        p.company_name,
                        p.period,
                        p.source_site_code,
                        p.category_code,
                        p.amount,
                        p.data_kind,
                        COALESCE(l.site_code, p.source_site_code) AS site_code,
                        COALESCE(s.regional, 'Nealocat') AS regional
                    FROM store_pnl_monthly p
                    LEFT JOIN store_pnl_site_links l
                      ON l.company_name = p.company_name
                     AND l.source_site_code = p.source_site_code
                    LEFT JOIN stores s
                      ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                ),
                preferred_kind AS (
                    SELECT
                        company_name,
                        period,
                        site_code,
                        CASE
                            WHEN BOOL_OR(data_kind = 'actual') THEN 'actual'
                            ELSE 'estimated'
                        END AS data_kind
                    FROM normalized
                    GROUP BY company_name, period, site_code
                ),
                preferred_rows AS (
                    SELECT n.*
                    FROM normalized n
                    JOIN preferred_kind k
                      ON k.company_name = n.company_name
                     AND k.period = n.period
                     AND k.site_code = n.site_code
                     AND k.data_kind = n.data_kind
                    WHERE (
                        (
                            $2::text IS NULL
                            AND ($1::text IS NULL OR n.company_name = $1)
                        )
                        OR (
                            n.site_code = $2
                            AND (
                                COALESCE($3::text, $1::text) IS NULL
                                OR n.company_name = COALESCE($3::text, $1::text)
                            )
                        )
                    )
                      AND ($4::text IS NULL OR n.regional = $4)
                )
                SELECT
                    EXTRACT(YEAR FROM period)::integer AS year,
                    category_code,
                    SUM(amount) AS amount,
                    COUNT(DISTINCT CASE
                        WHEN source_site_code <> '__FINANCE_UNALLOCATED__'
                        THEN COALESCE(site_code, company_name || ':' || source_site_code)
                    END)::integer AS store_count,
                    COUNT(DISTINCT period)::integer AS month_count,
                    BOOL_OR(data_kind = 'estimated') AS is_estimated
                FROM preferred_rows
                GROUP BY EXTRACT(YEAR FROM period), category_code
                ORDER BY year, category_code
                """,
                company,
                site_code,
                site_company,
                regional,
            )
