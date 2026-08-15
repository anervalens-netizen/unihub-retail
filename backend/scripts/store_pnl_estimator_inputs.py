"""Database input snapshot for the P&L estimator."""
from __future__ import annotations

from datetime import date

import asyncpg

from services.fiscal_rules import gross_to_net, legacy_gross_to_net


async def load_inputs(
    connection: asyncpg.Connection,
    *,
    input_cutoff: date | None = None,
):
    """Read raw estimator inputs without selecting a VAT interpretation.

    Shadow generations invoke this inside repeatable-read.  Gross sales remain
    raw here so legacy-v2 and effective-v3 are comparable from one snapshot.
    """
    cutoff = input_cutoff or date.max
    actual = await connection.fetch(
        """
        SELECT p.company_name, p.period,
               MIN(p.source_site_code) AS source_site_code,
               MIN(p.source_location_name) AS source_location_name,
               p.category_code, MAX(p.category_name) AS category_name,
               SUM(p.amount) AS amount,
               COALESCE(l.site_code, p.source_site_code) AS site_code
        FROM store_pnl_monthly p
        LEFT JOIN store_pnl_site_links l USING (company_name, source_site_code)
        WHERE p.data_kind = 'actual'
          AND p.source_site_code <> '__FINANCE_UNALLOCATED__'
          AND p.period <= $1
        GROUP BY p.company_name, p.period,
                 COALESCE(l.site_code, p.source_site_code), p.category_code
        """,
        cutoff,
    )
    gross_sales = await connection.fetch(
        """
        WITH sources AS (
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
                   to_date(import_month || '-01', 'YYYY-MM-DD') AS period,
                   site_code, total_value::numeric AS gross_amount, 1 AS priority
            FROM historical_monthly_sales
            UNION ALL
            SELECT CASE WHEN firma ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END,
                   to_date(import_month || '-01', 'YYYY-MM-DD'), site_code,
                   SUM(total_sales)::numeric, 2
            FROM reporting_agent_month GROUP BY firma, import_month, site_code
        ), preferred AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY company_name, period, site_code ORDER BY priority DESC
            ) AS preference_rank FROM sources
        )
        SELECT company_name, period, site_code, gross_amount
        FROM preferred
        WHERE preference_rank = 1
          AND period <= $1
        """,
        cutoff,
    )
    salaries = await connection.fetch(
        """
        SELECT CASE WHEN company_name ILIKE 'mobicell%' THEN 'Mobicell' ELSE 'Mobiup' END AS company_name,
               make_date(year, month, 1) AS period, site_code, SUM(total_salary)::numeric AS amount
        FROM salary_records
        WHERE site_code IS NOT NULL
          AND make_date(year, month, 1) <= $1
        GROUP BY company_name, year, month, site_code
        """,
        cutoff,
    )
    stores = await connection.fetch("SELECT site_code, locatie, firma FROM stores")
    return actual, gross_sales, salaries, stores


def normalize_sales(gross_sales, *, effective_vat: bool = False):
    """Normalize a previously captured gross-sales input snapshot."""
    net_converter = gross_to_net if effective_vat else legacy_gross_to_net
    return [
        {
            "company_name": row["company_name"],
            "period": row["period"],
            "site_code": row["site_code"],
            "amount": net_converter(row["gross_amount"], row["period"]),
        }
        for row in gross_sales
    ]
