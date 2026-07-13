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
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                WITH preferred_rows AS (
                    SELECT p.company_name, p.period, p.source_site_code,
                           p.source_location_name, p.category_code, p.amount,
                           p.data_kind,
                           COALESCE(l.site_code, p.source_site_code) AS site_code,
                           ROW_NUMBER() OVER (
                               PARTITION BY p.company_name, p.period,
                                            COALESCE(l.site_code, p.source_site_code),
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
                    WHERE p.period BETWEEN $1 AND $2
                      AND ($3::text IS NULL OR p.company_name = $3)
                )
                SELECT p.company_name, p.period, p.source_site_code,
                       p.source_location_name, p.category_code, p.amount,
                       p.data_kind, p.site_code
                FROM preferred_rows p
                WHERE p.preference_rank = 1
                  AND (
                      $4::text IS NULL
                      OR p.site_code = $4
                  )
                ORDER BY p.period, p.company_name, p.source_location_name, p.category_code
                """,
                start,
                end,
                company,
                site_code,
            )

    async def stores(self, company: str | None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                SELECT DISTINCT ON (
                    p.company_name,
                    COALESCE(l.site_code, p.source_site_code)
                )
                    p.company_name,
                    COALESCE(l.site_code, p.source_site_code) AS site_code,
                    p.source_location_name AS location
                FROM store_pnl_monthly p
                LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
                WHERE ($1::text IS NULL OR p.company_name = $1)
                ORDER BY p.company_name,
                         COALESCE(l.site_code, p.source_site_code),
                         p.period DESC,
                         CASE p.data_kind WHEN 'actual' THEN 0 ELSE 1 END,
                         p.imported_at DESC
                """,
                company,
            )

    async def annual_rows(
        self,
        company: str | None,
        site_code: str | None,
    ) -> list[asyncpg.Record]:
        async with self.pool.acquire() as connection:
            return await connection.fetch(
                """
                WITH preferred_rows AS (
                    SELECT p.company_name, p.period, p.source_site_code,
                           p.category_code, p.amount, p.data_kind,
                           COALESCE(l.site_code, p.source_site_code) AS site_code,
                           ROW_NUMBER() OVER (
                               PARTITION BY p.company_name, p.period,
                                            COALESCE(l.site_code, p.source_site_code),
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
                    WHERE ($1::text IS NULL OR p.company_name = $1)
                )
                SELECT EXTRACT(YEAR FROM p.period)::integer AS year,
                       p.category_code,
                       SUM(p.amount) AS amount,
                       BOOL_OR(p.data_kind = 'estimated') AS is_estimated
                FROM preferred_rows p
                WHERE p.preference_rank = 1
                  AND (
                      $2::text IS NULL
                      OR p.site_code = $2
                  )
                GROUP BY EXTRACT(YEAR FROM p.period), p.category_code
                ORDER BY year, p.category_code
                """,
                company,
                site_code,
            )
