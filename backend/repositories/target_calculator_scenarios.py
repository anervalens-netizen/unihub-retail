from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import asyncpg


class TargetScenarioFinalizedError(Exception):
    pass


class TargetScenarioVersionConflict(Exception):
    pass


class TargetScenarioAlgorithmMismatch(Exception):
    pass


class TargetCalculatorScenariosRepositoryMixin:
    pool: asyncpg.Pool

    async def _update_existing_draft(
        self,
        conn: asyncpg.Connection,
        *,
        existing: asyncpg.Record,
        scenario: dict[str, Any],
        expected_revision: int | None,
    ) -> int:
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
        return scenario_id

    async def _insert_draft(
        self,
        conn: asyncpg.Connection,
        *,
        scenario: dict[str, Any],
        expected_revision: int | None,
    ) -> int:
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
        return int(scenario_id)

    async def _replace_scenario_rows(
        self,
        conn: asyncpg.Connection,
        *,
        scenario_id: int,
        rows: list[dict[str, Any]],
    ) -> None:
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
                    scenario_id = await self._update_existing_draft(
                        conn,
                        existing=existing,
                        scenario=scenario,
                        expected_revision=expected_revision,
                    )
                else:
                    scenario_id = await self._insert_draft(
                        conn,
                        scenario=scenario,
                        expected_revision=expected_revision,
                    )
                await self._replace_scenario_rows(conn, scenario_id=scenario_id, rows=rows)
        return scenario_id

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
