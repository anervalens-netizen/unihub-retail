from __future__ import annotations

from datetime import date

import asyncpg


class StorePnlRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def available_months(self) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                SELECT period, bool_or(data_kind = 'actual') AS has_actual,
                       bool_or(data_kind = 'estimated') AS has_estimated
                FROM store_pnl_monthly
                GROUP BY period ORDER BY period DESC
                """
            )

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
                WITH preferred_rows AS (
                    SELECT p.company_name, p.period, p.source_site_code,
                           p.source_location_name, p.category_code, p.amount,
                           p.data_kind,
                           COALESCE(l.site_code, p.source_site_code) AS site_code,
                           COALESCE(s.regional, 'Nealocat') AS regional,
                           ROW_NUMBER() OVER (
                               PARTITION BY p.period,
                                            COALESCE(
                                                l.site_code,
                                                p.company_name || ':' || p.source_site_code
                                            ),
                                            p.category_code
                               ORDER BY CASE p.data_kind
                                   WHEN 'actual' THEN 0
                                   ELSE 1
                               END,
                               p.imported_at DESC,
                               p.id DESC
                           ) AS preference_rank
                    FROM store_pnl_monthly p
                    LEFT JOIN store_pnl_site_links l
                        USING (company_name, source_site_code)
                    LEFT JOIN stores s
                        ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                    WHERE p.period BETWEEN $1 AND $2
                      AND (
                          (
                              $4::text IS NULL
                              AND ($3::text IS NULL OR p.company_name = $3)
                          )
                          OR l.site_code = $4
                          OR (
                              l.site_code IS NULL
                              AND p.source_site_code = $4
                              AND p.company_name = COALESCE($5, $3)
                          )
                      )
                      AND ($6::text IS NULL OR COALESCE(s.regional, 'Nealocat') = $6)
                )
                SELECT p.company_name, p.period, p.source_site_code,
                       p.source_location_name, p.category_code, p.amount,
                       p.data_kind, p.site_code, p.regional
                FROM preferred_rows p
                WHERE p.preference_rank = 1
                ORDER BY p.period, p.company_name, p.source_location_name, p.category_code
                """,
                start,
                end,
                company,
                site_code,
                site_company,
                regional,
            )

    async def stores(self, company: str | None, regional: str | None = None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                SELECT DISTINCT ON (
                    CASE WHEN l.site_code IS NULL THEN p.company_name ELSE '' END,
                    COALESCE(l.site_code, p.source_site_code)
                )
                    p.company_name,
                    COALESCE(l.site_code, p.source_site_code) AS site_code,
                    p.source_location_name AS location,
                    COALESCE(s.regional, 'Nealocat') AS regional,
                    CASE WHEN l.site_code IS NULL THEN p.company_name END
                        AS scope_company
                FROM store_pnl_monthly p
                LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
                LEFT JOIN stores s ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                WHERE ($1::text IS NULL OR p.company_name = $1)
                  AND p.source_site_code <> '__FINANCE_UNALLOCATED__'
                  AND ($2::text IS NULL OR COALESCE(s.regional, 'Nealocat') = $2)
                ORDER BY CASE WHEN l.site_code IS NULL THEN p.company_name ELSE '' END,
                         COALESCE(l.site_code, p.source_site_code),
                         p.period DESC,
                         CASE p.data_kind WHEN 'actual' THEN 0 ELSE 1 END,
                         p.imported_at DESC
                """,
                company,
                regional,
            )

    async def regions(self, company: str | None) -> list[str]:
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT DISTINCT COALESCE(s.regional, 'Nealocat') AS regional
                FROM store_pnl_monthly p
                LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
                LEFT JOIN stores s ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                WHERE ($1::text IS NULL OR p.company_name = $1)
                  AND p.source_site_code <> '__FINANCE_UNALLOCATED__'
                ORDER BY regional
                """,
                company,
            )
        return [row["regional"] for row in rows]

    async def sales_rows(
        self,
        start: date,
        end: date,
        company: str | None,
        site_code: str | None,
        site_company: str | None,
        regional: str | None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                WITH sales_sources AS (
                    SELECT CASE WHEN h.firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
                           to_date(h.import_month || '-01', 'YYYY-MM-DD') AS period,
                           h.site_code, h.total_value AS amount, 1 AS priority
                    FROM historical_monthly_sales h
                    UNION ALL
                    SELECT CASE WHEN r.firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END,
                           to_date(r.import_month || '-01', 'YYYY-MM-DD'),
                           r.site_code, SUM(r.total_sales), 2
                    FROM reporting_agent_month r
                    GROUP BY r.firma, r.import_month, r.site_code
                ), preferred_sales AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY company_name, period, site_code ORDER BY priority DESC
                    ) AS preference_rank
                    FROM sales_sources
                )
                SELECT sales.period,
                       SUM(sales.amount) AS gross_amount,
                       SUM(sales.amount / 1.19) AS net_amount
                FROM preferred_sales sales
                JOIN stores s ON s.site_code = sales.site_code
                WHERE sales.preference_rank = 1
                  AND sales.period BETWEEN $1 AND $2
                  AND ($3::text IS NULL OR sales.company_name = $3)
                  AND ($4::text IS NULL OR sales.site_code = $4)
                  AND ($5::text IS NULL OR sales.company_name = $5)
                  AND ($6::text IS NULL OR s.regional = $6)
                GROUP BY sales.period ORDER BY sales.period
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
                WITH preferred_rows AS (
                    SELECT p.company_name, p.period, p.source_site_code,
                           p.category_code, p.amount, p.data_kind,
                           COALESCE(l.site_code, p.source_site_code) AS site_code,
                           COALESCE(s.regional, 'Nealocat') AS regional,
                           ROW_NUMBER() OVER (
                               PARTITION BY p.period,
                                            COALESCE(
                                                l.site_code,
                                                p.company_name || ':' || p.source_site_code
                                            ),
                                            p.category_code
                               ORDER BY CASE p.data_kind
                                   WHEN 'actual' THEN 0
                                   ELSE 1
                               END,
                               p.imported_at DESC,
                               p.id DESC
                           ) AS preference_rank
                    FROM store_pnl_monthly p
                    LEFT JOIN store_pnl_site_links l
                        USING (company_name, source_site_code)
                    LEFT JOIN stores s
                        ON s.site_code = COALESCE(l.site_code, p.source_site_code)
                    WHERE (
                        (
                            $2::text IS NULL
                            AND ($1::text IS NULL OR p.company_name = $1)
                        )
                        OR l.site_code = $2
                        OR (
                            l.site_code IS NULL
                            AND p.source_site_code = $2
                          AND p.company_name = COALESCE($3, $1)
                        )
                    )
                    AND ($4::text IS NULL OR COALESCE(s.regional, 'Nealocat') = $4)
                )
                SELECT EXTRACT(YEAR FROM p.period)::integer AS year,
                       p.category_code,
                       SUM(p.amount) AS amount,
                       COUNT(DISTINCT CASE
                           WHEN p.source_site_code <> '__FINANCE_UNALLOCATED__'
                           THEN COALESCE(
                               p.site_code,
                               p.company_name || ':' || p.source_site_code
                           )
                       END)::integer AS store_count,
                       BOOL_OR(p.data_kind = 'estimated') AS is_estimated
                FROM preferred_rows p
                WHERE p.preference_rank = 1
                GROUP BY EXTRACT(YEAR FROM p.period), p.category_code
                ORDER BY year, p.category_code
                """,
                company,
                site_code,
                site_company,
                regional,
            )
