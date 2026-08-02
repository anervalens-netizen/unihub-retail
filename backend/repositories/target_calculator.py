from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import asyncpg

from retail_filters import distribution_location_clause


class TargetScenarioFinalizedError(Exception):
    pass


class TargetScenarioVersionConflict(Exception):
    pass


class TargetScenarioAlgorithmMismatch(Exception):
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

    async def get_active_cohort(self, cohort_month: str, target_month: str | None = None) -> list[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                f"""
                SELECT
                    ram.site_code,
                    s.locatie,
                    s.firma,
                    s.regional,
                    s.asm
                FROM reporting_agent_month ram
                JOIN stores s ON s.site_code = ram.site_code
                WHERE ram.import_month = $1
                  AND s.is_active = TRUE
                  AND {distribution_location_clause("s")}
                  AND NOT EXISTS (
                      SELECT 1
                      FROM target_calculator_store_exclusions tcse
                      WHERE tcse.site_code = ram.site_code
                        AND ($2::TEXT IS NULL OR tcse.effective_from_month <= $2)
                  )
                GROUP BY ram.site_code, s.locatie, s.firma, s.regional, s.asm
                ORDER BY s.regional, s.locatie, ram.site_code
                """,
                cohort_month,
                target_month,
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
                ),
                historical_sales AS (
                    SELECT hms.import_month, hms.site_code, SUM(hms.total_value) AS realized
                    FROM historical_monthly_sales hms
                    WHERE hms.import_month = ANY($1::text[])
                      AND hms.site_code = ANY($2::text[])
                      AND NOT EXISTS (
                          SELECT 1
                          FROM sales s
                          WHERE s.import_month = hms.import_month
                            AND s.site_code = hms.site_code
                      )
                    GROUP BY hms.import_month, hms.site_code
                ),
                combined_sales AS (
                    SELECT import_month, site_code, realized FROM sales
                    UNION ALL
                    SELECT import_month, site_code, realized FROM historical_sales
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
                LEFT JOIN combined_sales s
                  ON s.import_month = m.import_month AND s.site_code = st.site_code
                ORDER BY m.import_month, st.site_code
                """,
                months,
                site_codes,
            )

    async def get_profitability_inputs(
        self,
        *,
        site_codes: list[str],
        target_month: str,
    ) -> dict[str, Any]:
        if not site_codes:
            return {
                "pnl_months": [],
                "pnl_rows": [],
                "forecast_run": None,
                "forecast_rows": [],
            }

        target_date = date.fromisoformat(f"{target_month}-01")
        required_categories = ["v11", "c11", "c4", "c5", "c6"]
        expected_pairs = len(site_codes) * len(required_categories)
        async with self.pool.acquire() as conn:
            pnl_month_records = await conn.fetch(
                """
                WITH resolved AS (
                    SELECT
                        COALESCE(link.site_code, pnl.source_site_code) AS site_code,
                        pnl.period,
                        pnl.category_code
                    FROM store_pnl_monthly pnl
                    LEFT JOIN store_pnl_site_links link
                      ON link.company_name = pnl.company_name
                     AND link.source_site_code = pnl.source_site_code
                    WHERE pnl.data_kind = 'actual'
                      AND pnl.period < $1
                      AND pnl.category_code = ANY($2::TEXT[])
                      AND COALESCE(link.site_code, pnl.source_site_code) = ANY($3::TEXT[])
                )
                SELECT period
                FROM resolved
                GROUP BY period
                HAVING COUNT(DISTINCT (site_code, category_code)) = $4
                ORDER BY period DESC
                LIMIT 3
                """,
                target_date,
                required_categories,
                site_codes,
                expected_pairs,
            )
            pnl_months = sorted(record["period"] for record in pnl_month_records)
            pnl_rows: list[asyncpg.Record] = []
            if len(pnl_months) == 3:
                pnl_rows = await conn.fetch(
                    """
                    SELECT
                        COALESCE(link.site_code, pnl.source_site_code) AS site_code,
                        pnl.category_code,
                        SUM(pnl.amount)::NUMERIC(16, 2) AS amount
                    FROM store_pnl_monthly pnl
                    LEFT JOIN store_pnl_site_links link
                      ON link.company_name = pnl.company_name
                     AND link.source_site_code = pnl.source_site_code
                    WHERE pnl.data_kind = 'actual'
                      AND pnl.period = ANY($1::DATE[])
                      AND pnl.category_code = ANY($2::TEXT[])
                      AND COALESCE(link.site_code, pnl.source_site_code) = ANY($3::TEXT[])
                    GROUP BY COALESCE(link.site_code, pnl.source_site_code), pnl.category_code
                    ORDER BY site_code, pnl.category_code
                    """,
                    pnl_months,
                    required_categories,
                    site_codes,
                )

            forecast_run = await conn.fetchrow(
                """
                SELECT id, forecast_month, source_month, model_name, model_mode,
                       variant, generated_at::TEXT, metadata
                FROM ai_forecast_runs
                WHERE status = 'completed'
                  AND metric = 'sales_value'
                  AND horizon = 'current_month'
                  AND forecast_month = $1
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                target_month,
            )
            forecast_rows: list[asyncpg.Record] = []
            if forecast_run:
                forecast_rows = await conn.fetch(
                    """
                    SELECT site_code, forecast_sales
                    FROM ai_forecast_store_month
                    WHERE run_id = $1
                      AND site_code = ANY($2::TEXT[])
                    ORDER BY site_code
                    """,
                    forecast_run["id"],
                    site_codes,
                )

        return {
            "pnl_months": [period.strftime("%Y-%m") for period in pnl_months],
            "pnl_rows": pnl_rows,
            "forecast_run": forecast_run,
            "forecast_rows": forecast_rows,
        }

    async def get_effective_target_rule_set(self, target_month: str) -> asyncpg.Record | None:
        """Return the single effective-dated Target rule-set for a calculation month."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT id, version, effective_from_month, effective_to_month, rules, rules_sha256
                FROM target_calculator_rule_sets
                WHERE effective_from_month <= $1
                  AND (effective_to_month IS NULL OR effective_to_month > $1)
                ORDER BY effective_from_month DESC, version DESC
                LIMIT 1
                """,
                target_month,
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
                    SELECT id, status, revision, calculation_method
                    FROM target_scenarios
                    WHERE target_month = $1
                    FOR UPDATE
                    """,
                    scenario["target_month"],
                )
                if existing:
                    if existing["status"] != "draft":
                        raise TargetScenarioFinalizedError
                    if existing.get("calculation_method", scenario["calculation_method"]) != scenario["calculation_method"]:
                        raise TargetScenarioAlgorithmMismatch
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
                            calculation_params = $9::jsonb,
                            rule_set_id = $10,
                            rule_set_hash = $11,
                            rule_set_snapshot = $12::jsonb,
                            calculation_input_sha256 = $13,
                            profitability_input_sha256 = $14,
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
                        json.dumps(scenario.get("calculation_params", {})),
                        scenario.get("rule_set_id"),
                        scenario.get("rule_set_hash"),
                        json.dumps(scenario.get("rule_set_snapshot")) if scenario.get("rule_set_snapshot") else None,
                        scenario.get("calculation_input_sha256"),
                        scenario.get("profitability_input_sha256"),
                    )
                else:
                    if expected_revision is not None:
                        raise TargetScenarioVersionConflict
                    scenario_id = await conn.fetchval(
                        """
                        INSERT INTO target_scenarios (
                            target_month, cohort_month, total_target, min_floor,
                            previous_month_floor_pct, calculation_method,
                            source_months, warnings, calculation_params,
                            rule_set_id, rule_set_hash, rule_set_snapshot,
                            calculation_input_sha256, profitability_input_sha256
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9::jsonb, $10, $11, $12::jsonb, $13, $14)
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
                        json.dumps(scenario.get("calculation_params", {})),
                        scenario.get("rule_set_id"),
                        scenario.get("rule_set_hash"),
                        json.dumps(scenario.get("rule_set_snapshot")) if scenario.get("rule_set_snapshot") else None,
                        scenario.get("calculation_input_sha256"),
                        scenario.get("profitability_input_sha256"),
                    )
                await conn.execute(
                    "DELETE FROM target_scenario_rows WHERE scenario_id = $1",
                    scenario_id,
                )
                await conn.executemany(
                    """
                    INSERT INTO target_scenario_rows (
                        scenario_id, site_code, locatie, firma, regional, asm,
                        calculated_weight, floor_target, cap_target, proposed_target,
                        is_floor_limited, is_cap_limited, history, calculation_details, profitability_snapshot
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb, $15::jsonb)
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
                            row.get("cap_target"),
                            row["proposed_target"],
                            row["is_floor_limited"],
                            row.get("is_cap_limited", False),
                            json.dumps(row["history"]),
                            json.dumps(row.get("calculation_details", {})),
                            json.dumps(row.get("profitability_snapshot")) if row.get("profitability_snapshot") else None,
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
                    ts.revision, ts.calculation_method, ts.source_months, ts.warnings,
                    ts.calculation_params, ts.rule_set_id, ts.rule_set_hash, ts.rule_set_snapshot,
                    ts.calculation_input_sha256, ts.profitability_input_sha256, ts.created_at::text,
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
                    ts.calculation_params, ts.rule_set_id, ts.rule_set_hash, ts.rule_set_snapshot,
                    ts.calculation_input_sha256, ts.profitability_input_sha256,
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
                    floor_target, cap_target, proposed_target, final_target, is_floor_limited, is_cap_limited,
                    manager_override_target, manager_override_reason, manager_override_actor,
                    manager_override_at::text, manager_override_revision, profitability_snapshot,
                    history, calculation_details, note, updated_at::text
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
        actor: str | None = None,
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
                if int(existing or 0) != len(rows):
                    return int(existing or 0)
                await conn.executemany(
                    """
                    UPDATE target_scenario_rows
                    SET final_target = $3,
                        note = $4,
                        manager_override_target = CASE
                            WHEN $3 IS DISTINCT FROM proposed_target THEN $3
                            ELSE NULL
                        END,
                        manager_override_reason = CASE
                            WHEN $3 IS DISTINCT FROM proposed_target THEN $4
                            ELSE NULL
                        END,
                        manager_override_actor = CASE
                            WHEN $3 IS DISTINCT FROM proposed_target THEN $5
                            ELSE NULL
                        END,
                        manager_override_at = CASE
                            WHEN $3 IS DISTINCT FROM proposed_target THEN now()
                            ELSE NULL
                        END,
                        manager_override_revision = $6,
                        updated_at = now()
                    WHERE scenario_id = $1 AND site_code = $2
                    """,
                    [
                        (
                            scenario_id,
                            row["site_code"],
                            row["final_target"],
                            row.get("override_reason") or row.get("note"),
                            actor,
                            expected_revision + 1,
                        )
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
                        COALESCE(SUM(total_quantity), 0)::INT AS cartele_qty
                    FROM reporting_cartela_day
                    WHERE site_code = $1
                      AND import_month IN (SELECT import_month FROM month_axis)
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
