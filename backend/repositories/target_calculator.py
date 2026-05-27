from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import asyncpg


class TargetCalculatorRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_latest_sales_month(self, before_month: str | None = None) -> str | None:
        condition = "WHERE import_month < $1" if before_month else ""
        params = (before_month,) if before_month else ()
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                f"SELECT MAX(import_month) FROM reporting_agent_month {condition}",
                *params,
            )

    async def get_target_total(self, month: str) -> Decimal:
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COALESCE(SUM(target_value), 0) FROM store_targets WHERE import_month = $1",
                month,
            )
        return Decimal(value or 0)

    async def get_active_cohort(self, cohort_month: str) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT
                    ram.site_code,
                    s.locatie,
                    s.firma,
                    s.regional,
                    s.asm
                FROM reporting_agent_month ram
                JOIN stores s ON s.site_code = ram.site_code
                WHERE ram.import_month = $1
                  AND s.locatie NOT ILIKE 'TR %'
                GROUP BY ram.site_code, s.locatie, s.firma, s.regional, s.asm
                ORDER BY s.regional, s.locatie, ram.site_code
                """,
                cohort_month,
            )

    async def get_source_metrics(
        self,
        site_codes: list[str],
        months: list[str],
    ) -> list[asyncpg.Record]:
        if not site_codes or not months:
            return []
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH requested_months AS (
                    SELECT unnest($1::text[]) AS import_month
                ),
                requested_stores AS (
                    SELECT unnest($2::text[]) AS site_code
                ),
                sales AS (
                    SELECT import_month, site_code, SUM(total_sales) AS realized
                    FROM reporting_agent_month
                    WHERE import_month = ANY($1::text[])
                      AND site_code = ANY($2::text[])
                    GROUP BY import_month, site_code
                )
                SELECT
                    m.import_month,
                    st.site_code,
                    COALESCE(t.target_value, 0) AS target,
                    COALESCE(s.realized, 0) AS realized
                FROM requested_months m
                CROSS JOIN requested_stores st
                LEFT JOIN store_targets t
                  ON t.import_month = m.import_month AND t.site_code = st.site_code
                LEFT JOIN sales s
                  ON s.import_month = m.import_month AND s.site_code = st.site_code
                ORDER BY m.import_month, st.site_code
                """,
                months,
                site_codes,
            )

    async def save_draft_scenario(
        self,
        scenario: dict[str, Any],
        rows: list[dict[str, Any]],
    ) -> int | None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                scenario_id = await conn.fetchval(
                    """
                    INSERT INTO target_scenarios (
                        target_month, cohort_month, total_target, min_floor,
                        previous_month_floor_pct, calculation_method, source_months, warnings
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
                    ON CONFLICT (target_month) DO UPDATE
                    SET cohort_month = EXCLUDED.cohort_month,
                        total_target = EXCLUDED.total_target,
                        min_floor = EXCLUDED.min_floor,
                        previous_month_floor_pct = EXCLUDED.previous_month_floor_pct,
                        calculation_method = EXCLUDED.calculation_method,
                        source_months = EXCLUDED.source_months,
                        warnings = EXCLUDED.warnings,
                        updated_at = now()
                    WHERE target_scenarios.status = 'draft'
                    RETURNING id
                    """,
                    scenario["target_month"],
                    scenario["cohort_month"],
                    scenario["total_target"],
                    scenario["min_floor"],
                    scenario["previous_month_floor_pct"],
                    scenario["calculation_method"],
                    json.dumps(scenario["source_months"]),
                    json.dumps(scenario["warnings"]),
                )
                if scenario_id is None:
                    return None
                await conn.execute(
                    "DELETE FROM target_scenario_rows WHERE scenario_id = $1",
                    scenario_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO target_scenario_rows (
                        scenario_id, site_code, locatie, firma, regional, asm,
                        calculated_weight, floor_target, proposed_target, final_target,
                        is_floor_limited, history
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $9, $10, $11::jsonb)
                    """,
                    [
                        (
                            scenario_id,
                            row["site_code"],
                            row["locatie"],
                            row["firma"],
                            row["regional"],
                            row["asm"],
                            row["calculated_weight"],
                            row["floor_target"],
                            row["proposed_target"],
                            row["is_floor_limited"],
                            json.dumps(row["history"]),
                        )
                        for row in rows
                    ],
                )
        return int(scenario_id)

    async def list_scenarios(self, limit: int = 20) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT
                    ts.id, ts.target_month, ts.cohort_month, ts.total_target,
                    ts.min_floor, ts.previous_month_floor_pct, ts.status,
                    ts.calculation_method, ts.source_months, ts.warnings, ts.created_at::text,
                    ts.updated_at::text, ts.finalized_at::text,
                    COUNT(tr.site_code) AS store_count,
                    COALESCE(SUM(tr.proposed_target), 0) AS proposed_total,
                    COALESCE(SUM(tr.final_target), 0) AS final_total
                FROM target_scenarios ts
                LEFT JOIN target_scenario_rows tr ON tr.scenario_id = ts.id
                GROUP BY ts.id
                ORDER BY ts.created_at DESC
                LIMIT $1
                """,
                limit,
            )

    async def get_scenario(self, scenario_id: int) -> asyncpg.Record | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT
                    ts.id, ts.target_month, ts.cohort_month, ts.total_target,
                    ts.min_floor, ts.previous_month_floor_pct, ts.status,
                    ts.calculation_method, ts.source_months, ts.warnings,
                    ts.created_at::text, ts.updated_at::text, ts.finalized_at::text
                FROM target_scenarios ts
                WHERE ts.id = $1
                """,
                scenario_id,
            )

    async def get_scenario_rows(self, scenario_id: int) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT
                    site_code, locatie, firma, regional, asm, calculated_weight,
                    floor_target, proposed_target, final_target, is_floor_limited,
                    history, note, updated_at::text
                FROM target_scenario_rows
                WHERE scenario_id = $1
                ORDER BY regional, locatie, site_code
                """,
                scenario_id,
            )

    async def update_final_targets(
        self,
        scenario_id: int,
        rows: list[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                status = await conn.fetchval(
                    "SELECT status FROM target_scenarios WHERE id = $1 FOR UPDATE",
                    scenario_id,
                )
                if status != "draft":
                    return 0
                existing = await conn.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM target_scenario_rows
                    WHERE scenario_id = $1 AND site_code = ANY($2::text[])
                    """,
                    scenario_id,
                    [row["site_code"] for row in rows],
                )
                await conn.executemany(
                    """
                    UPDATE target_scenario_rows
                    SET final_target = $3, note = $4, updated_at = now()
                    WHERE scenario_id = $1 AND site_code = $2
                    """,
                    [
                        (scenario_id, row["site_code"], row["final_target"], row.get("note"))
                        for row in rows
                    ],
                )
                await conn.execute(
                    "UPDATE target_scenarios SET updated_at = now() WHERE id = $1",
                    scenario_id,
                )
        return int(existing or 0)

    async def finalize_scenario(self, scenario_id: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                scenario = await conn.fetchrow(
                    "SELECT target_month, total_target, status FROM target_scenarios WHERE id = $1 FOR UPDATE",
                    scenario_id,
                )
                if not scenario or scenario["status"] != "draft":
                    return False
                final_total = await conn.fetchval(
                    "SELECT COALESCE(SUM(final_target), 0) FROM target_scenario_rows WHERE scenario_id = $1",
                    scenario_id,
                )
                if Decimal(final_total or 0).quantize(Decimal("0.01")) != Decimal(
                    scenario["total_target"]
                ).quantize(Decimal("0.01")):
                    return False
                await conn.execute(
                    """
                    DELETE FROM store_targets
                    WHERE import_month = $2
                      AND site_code NOT IN (
                          SELECT site_code
                          FROM target_scenario_rows
                          WHERE scenario_id = $1
                      )
                    """,
                    scenario_id,
                    scenario["target_month"],
                )
                await conn.execute(
                    """
                    INSERT INTO store_targets (import_month, site_code, target_value, source_file)
                    SELECT $2, site_code, final_target, $3
                    FROM target_scenario_rows
                    WHERE scenario_id = $1
                    ON CONFLICT (import_month, site_code) DO UPDATE
                    SET target_value = EXCLUDED.target_value,
                        source_file = EXCLUDED.source_file,
                        created_at = now()
                    """,
                    scenario_id,
                    scenario["target_month"],
                    f"target-calculator:{scenario_id}",
                )
                await conn.execute(
                    """
                    UPDATE target_scenarios
                    SET status = 'finalized', finalized_at = now(), updated_at = now()
                    WHERE id = $1
                    """,
                    scenario_id,
                )
        return True
