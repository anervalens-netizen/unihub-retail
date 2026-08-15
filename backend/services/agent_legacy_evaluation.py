"""Legacy V1 agent-evaluation query and response projection."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from business_rules import AGENT_LIFECYCLE_BASELINE_MONTH
from schemas.agents import (
    AgentEvaluationOption,
    AgentEvaluationResponse,
    AgentEvaluationRow,
    AgentQualifier,
)
from services.filters import FilterInput, normalize_filter_values


V1_TARGET_THRESHOLDS = (Decimal("100"), Decimal("90"), Decimal("80"))
V1_VALUE_THRESHOLDS = (Decimal("100"), Decimal("95"), Decimal("90"))
V1_RECEIPT_THRESHOLDS = (Decimal("35"), Decimal("30"), Decimal("25"))
V1_FOCUS_THRESHOLDS = (Decimal("8"), Decimal("7"), Decimal("6"))
V1_PREMIUM_GLASS_THRESHOLDS = (Decimal("50"), Decimal("40"), Decimal("30"))
V1_QUALIFIER_BANDS: tuple[tuple[int, AgentQualifier], ...] = (
    (18, "Excelent"),
    (14, "Foarte Bun"),
    (10, "Bun"),
    (6, "Mediu"),
)


def v1_pct_points(
    value: Decimal | None,
    thresholds: tuple[Decimal, Decimal, Decimal],
) -> int:
    if value is not None:
        for points, threshold in zip((3, 2, 1), thresholds, strict=True):
            if value >= threshold:
                return points
    return 0


def v1_qualifier(points: int) -> AgentQualifier:
    for minimum_points, label in V1_QUALIFIER_BANDS:
        if points >= minimum_points:
            return label
    return "Scazut"


LEGACY_AGENT_EVALUATION_QUERY = f"""
            WITH current_month AS (
                SELECT MAX(import_month) AS month
                FROM reporting_agent_month
            ),
            current_agents AS (
                SELECT DISTINCT ON (ram.agent)
                    ram.agent,
                    ram.firma,
                    ram.site_code,
                    ram.locatie,
                    ram.regional,
                    ram.asm
                FROM reporting_agent_month ram
                JOIN current_month cm ON cm.month = ram.import_month
                WHERE ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
                ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
            ),
            location_working_days AS (
                SELECT
                    import_month,
                    site_code,
                    COUNT(DISTINCT sale_date)::INT AS working_days
                FROM reporting_agent_day
                WHERE import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
                GROUP BY import_month, site_code
            ),
            monthly_base AS (
                SELECT
                    ram.import_month AS month,
                    ca.firma,
                    ca.site_code,
                    ca.locatie,
                    ca.regional,
                    ca.asm,
                    ram.agent,
                    ram.total_sales,
                    ram.total_quantity,
                    ram.focus_quantity,
                    ram.receipt_count,
                    ram.receipt_2plus_count,
                    ram.working_days,
                    COALESCE(st.target_value, 0) AS store_target,
                    COALESCE(lwd.working_days, 0) AS store_working_days
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                LEFT JOIN location_working_days lwd
                  ON lwd.import_month = ram.import_month
                 AND lwd.site_code = ram.site_code
                LEFT JOIN store_targets st
                  ON st.import_month = ram.import_month
                 AND st.site_code = ram.site_code
                WHERE ram.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
                  AND ($1::TEXT IS NULL OR ram.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT[] IS NULL OR ca.site_code = ANY($4::TEXT[]))
                  AND ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
            ),
            monthly_targets AS (
                SELECT
                    *,
                    CASE
                        WHEN store_working_days > 0
                        THEN ROUND(store_target * working_days / store_working_days, 2)
                        ELSE 0
                    END AS target_value,
                    CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
                    CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
                    CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
                    CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
                FROM monthly_base
            ),
            agent_period AS (
                SELECT
                    CASE
                        WHEN $1::TEXT IS NULL THEN '{AGENT_LIFECYCLE_BASELINE_MONTH}..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE month
                    END AS month,
                    firma,
                    site_code,
                    locatie,
                    regional,
                    asm,
                    agent,
                    COALESCE(SUM(total_sales), 0) AS total_sales,
                    COALESCE(SUM(total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(focus_quantity), 0)::INT AS focus_quantity,
                    COALESCE(SUM(receipt_count), 0)::INT AS receipt_count,
                    COALESCE(SUM(receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                    COALESCE(SUM(working_days), 0)::INT AS working_days,
                    COALESCE(SUM(store_target), 0) AS store_target,
                    COALESCE(SUM(store_working_days), 0)::INT AS store_working_days,
                    COALESCE(SUM(target_value), 0) AS target_value
                FROM monthly_targets
                GROUP BY
                    CASE
                        WHEN $1::TEXT IS NULL THEN '{AGENT_LIFECYCLE_BASELINE_MONTH}..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE month
                    END,
                    firma,
                    site_code,
                    locatie,
                    regional,
                    asm,
                    agent
            ),
            agent_metrics AS (
                SELECT
                    *,
                    CASE WHEN target_value > 0 THEN ROUND(total_sales * 100.0 / target_value, 2) END AS target_pct,
                    CASE WHEN working_days > 0 THEN ROUND(total_sales / working_days, 2) END AS daily_average,
                    CASE WHEN total_quantity > 0 THEN ROUND(total_sales / total_quantity, 2) END AS value_reper,
                    CASE WHEN receipt_count > 0 THEN ROUND(receipt_2plus_count * 100.0 / receipt_count, 2) END AS bonuri_pct,
                    CASE WHEN total_quantity > 0 THEN ROUND(focus_quantity * 100.0 / total_quantity, 2) END AS focus_pct
                FROM agent_period
            ),
            peer_metrics AS (
                SELECT
                    *,
                    CASE
                        WHEN COUNT(*) OVER (PARTITION BY month, site_code) > 1
                        THEN ROUND(
                            (
                                SUM(COALESCE(daily_average, 0)) OVER (PARTITION BY month, site_code)
                                - COALESCE(daily_average, 0)
                            )
                            / NULLIF(COUNT(*) OVER (PARTITION BY month, site_code) - 1, 0),
                            2
                        )
                    END AS peer_daily_average
                FROM agent_metrics
            ),
            premium_lines AS (
                SELECT DISTINCT
                    st.id,
                    CASE
                        WHEN $1::TEXT IS NULL THEN '{AGENT_LIFECYCLE_BASELINE_MONTH}..curent'
                        WHEN POSITION(',' IN $1::TEXT) > 0 THEN 'custom'
                        ELSE st.import_month
                    END AS month,
                    st.agent,
                    pgm.is_premium_glass AS is_premium,
                    st.quantity::INT AS qty
                FROM sales_transactions st
                JOIN current_agents ca ON ca.agent = st.agent
                JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
                WHERE st.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
                  AND ($1::TEXT IS NULL OR st.import_month = ANY(string_to_array($1::TEXT, ',')))
                  AND ($2::TEXT IS NULL OR LOWER(ca.firma) = LOWER($2))
                  AND ($3::TEXT IS NULL OR ca.asm = $3 OR ca.regional = $3)
                  AND ($4::TEXT[] IS NULL OR ca.site_code = ANY($4::TEXT[]))
                  AND LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'
                  AND st.quantity > 0
                  AND st.agent IS NOT NULL
                  AND TRIM(st.agent) != ''
                  AND st.agent != '-'
                  AND st.agent NOT ILIKE 'TR%'
            ),
            premium_by_agent AS (
                SELECT
                    month,
                    agent,
                    COALESCE(SUM(qty), 0)::INT AS glass_qty,
                    COALESCE(SUM(qty) FILTER (WHERE is_premium), 0)::INT AS premium_glass_qty
                FROM premium_lines
                GROUP BY month, agent
            )
            SELECT
                pm.*,
                COALESCE(pba.glass_qty, 0)::INT AS glass_qty,
                COALESCE(pba.premium_glass_qty, 0)::INT AS premium_glass_qty,
                CASE
                    WHEN COALESCE(pba.glass_qty, 0) > 0
                    THEN ROUND(COALESCE(pba.premium_glass_qty, 0) * 100.0 / pba.glass_qty, 2)
                END AS premium_glass_pct
            FROM peer_metrics pm
            LEFT JOIN premium_by_agent pba
              ON pba.month = pm.month
             AND pba.agent = pm.agent
            ORDER BY pm.month DESC, pm.asm, pm.locatie, pm.total_sales DESC, pm.agent
        """

LEGACY_AGENT_OPTIONS_QUERY = f"""
            WITH current_month AS (
                SELECT MAX(import_month) AS month
                FROM reporting_agent_month
            ),
            current_agents AS (
                SELECT DISTINCT ON (ram.agent)
                    ram.agent,
                    ram.firma,
                    ram.regional,
                    ram.asm,
                    ram.site_code,
                    ram.locatie
                FROM reporting_agent_month ram
                JOIN current_month cm ON cm.month = ram.import_month
                WHERE ram.agent IS NOT NULL
                  AND TRIM(ram.agent) != ''
                  AND ram.agent != '-'
                  AND ram.agent NOT ILIKE 'TR%'
                ORDER BY ram.agent, ram.working_days DESC, ram.total_sales DESC, ram.site_code
            ),
            scoped AS (
                SELECT DISTINCT ram.import_month AS month, ca.firma, ca.regional, ca.asm, ca.site_code, ca.locatie
                FROM reporting_agent_month ram
                JOIN current_agents ca ON ca.agent = ram.agent
                WHERE ram.import_month >= '{AGENT_LIFECYCLE_BASELINE_MONTH}'
            )
            SELECT 'month' AS type, month AS value, month AS label FROM scoped
            UNION
            SELECT 'firma' AS type, firma AS value, firma AS label FROM scoped WHERE firma IS NOT NULL AND TRIM(firma) != ''
            UNION
            SELECT 'asm' AS type, asm AS value, asm AS label FROM scoped WHERE asm IS NOT NULL AND TRIM(asm) != ''
            UNION
            SELECT 'store' AS type, site_code AS value, locatie || ' (' || site_code || ')' AS label
            FROM scoped
            WHERE ($1::TEXT IS NULL OR LOWER(firma) = LOWER($1))
              AND ($2::TEXT IS NULL OR asm = $2 OR regional = $2)
            ORDER BY type, label
        """


async def get_agent_evaluation(
    repo: Any,
    month: str | None,
    months: str | None,
    firma: str | None,
    asm: str | None,
    site_code: FilterInput,
) -> AgentEvaluationResponse:
    month_filter = months or month
    site_codes = normalize_filter_values(site_code)
    scoped_firma, scoped_asm = (None, None) if site_codes else (firma, asm)
    rows = await repo.get_agent_evaluation(
        LEGACY_AGENT_EVALUATION_QUERY,
        [month_filter, scoped_firma, scoped_asm, site_codes],
    )
    option_rows = await repo.get_agent_evaluation(
        LEGACY_AGENT_OPTIONS_QUERY,
        [firma, asm],
    )
    month_options, firmas, asms, stores = _options(option_rows)
    return AgentEvaluationResponse(
        months=month_options,
        firmas=firmas,
        asms=asms,
        stores=stores,
        rows=[_evaluation_row(row) for row in rows],
    )


def _options(
    rows: list[Any],
) -> tuple[
    list[AgentEvaluationOption],
    list[AgentEvaluationOption],
    list[AgentEvaluationOption],
    list[AgentEvaluationOption],
]:
    options: dict[str, list[AgentEvaluationOption]] = {
        "month": [], "firma": [], "asm": [], "store": []
    }
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["type"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        options[row["type"]].append(
            AgentEvaluationOption(value=row["value"], label=row["label"])
        )
    return options["month"], options["firma"], options["asm"], options["store"]


def _evaluation_row(row: Any) -> AgentEvaluationRow:
    target_points = v1_pct_points(row["target_pct"], V1_TARGET_THRESHOLDS)
    daily_points = int(
        row["daily_average"] is not None
        and row["peer_daily_average"] is not None
        and row["daily_average"] > row["peer_daily_average"]
    ) * 3
    value_points = v1_pct_points(row["value_reper"], V1_VALUE_THRESHOLDS)
    bonuri_points = v1_pct_points(row["bonuri_pct"], V1_RECEIPT_THRESHOLDS)
    focus_points = v1_pct_points(row["focus_pct"], V1_FOCUS_THRESHOLDS)
    premium_points = v1_pct_points(
        row["premium_glass_pct"], V1_PREMIUM_GLASS_THRESHOLDS
    )
    segment_points = (
        target_points, daily_points, value_points, bonuri_points,
        focus_points, premium_points,
    )
    total_points = sum(segment_points)
    return AgentEvaluationRow(
        month=row["month"],
        firma=row["firma"],
        site_code=row["site_code"],
        locatie=row["locatie"],
        regional=row["regional"],
        asm=row["asm"],
        agent=row["agent"],
        total_sales=row["total_sales"],
        total_quantity=row["total_quantity"],
        working_days=row["working_days"],
        store_target=row["store_target"],
        store_working_days=row["store_working_days"],
        target_value=row["target_value"],
        target_pct=row["target_pct"],
        daily_average=row["daily_average"],
        peer_daily_average=row["peer_daily_average"],
        value_reper=row["value_reper"],
        receipt_count=row["receipt_count"],
        receipt_2plus_count=row["receipt_2plus_count"],
        bonuri_pct=row["bonuri_pct"],
        focus_quantity=row["focus_quantity"],
        focus_pct=row["focus_pct"],
        glass_qty=row["glass_qty"],
        premium_glass_qty=row["premium_glass_qty"],
        premium_glass_pct=row["premium_glass_pct"],
        target_points=target_points,
        daily_points=daily_points,
        value_reper_points=value_points,
        bonuri_points=bonuri_points,
        focus_points=focus_points,
        premium_glass_points=premium_points,
        total_points=total_points,
        has_red_segment=any(point == 0 for point in segment_points),
        qualifier=v1_qualifier(total_points),
    )
