from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import asyncpg


class TargetScenarioFinalizedError(Exception):
    pass


class TargetScenarioVersionConflict(Exception):
    pass


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
        expected_revision: int | None,
    ) -> int:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    scenario["target_month"],
                )
                existing = await conn.fetchrow(
                    """
                    SELECT id, status, revision
                    FROM target_scenarios
                    WHERE target_month = $1
                    FOR UPDATE
                    """,
                    scenario["target_month"],
                )
                if existing:
                    if existing["status"] != "draft":
                        raise TargetScenarioFinalizedError
                    if expected_revision != int(existing["revision"]):
                        raise TargetScenarioVersionConflict
                    scenario_id = int(existing["id"])
                    await conn.execute(
                        """
                        UPDATE target_scenarios
                        SET cohort_month = $2,
                            total_target = $3,
                            min_floor = $4,
                            previous_month_floor_pct = $5,
                            calculation_method = $6,
                            source_months = $7::jsonb,
                            warnings = $8::jsonb,
                            revision = revision + 1,
                            updated_at = now()
                        WHERE id = $1
                        """,
                        scenario_id,
                        scenario["cohort_month"],
                        scenario["total_target"],
                        scenario["min_floor"],
                        scenario["previous_month_floor_pct"],
                        scenario["calculation_method"],
                        json.dumps(scenario["source_months"]),
                        json.dumps(scenario["warnings"]),
                    )
                else:
                    if expected_revision is not None:
                        raise TargetScenarioVersionConflict
                    scenario_id = await conn.fetchval(
                        """
                        INSERT INTO target_scenarios (
                            target_month, cohort_month, total_target, min_floor,
                            previous_month_floor_pct, calculation_method,
                            source_months, warnings
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
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
                await conn.execute(
                    "DELETE FROM target_scenario_rows WHERE scenario_id = $1",
                    scenario_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO target_scenario_rows (
                        scenario_id, site_code, locatie, firma, regional, asm,
                        calculated_weight, floor_target, proposed_target,
                        is_floor_limited, history
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
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
                    ts.revision, ts.calculation_method, ts.source_months, ts.warnings, ts.created_at::text,
                    ts.updated_at::text, ts.finalized_at::text,
                    COUNT(tr.site_code) AS store_count,
                    COALESCE(SUM(tr.proposed_target), 0) AS proposed_total,
                    COALESCE(SUM(tr.final_target), 0) AS final_total,
                    COUNT(*) FILTER (WHERE tr.site_code IS NOT NULL AND tr.final_target IS NULL)::INT AS pending_final_count
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
                    ts.revision, ts.calculation_method, ts.source_months, ts.warnings,
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
        expected_revision: int,
    ) -> int:
        if not rows:
            return 0
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                scenario = await conn.fetchrow(
                    """
                    SELECT status, revision
                    FROM target_scenarios
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    scenario_id,
                )
                if not scenario or scenario["status"] != "draft":
                    return 0
                if int(scenario["revision"]) != expected_revision:
                    raise TargetScenarioVersionConflict
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
                    """
                    UPDATE target_scenarios
                    SET revision = revision + 1, updated_at = now()
                    WHERE id = $1
                    """,
                    scenario_id,
                )
        return int(existing or 0)

    async def finalize_scenario(self, scenario_id: int, expected_revision: int) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                scenario = await conn.fetchrow(
                    """
                    SELECT target_month, total_target, status, revision
                    FROM target_scenarios
                    WHERE id = $1
                    FOR UPDATE
                    """,
                    scenario_id,
                )
                if not scenario or scenario["status"] != "draft":
                    return False
                if int(scenario["revision"]) != expected_revision:
                    raise TargetScenarioVersionConflict
                final_total = await conn.fetchval(
                    "SELECT COALESCE(SUM(final_target), 0) FROM target_scenario_rows WHERE scenario_id = $1",
                    scenario_id,
                )
                pending_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM target_scenario_rows WHERE scenario_id = $1 AND final_target IS NULL",
                    scenario_id,
                )
                if int(pending_count or 0) > 0:
                    return False
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
                    SET status = 'finalized',
                        revision = revision + 1,
                        finalized_at = now(),
                        updated_at = now()
                    WHERE id = $1
                    """,
                    scenario_id,
                )
        return True

    async def get_store_detail(self, scenario_id: int, site_code: str) -> dict[str, Any] | None:
        async with self.pool.acquire() as conn:
            scenario_row = await conn.fetchrow(
                """
                SELECT
                    ts.id, ts.target_month, ts.cohort_month, ts.total_target,
                    tr.site_code, tr.locatie, tr.firma, tr.regional, tr.asm,
                    tr.proposed_target, tr.final_target, tr.history
                FROM target_scenarios ts
                JOIN target_scenario_rows tr ON tr.scenario_id = ts.id
                WHERE ts.id = $1 AND tr.site_code = $2
                """,
                scenario_id,
                site_code,
            )
            if not scenario_row:
                return None

            history = await conn.fetch(
                """
                WITH month_axis AS (
                    SELECT to_char(
                        generate_series(
                            to_date($2 || '-01', 'YYYY-MM-DD') - INTERVAL '15 months',
                            to_date($2 || '-01', 'YYYY-MM-DD'),
                            INTERVAL '1 month'
                        ),
                        'YYYY-MM'
                    ) AS import_month
                ),
                monthly_sales AS (
                    SELECT
                        import_month,
                        site_code,
                        SUM(total_sales) AS total_sales,
                        SUM(total_quantity) AS total_quantity,
                        SUM(focus_quantity) AS focus_quantity,
                        SUM(receipt_count) AS receipt_count,
                        SUM(receipt_2plus_count) AS receipt_2plus_count,
                        COUNT(DISTINCT agent) FILTER (WHERE agent IS NOT NULL AND agent <> '-') AS active_agents,
                        MAX(working_days) AS working_days
                    FROM reporting_agent_month
                    WHERE site_code = $1
                      AND import_month IN (SELECT import_month FROM month_axis)
                    GROUP BY import_month, site_code
                ),
                cartele AS (
                    SELECT
                        import_month,
                        COALESCE(SUM(quantity), 0)::INT AS cartele_qty
                    FROM sales_transactions
                    WHERE site_code = $1
                      AND import_month IN (SELECT import_month FROM month_axis)
                      AND is_cartela = true
                    GROUP BY import_month
                ),
                daily_days AS (
                    SELECT
                        import_month,
                        COUNT(DISTINCT sale_date)::INT AS working_days
                    FROM reporting_agent_day
                    WHERE site_code = $1
                      AND import_month IN (SELECT import_month FROM month_axis)
                    GROUP BY import_month
                )
                SELECT
                    ma.import_month,
                    COALESCE(ms.total_sales, 0) AS total_sales,
                    COALESCE(ms.total_quantity, 0) AS total_quantity,
                    COALESCE(ms.focus_quantity, 0) AS focus_quantity,
                    COALESCE(ms.receipt_count, 0) AS receipt_count,
                    COALESCE(ms.receipt_2plus_count, 0) AS receipt_2plus_count,
                    COALESCE(ms.active_agents, 0)::INT AS active_agents,
                    COALESCE(dd.working_days, ms.working_days, 0)::INT AS working_days,
                    COALESCE(c.cartele_qty, 0)::INT AS cartele_qty,
                    COALESCE(st.target_value, 0) AS target_value
                FROM month_axis ma
                LEFT JOIN monthly_sales ms ON ms.import_month = ma.import_month
                LEFT JOIN cartele c ON c.import_month = ma.import_month
                LEFT JOIN daily_days dd ON dd.import_month = ma.import_month
                LEFT JOIN store_targets st ON st.import_month = ma.import_month AND st.site_code = $1
                ORDER BY ma.import_month
                """,
                site_code,
                scenario_row["cohort_month"],
            )

            agents = await conn.fetch(
                """
                WITH current_agents AS (
                    SELECT
                        agent,
                        SUM(total_sales) AS total_sales,
                        SUM(total_quantity) AS total_quantity,
                        SUM(focus_quantity) AS focus_quantity,
                        SUM(receipt_count) AS receipt_count,
                        SUM(receipt_2plus_count) AS receipt_2plus_count
                    FROM reporting_agent_month
                    WHERE import_month = $2
                      AND site_code = $1
                      AND agent IS NOT NULL
                      AND agent <> '-'
                    GROUP BY agent
                ),
                agent_history AS (
                    SELECT
                        agent,
                        COUNT(DISTINCT import_month)::INT AS active_months_16,
                        SUM(total_sales) AS sales_16m
                    FROM reporting_agent_month
                    WHERE site_code = $1
                      AND import_month BETWEEN to_char(to_date($2 || '-01', 'YYYY-MM-DD') - INTERVAL '15 months', 'YYYY-MM')
                                           AND $2
                      AND agent IS NOT NULL
                      AND agent <> '-'
                    GROUP BY agent
                ),
                store_total AS (
                    SELECT COALESCE(SUM(total_sales), 0) AS total_sales
                    FROM current_agents
                )
                SELECT
                    ca.agent,
                    ca.total_sales,
                    ca.total_quantity,
                    ca.focus_quantity,
                    ca.receipt_count,
                    ca.receipt_2plus_count,
                    COALESCE(ah.active_months_16, 0)::INT AS active_months_16,
                    COALESCE(ah.sales_16m, 0) AS sales_16m,
                    CASE WHEN st.total_sales > 0 THEN ca.total_sales * 100.0 / st.total_sales ELSE 0 END AS sales_share_pct
                FROM current_agents ca
                CROSS JOIN store_total st
                LEFT JOIN agent_history ah ON ah.agent = ca.agent
                ORDER BY ca.total_sales DESC, ca.agent
                """,
                site_code,
                scenario_row["cohort_month"],
            )

            return {
                "scenario": scenario_row,
                "history": history,
                "agents": agents,
            }
