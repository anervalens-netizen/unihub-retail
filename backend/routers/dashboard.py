from __future__ import annotations

import asyncio
import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query

from db.connection import get_pool
from dependencies import get_current_user
from models import (
    AgentStats,
    AsmStats,
    BrandMixItem,
    CategoryMixItem,
    DailySalesPoint,
    DashboardAllResponse,
    DashboardHistoryResponse,
    DashboardSpecialCard,
    DashboardSpecialCardsResponse,
    DashboardSummary,
    MonthlyHistoryPoint,
    PeriodComparisonPayload,
    PeriodComparisonPoint,
    PromoIncentiveSummary,
    ReceiptBucketItem,
    RegionalStats,
    StoreAgentStats,
    StoreStats,
)
from routers.dashboard_filters import (
    scoped_clauses,
)
from routers.shared import normalize_filter
from services.dashboard_specials import (
    build_incentive_card,
    build_promotion_card,
    incentive_multiplier,
    load_incentive_codes,
    load_incentive_reward_map,
    load_special_cards_config,
    parse_incentive_definition,
    parse_promotion_definition,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _shift_month(month: str, offset: int) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    absolute = year * 12 + (month_number - 1) + offset
    shifted_year, shifted_month_index = divmod(absolute, 12)
    return f"{shifted_year:04d}-{shifted_month_index + 1:02d}"


def _month_day_range(month: str, cutoff_day: int) -> tuple[date, date, str]:
    year, month_number = (int(part) for part in month.split("-"))
    _, last_day = calendar.monthrange(year, month_number)
    final_day = max(1, min(cutoff_day, last_day))
    start = date(year, month_number, 1)
    end = date(year, month_number, final_day)
    return start, end, f"01-{final_day:02d}"


def _build_scoped_params(
    initial_params: list[Any],
    *,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[Any], dict[str, int]]:
    params = list(initial_params)
    positions: dict[str, int] = {}
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)
    return params, positions


async def _get_store_incentive_multipliers(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
) -> tuple[dict[str, float], dict[str, float | None]]:
    """Returns (multipliers, achievements) keyed by site_code.
    multipliers: {site_code: 0.0 | 0.5 | 1.0}
    achievements: {site_code: forecasted_ratio | None} — None when no target configured.
    Uses previziune (actual * days_in_month / last_imported_day) for partial months.
    Agent filter intentionally excluded — achievement is a store-level metric.
    """
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=None,
    )
    query_clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="ram",
        store_alias="ram",
        agent_alias="ram",
        month_alias="ram.import_month",
        month_position=1,
        scope_base_alias="ram",
        param_floor=len(params),
    )
    clauses = ["ram.import_month = $1"] + query_clauses

    # Compute forecast factor: project partial-month sales to end-of-month
    meta_row = await conn.fetchrow(
        """
        SELECT
            COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
            EXTRACT(DAY FROM MAX(rid.sale_date))::INT AS last_sale_day,
            EXTRACT(DAY FROM (
                date_trunc('month', to_date($1 || '-01', 'YYYY-MM-DD'))
                + INTERVAL '1 month - 1 day'
            ))::INT AS days_in_month
        FROM import_snapshots snap
        LEFT JOIN (
            SELECT MAX(sale_date) AS sale_date
            FROM reporting_item_day
            WHERE import_month = $1
        ) rid ON true
        WHERE snap.import_month = $1
        """,
        month,
    )
    if meta_row and not meta_row["is_final"] and meta_row["last_sale_day"]:
        last_day = int(meta_row["last_sale_day"])
        days_in_month = int(meta_row["days_in_month"] or last_day)
        forecast_factor = days_in_month / last_day if last_day > 0 else 1.0
    else:
        forecast_factor = 1.0

    rows = await conn.fetch(
        f"""
        SELECT
            ram.site_code,
            COALESCE(SUM(ram.total_sales), 0) AS store_sales,
            COALESCE(MAX(st.target_value), 0) AS target
        FROM reporting_agent_month ram
        LEFT JOIN store_targets st
            ON st.site_code = ram.site_code AND st.import_month = $1
        WHERE {" AND ".join(clauses)}
        GROUP BY ram.site_code
        """,
        *params,
        *scope_params,
    )
    multipliers: dict[str, float] = {}
    achievements: dict[str, float | None] = {}
    for row in rows:
        target = float(row["target"] or 0)
        sales = float(row["store_sales"] or 0) * forecast_factor
        if target > 0:
            ach = sales / target
            achievements[row["site_code"]] = ach
        else:
            achievements[row["site_code"]] = None
            ach = 0.0
        multipliers[row["site_code"]] = incentive_multiplier(ach)
    return multipliers, achievements


async def _fetch_store_stats_rows(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[Any]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    query_clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    clauses = query_clauses or ["true"]
    return await conn.fetch(
        f"""
        WITH filtered_days AS (
            SELECT *
            FROM reporting_agent_day agg
            WHERE {" AND ".join(clauses)}
        )
        SELECT
            fd.import_month,
            fd.site_code,
            fd.locatie,
            fd.firma,
            fd.regional,
            fd.asm,
            COALESCE(SUM(fd.total_sales), 0) AS total_vanzari,
            COALESCE(SUM(fd.total_quantity), 0)::INT AS qty_total,
            COALESCE(SUM(fd.receipt_count), 0)::INT AS nr_bonuri,
            COUNT(DISTINCT fd.agent)::INT AS nr_agenti,
            COUNT(DISTINCT fd.sale_date)::INT AS zile_active,
            COALESCE(MAX(stg.target_value), 0) AS target,
            CASE
                WHEN COALESCE(MAX(stg.target_value), 0) > 0
                THEN ROUND(COALESCE(SUM(fd.total_sales), 0) * 100.0 / MAX(stg.target_value), 2)
                ELSE NULL
            END AS proc_realizare_target
        FROM filtered_days fd
        LEFT JOIN store_targets stg
            ON stg.import_month = fd.import_month
            AND stg.site_code = fd.site_code
        GROUP BY
            fd.import_month,
            fd.site_code,
            fd.locatie,
            fd.firma,
            fd.regional,
            fd.asm
        ORDER BY proc_realizare_target DESC NULLS LAST, total_vanzari DESC, fd.locatie ASC
        """,
        *params,
        *scope_params,
    )


async def _fetch_agent_stats_rows(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[dict[str, Any]]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    agent_clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    rows = await conn.fetch(
        f"""
        WITH store_agent_counts AS (
            SELECT
                import_month,
                site_code,
                COUNT(*)::INT AS active_agents
            FROM reporting_agent_month
            WHERE import_month = $1
            GROUP BY import_month, site_code
        )
        SELECT
            agg.import_month,
            agg.agent,
            agg.site_code,
            agg.locatie,
            agg.firma,
            agg.regional,
            agg.asm,
            agg.total_quantity AS acc_qty_realizat,
            agg.receipt_count AS nr_bonuri,
            agg.receipt_2plus_count AS nr_bon2acc,
            CASE
                WHEN agg.receipt_count > 0
                THEN ROUND(agg.receipt_2plus_count * 100.0 / agg.receipt_count, 2)
                ELSE NULL
            END AS proc_bon2acc,
            agg.total_sales AS total_vanzari,
            agg.working_days AS zile_lucrate,
            CASE
                WHEN agg.working_days > 0
                THEN ROUND(agg.total_sales / agg.working_days, 2)
                ELSE NULL
            END AS medie_zilnica,
            agg.focus_quantity AS acc_focus_qty,
            CASE
                WHEN agg.total_quantity > 0
                THEN ROUND(agg.focus_quantity * 100.0 / agg.total_quantity, 2)
                ELSE NULL
            END AS prc_focus_acc_qty,
            CASE
                WHEN sac.active_agents > 0 THEN ROUND(stg.target_value / sac.active_agents, 2)
                ELSE NULL
            END AS target,
            CASE
                WHEN sac.active_agents > 0 AND stg.target_value > 0
                THEN ROUND(agg.total_sales * 100.0 / (stg.target_value / sac.active_agents), 2)
                ELSE NULL
            END AS proc_realizare_target
        FROM reporting_agent_month agg
        LEFT JOIN store_targets stg
            ON stg.import_month = agg.import_month
            AND stg.site_code = agg.site_code
        LEFT JOIN store_agent_counts sac
            ON sac.import_month = agg.import_month
            AND sac.site_code = agg.site_code
        WHERE {" AND ".join(agent_clauses)}
        ORDER BY agg.total_sales DESC, agg.agent ASC
        """,
        *params,
        *scope_params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows

    config, _ = load_special_cards_config()
    promotion_definition, _ = parse_promotion_definition(config, month)
    incentive_definition, _ = parse_incentive_definition(config, month)
    incentive_codes, _ = (
        load_incentive_codes(incentive_definition)
        if incentive_definition is not None
        else (None, None)
    )
    promotion_codes = (
        promotion_definition["item_codes"] if promotion_definition is not None else []
    )
    if not promotion_codes and not incentive_codes:
        return base_rows

    metric_positions: dict[str, int] = {}
    metric_params: list[Any] = [month, promotion_codes or [], incentive_codes or []]
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            metric_params.append(value)
            metric_positions[key] = len(metric_params)

    metric_query_clauses, metric_scope_params = scoped_clauses(
        user,
        metric_positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(metric_params),
    )
    metric_clauses = ["agg.import_month = $1", *metric_query_clauses]
    metric_rows = await conn.fetch(
        f"""
        SELECT
            agg.import_month,
            agg.site_code,
            agg.agent,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($2::TEXT[]) > 0
                             AND agg.item_code = ANY($2::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS promo_qty,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($3::TEXT[]) > 0
                             AND agg.item_code = ANY($3::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS incentive_qty
        FROM reporting_item_month agg
        WHERE {" AND ".join(metric_clauses)}
        GROUP BY agg.import_month, agg.site_code, agg.agent
        """,
        *metric_params,
        *metric_scope_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["site_code"]), str(row["agent"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get(
            (str(row["import_month"]), str(row["site_code"]), str(row["agent"]))
        )
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows


async def _fetch_regional_stats(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[dict[str, Any]]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    query_clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    clauses = query_clauses or ["true"]
    rows = await conn.fetch(
        f"""
        WITH regional_base AS (
            SELECT
                agg.import_month,
                agg.regional,
                COALESCE(SUM(agg.total_sales), 0) AS total_vanzari,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS nr_bonuri,
                COUNT(DISTINCT agg.agent)::INT AS nr_agenti,
                COALESCE(SUM(agg.working_days), 0)::INT AS zile_active,
                COALESCE(SUM(agg.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                COALESCE(SUM(agg.focus_quantity), 0)::INT AS focus_quantity
            FROM reporting_agent_month agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.import_month, agg.regional
        ),
        regional_stores AS (
            SELECT DISTINCT agg.regional, agg.site_code
            FROM reporting_agent_month agg
            WHERE {" AND ".join(clauses)}
        ),
        regional_targets AS (
            SELECT
                rs.regional,
                COALESCE(SUM(stg.target_value), 0) AS target
            FROM regional_stores rs
            LEFT JOIN store_targets stg
                ON stg.import_month = $1
                AND stg.site_code = rs.site_code
            GROUP BY rs.regional
        )
        SELECT
            rb.import_month,
            rb.regional,
            rb.total_vanzari,
            rb.qty_total,
            rb.nr_bonuri,
            rb.nr_agenti,
            rb.zile_active,
            COALESCE(rt.target, 0) AS target,
            CASE
                WHEN COALESCE(rt.target, 0) > 0
                THEN ROUND(rb.total_vanzari * 100.0 / rt.target, 2)
                ELSE NULL
            END AS proc_realizare_target,
            CASE
                WHEN rb.zile_active > 0
                THEN ROUND(rb.total_vanzari / rb.zile_active, 2)
                ELSE NULL
            END AS medie_zilnica,
            CASE
                WHEN rb.nr_bonuri > 0
                THEN ROUND(rb.receipt_2plus_count * 100.0 / rb.nr_bonuri, 2)
                ELSE NULL
            END AS proc_bon2acc,
            CASE
                WHEN rb.qty_total > 0
                THEN ROUND(rb.focus_quantity * 100.0 / rb.qty_total, 2)
                ELSE NULL
            END AS prc_focus_acc_qty
        FROM regional_base rb
        LEFT JOIN regional_targets rt ON rt.regional = rb.regional
        ORDER BY rb.total_vanzari DESC, rb.regional ASC
        """,
        *params,
        *scope_params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows

    config, _ = load_special_cards_config()
    promotion_definition, _ = parse_promotion_definition(config, month)
    incentive_definition, _ = parse_incentive_definition(config, month)
    incentive_codes, _ = (
        load_incentive_codes(incentive_definition)
        if incentive_definition is not None
        else (None, None)
    )
    promotion_codes = (
        promotion_definition["item_codes"] if promotion_definition is not None else []
    )
    if not promotion_codes and not incentive_codes:
        for row in base_rows:
            row["promo_qty"] = 0
            row["incentive_qty"] = 0
        return base_rows

    metric_positions: dict[str, int] = {}
    metric_params: list[Any] = [month, promotion_codes or [], incentive_codes or []]
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            metric_params.append(value)
            metric_positions[key] = len(metric_params)

    metric_query_clauses, metric_scope_params = scoped_clauses(
        user,
        metric_positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(metric_params),
    )
    metric_clauses = ["agg.import_month = $1", *metric_query_clauses]
    metric_rows = await conn.fetch(
        f"""
        SELECT
            agg.import_month,
            agg.regional,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($2::TEXT[]) > 0
                             AND agg.item_code = ANY($2::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS promo_qty,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($3::TEXT[]) > 0
                             AND agg.item_code = ANY($3::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS incentive_qty
        FROM reporting_item_month agg
        WHERE {" AND ".join(metric_clauses)}
        GROUP BY agg.import_month, agg.regional
        """,
        *metric_params,
        *metric_scope_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["regional"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get((str(row["import_month"]), str(row["regional"])))
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows


async def _fetch_asm_stats(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[dict[str, Any]]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    query_clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    clauses = query_clauses or ["true"]
    rows = await conn.fetch(
        f"""
        WITH asm_base AS (
            SELECT
                agg.import_month,
                agg.regional,
                agg.asm,
                COALESCE(SUM(agg.total_sales), 0) AS total_vanzari,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS qty_total,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS nr_bonuri,
                COUNT(DISTINCT agg.agent)::INT AS nr_agenti,
                COALESCE(SUM(agg.working_days), 0)::INT AS zile_active,
                COALESCE(SUM(agg.receipt_2plus_count), 0)::INT AS receipt_2plus_count,
                COALESCE(SUM(agg.focus_quantity), 0)::INT AS focus_quantity
            FROM reporting_agent_month agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.import_month, agg.regional, agg.asm
        ),
        asm_stores AS (
            SELECT DISTINCT agg.regional, agg.asm, agg.site_code
            FROM reporting_agent_month agg
            WHERE {" AND ".join(clauses)}
        ),
        asm_targets AS (
            SELECT
                ast.regional,
                ast.asm,
                COALESCE(SUM(stg.target_value), 0) AS target
            FROM asm_stores ast
            LEFT JOIN store_targets stg
                ON stg.import_month = $1
                AND stg.site_code = ast.site_code
            GROUP BY ast.regional, ast.asm
        )
        SELECT
            ab.import_month,
            ab.regional,
            ab.asm,
            ab.total_vanzari,
            ab.qty_total,
            ab.nr_bonuri,
            ab.nr_agenti,
            ab.zile_active,
            COALESCE(at.target, 0) AS target,
            CASE
                WHEN COALESCE(at.target, 0) > 0
                THEN ROUND(ab.total_vanzari * 100.0 / at.target, 2)
                ELSE NULL
            END AS proc_realizare_target,
            CASE
                WHEN ab.zile_active > 0
                THEN ROUND(ab.total_vanzari / ab.zile_active, 2)
                ELSE NULL
            END AS medie_zilnica,
            CASE
                WHEN ab.nr_bonuri > 0
                THEN ROUND(ab.receipt_2plus_count * 100.0 / ab.nr_bonuri, 2)
                ELSE NULL
            END AS proc_bon2acc,
            CASE
                WHEN ab.qty_total > 0
                THEN ROUND(ab.focus_quantity * 100.0 / ab.qty_total, 2)
                ELSE NULL
            END AS prc_focus_acc_qty
        FROM asm_base ab
        LEFT JOIN asm_targets at ON at.regional = ab.regional AND at.asm = ab.asm
        ORDER BY ab.total_vanzari DESC, ab.regional ASC, ab.asm ASC
        """,
        *params,
        *scope_params,
    )

    base_rows = [dict(row) for row in rows]
    if not base_rows:
        return base_rows

    config, _ = load_special_cards_config()
    promotion_definition, _ = parse_promotion_definition(config, month)
    incentive_definition, _ = parse_incentive_definition(config, month)
    incentive_codes, _ = (
        load_incentive_codes(incentive_definition)
        if incentive_definition is not None
        else (None, None)
    )
    promotion_codes = (
        promotion_definition["item_codes"] if promotion_definition is not None else []
    )
    if not promotion_codes and not incentive_codes:
        for row in base_rows:
            row["promo_qty"] = 0
            row["incentive_qty"] = 0
        return base_rows

    metric_positions: dict[str, int] = {}
    metric_params: list[Any] = [month, promotion_codes or [], incentive_codes or []]
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            metric_params.append(value)
            metric_positions[key] = len(metric_params)

    metric_query_clauses, metric_scope_params = scoped_clauses(
        user,
        metric_positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(metric_params),
    )
    metric_clauses = ["agg.import_month = $1", *metric_query_clauses]
    metric_rows = await conn.fetch(
        f"""
        SELECT
            agg.import_month,
            agg.regional,
            agg.asm,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($2::TEXT[]) > 0
                             AND agg.item_code = ANY($2::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS promo_qty,
            COALESCE(
                SUM(
                    CASE
                        WHEN cardinality($3::TEXT[]) > 0
                             AND agg.item_code = ANY($3::TEXT[])
                        THEN agg.positive_quantity
                        ELSE 0
                    END
                ),
                0
            ) AS incentive_qty
        FROM reporting_item_month agg
        WHERE {" AND ".join(metric_clauses)}
        GROUP BY agg.import_month, agg.regional, agg.asm
        """,
        *metric_params,
        *metric_scope_params,
    )
    campaign_metrics = {
        (str(row["import_month"]), str(row["regional"]), str(row["asm"])): dict(row)
        for row in metric_rows
    }
    for row in base_rows:
        metrics = campaign_metrics.get(
            (str(row["import_month"]), str(row["regional"]), str(row["asm"]))
        )
        row["promo_qty"] = int(metrics["promo_qty"]) if metrics else 0
        row["incentive_qty"] = int(metrics["incentive_qty"]) if metrics else 0
    return base_rows


async def _fetch_period_comparison(
    conn: Any,
    user: dict[str, Any],
    month: str,
    cutoff_day: int,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> PeriodComparisonPayload:
    previous_month = _shift_month(month, -1)
    year_over_year_month = _shift_month(month, -12)
    periods = [
        ("Curenta", month),
        ("Luna trecuta", previous_month),
        ("Anul trecut", year_over_year_month),
    ]
    rows: list[PeriodComparisonPoint] = []

    for label, period_month in periods:
        start_date, end_date, day_range = _month_day_range(period_month, cutoff_day)
        params, positions = _build_scoped_params(
            [period_month, start_date, end_date],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )

        query_clauses, scope_params = scoped_clauses(
            user,
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
            scope_base_alias="agg",
            param_floor=len(params),
        )
        clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            *query_clauses,
        ]
        row = await conn.fetchrow(
            f"""
            WITH filtered_days AS (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
            )
            SELECT
                COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0), 2) AS daily_average,
                ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS avg_receipt_value,
                ROUND(
                    COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                    / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0),
                    2
                ) AS proc_bon2acc,
                ROUND(
                    COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                    / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0),
                    2
                ) AS prc_focus_acc_qty
            FROM filtered_days fd
            """,
            *params,
            *scope_params,
        )
        rows.append(
            PeriodComparisonPoint(
                label=label,
                month=period_month,
                day_range=day_range,
                total_sales=row["total_sales"] if row else 0,
                total_quantity=row["total_quantity"] if row else 0,
                total_receipts=row["total_receipts"] if row else 0,
                working_days=row["working_days"] if row else 0,
                daily_average=row["daily_average"] if row else None,
                avg_receipt_value=row["avg_receipt_value"] if row else None,
                proc_bon2acc=row["proc_bon2acc"] if row else None,
                prc_focus_acc_qty=row["prc_focus_acc_qty"] if row else None,
            )
        )

    return PeriodComparisonPayload(
        current=rows[0],
        previous=rows[1],
        year_over_year=rows[2],
    )


async def _fetch_receipt_bucket_mix(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[ReceiptBucketItem]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    rows = await conn.fetch(
        f"""
        WITH filtered_month AS (
            SELECT *
            FROM reporting_agent_month agg
            WHERE {" AND ".join(clauses)}
        )
        SELECT
            bucket,
            receipt_count,
            ROUND(receipt_count * 100.0 / NULLIF(SUM(receipt_count) OVER (), 0), 2) AS share_pct
        FROM (
            SELECT '1' AS bucket, COALESCE(SUM(receipt_1_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '2' AS bucket, COALESCE(SUM(receipt_2_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '3' AS bucket, COALESCE(SUM(receipt_3_count), 0)::INT AS receipt_count FROM filtered_month
            UNION ALL
            SELECT '>3' AS bucket, COALESCE(SUM(receipt_4plus_count), 0)::INT AS receipt_count FROM filtered_month
        ) buckets
        WHERE receipt_count > 0
        ORDER BY
            CASE bucket
                WHEN '1' THEN 1
                WHEN '2' THEN 2
                WHEN '3' THEN 3
                ELSE 4
            END
        """,
        *params,
        *scope_params,
    )
    return [ReceiptBucketItem(**dict(row)) for row in rows]


async def _fetch_focus_subcategory_mix(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[CategoryMixItem]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    rows = await conn.fetch(
        f"""
        WITH focus_sales AS (
            SELECT
                agg.focus_subcategory AS category,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_focus_item_month agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.focus_subcategory
        ),
        ranked AS (
            SELECT
                category,
                sales_total,
                quantity_total,
                ROW_NUMBER() OVER (ORDER BY quantity_total DESC, sales_total DESC, category ASC) AS rank_no
            FROM focus_sales
            WHERE quantity_total > 0
        ),
        grouped AS (
            SELECT
                CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END AS category,
                SUM(sales_total) AS sales_total,
                SUM(quantity_total) AS quantity_total
            FROM ranked
            GROUP BY CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END
        )
        SELECT
            category,
            sales_total,
            quantity_total,
            ROUND(quantity_total * 100.0 / NULLIF(SUM(quantity_total) OVER (), 0), 2) AS share_pct
        FROM grouped
        ORDER BY quantity_total DESC, sales_total DESC, category ASC
        """,
        *params,
        *scope_params,
    )
    return [CategoryMixItem(**dict(row)) for row in rows]


async def _fetch_brand_mix(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[BrandMixItem]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    rows = await conn.fetch(
        f"""
        WITH brand_sales AS (
            SELECT
                agg.brand_group AS brand,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_category_month agg
            WHERE {" AND ".join(clauses)}
              AND LOWER(TRIM(agg.category)) IN ('stil si protectie', 'folii sticla')
            GROUP BY agg.brand_group
        )
        SELECT
            brand,
            sales_total,
            quantity_total,
            ROUND(sales_total * 100.0 / NULLIF(SUM(sales_total) OVER (), 0), 2) AS share_pct
        FROM brand_sales
        WHERE sales_total > 0 OR quantity_total > 0
        ORDER BY sales_total DESC, quantity_total DESC, brand ASC
        """,
        *params,
        *scope_params,
    )
    return [BrandMixItem(**dict(row)) for row in rows]


async def _fetch_promo_incentive_summary(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> PromoIncentiveSummary:
    config, _ = load_special_cards_config()
    promotion_definition, promotion_error = parse_promotion_definition(config, month)
    incentive_definition, incentive_error = parse_incentive_definition(config, month)

    promo_qty = 0
    promo_sales: Decimal = Decimal("0")
    incentive_qty = 0
    incentive_value: Decimal = Decimal("0")

    if promotion_definition is not None and promotion_error is None:
        promo_params, promo_positions = _build_scoped_params(
            [
                month,
                promotion_definition["start_date"],
                promotion_definition["end_date"],
                promotion_definition["item_codes"],
            ],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        promo_clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            f"agg.item_code = ANY($4::TEXT[])",
        ]
        promo_query_clauses, promo_scope_params = scoped_clauses(
            user,
            promo_positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
            scope_base_alias="agg",
            param_floor=len(promo_params),
        )
        promo_clauses.extend(promo_query_clauses)
        promo_row = await conn.fetchrow(
            f"""
            SELECT
                COALESCE(SUM(agg.positive_quantity), 0) AS promo_qty,
                COALESCE(SUM(agg.total_sales), 0) AS promo_sales
            FROM reporting_item_day agg
            WHERE {" AND ".join(promo_clauses)}
            """,
            *promo_params,
            *promo_scope_params,
        )
        if promo_row:
            promo_qty = int(promo_row["promo_qty"] or 0)
            promo_sales = promo_row["promo_sales"] or Decimal("0")

    if (
        incentive_definition is not None
        and incentive_error is None
        and month == incentive_definition["month"]
    ):
        reward_map, reward_map_error = load_incentive_reward_map(incentive_definition)
        if reward_map is not None and reward_map_error is None:
            incentive_codes = list(reward_map.keys())
            incentive_params, incentive_positions = _build_scoped_params(
                [month, incentive_codes],
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
            )
            incentive_clauses = [
                "agg.import_month = $1",
                "agg.item_code = ANY($2::TEXT[])",
            ]
            incentive_query_clauses, incentive_scope_params = scoped_clauses(
                user,
                incentive_positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
                month_alias="agg.import_month",
                month_position=1,
                scope_base_alias="agg",
                param_floor=len(incentive_params),
            )
            incentive_clauses.extend(incentive_query_clauses)
            item_rows = await conn.fetch(
                f"""
                SELECT agg.site_code, agg.item_code,
                       COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                FROM reporting_item_month agg
                WHERE {" AND ".join(incentive_clauses)}
                GROUP BY agg.site_code, agg.item_code
                """,
                *incentive_params,
                *incentive_scope_params,
            )
            store_multipliers, _ = await _get_store_incentive_multipliers(
                conn, user, month, firma, regional, asm, site_code
            )
            incentive_qty = sum(int(r["qty"]) for r in item_rows)
            incentive_value = Decimal(str(
                sum(
                    max(0, int(r["qty"]))
                    * reward_map.get(r["item_code"], 0)
                    * store_multipliers.get(r["site_code"], 0)
                    for r in item_rows
                )
            ))

    promo_impact = promo_sales * Decimal("0.20")
    return PromoIncentiveSummary(
        promo_qty=promo_qty,
        promo_sales=promo_sales,
        promo_impact=promo_impact,
        incentive_qty=incentive_qty,
        incentive_value=incentive_value,
    )


async def _fetch_category_mix(
    conn: Any,
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> list[CategoryMixItem]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    rows = await conn.fetch(
        f"""
        WITH category_sales AS (
            SELECT
                agg.category,
                COALESCE(SUM(agg.total_sales), 0) AS sales_total,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS quantity_total
            FROM reporting_category_month agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.category
        ),
        ranked AS (
            SELECT
                category,
                sales_total,
                quantity_total,
                ROW_NUMBER() OVER (ORDER BY sales_total DESC, category ASC) AS rank_no
            FROM category_sales
        ),
        grouped AS (
            SELECT
                CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END AS category,
                SUM(sales_total) AS sales_total,
                SUM(quantity_total) AS quantity_total
            FROM ranked
            GROUP BY CASE WHEN rank_no <= 5 THEN category ELSE 'Altele' END
        )
        SELECT
            category,
            sales_total,
            quantity_total,
            ROUND(sales_total * 100.0 / NULLIF(SUM(sales_total) OVER (), 0), 2) AS share_pct
        FROM grouped
        ORDER BY sales_total DESC, category ASC
        """,
        *params,
        *scope_params,
    )
    return [CategoryMixItem(**dict(row)) for row in rows]


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> DashboardSummary:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            WITH filtered_days AS (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
            ),
            sales_summary AS (
                SELECT
                    fd.import_month AS month,
                    COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                    COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                    ROUND(COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS proc_bon2acc,
                    ROUND(COALESCE(SUM(fd.focus_quantity), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS prc_focus_acc_qty,
                    COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                    COUNT(DISTINCT fd.agent)::INT AS total_agents,
                    COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                    ROUND(
                        COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0),
                        2
                    ) AS daily_average
                FROM filtered_days fd
                GROUP BY fd.import_month
            ),
            last_sale AS (
                SELECT MAX(sale_date) AS last_sale_date
                FROM filtered_days
            ),
            target_summary AS (
                SELECT
                    stg.import_month AS month,
                    COALESCE(SUM(stg.target_value), 0) AS total_target
                FROM store_targets stg
                WHERE stg.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = stg.site_code
                  )
                GROUP BY stg.import_month
            ),
            month_meta AS (
                SELECT
                    snap.import_month,
                    COALESCE(snap.is_month_final, true) AS is_month_final,
                    EXTRACT(DAY FROM (
                        date_trunc('month', to_date(snap.import_month || '-01', 'YYYY-MM-DD'))
                        + INTERVAL '1 month - 1 day'
                    ))::INT AS days_in_month
                FROM import_snapshots snap
                WHERE snap.import_month = $1 AND snap.status = 'completed'
                ORDER BY snap.created_at DESC
                LIMIT 1
            ),

            cartele_summary AS (
                SELECT
                    COALESCE(SUM(c.qty_total), 0)::INT AS cartele_qty
                FROM v_cartele_monthly c
                WHERE c.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = c.site_code
                        AND fd.agent = c.agent
                        AND fd.import_month = c.import_month
                  )
            )
            SELECT
                ss.month,
                ss.total_sales,
                COALESCE(ts.total_target, 0) AS total_target,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS target_progress_pct,
                CASE
                    WHEN COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND(ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month, 2)
                    ELSE ss.total_sales
                END AS forecast_sales,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                         AND COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND((ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month) * 100.0 / ts.total_target, 2)
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS forecast_target_progress_pct,
                ss.total_quantity,
                ss.total_receipts,
                ss.proc_bon2acc,
                ss.prc_focus_acc_qty,
                ss.total_stores,
                ss.total_agents,
                ss.working_days,
                ss.daily_average,
                COALESCE(mm.is_month_final, true) AS is_month_final,
                ls.last_sale_date,
                CASE
                    WHEN ls.last_sale_date IS NOT NULL THEN EXTRACT(DAY FROM ls.last_sale_date)::INT
                    ELSE NULL
                END AS imported_day_of_month,
                mm.days_in_month,
                cs.cartele_qty
            FROM sales_summary ss
            LEFT JOIN target_summary ts ON ts.month = ss.month
            LEFT JOIN month_meta mm ON mm.import_month = ss.month
            LEFT JOIN last_sale ls ON true
            LEFT JOIN cartele_summary cs ON true
            """,
            *params,
            *scope_params,
        )
    if row is None:
        return DashboardSummary(
            month=month,
            total_sales=0,
            total_target=0,
            target_progress_pct=None,
            forecast_sales=None,
            forecast_target_progress_pct=None,
            total_quantity=0,
            total_receipts=0,
            proc_bon2acc=None,
            prc_focus_acc_qty=None,
            total_stores=0,
            total_agents=0,
            working_days=0,
            daily_average=None,
            is_month_final=True,
            last_sale_date=None,
            imported_day_of_month=None,
            days_in_month=None,
            cartele_qty=0,
        )
    return DashboardSummary(**dict(row))


@router.get("/agents", response_model=list[AgentStats])
async def get_agent_stats(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[AgentStats]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            WITH filtered_days AS (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
            ),
            sales_summary AS (
                SELECT
                    fd.import_month AS month,
                    COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                    COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                    ROUND(COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0), 2) AS proc_bon2acc,
                    ROUND(COALESCE(SUM(fd.focus_quantity), 0) * 100.0 / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0), 2) AS prc_focus_acc_qty,
                    COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                    COUNT(DISTINCT fd.agent)::INT AS total_agents,
                    COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                    ROUND(
                        COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0),
                        2
                    ) AS daily_average
                FROM filtered_days fd
                GROUP BY fd.import_month
            ),
            last_sale AS (
                SELECT MAX(sale_date) AS last_sale_date
                FROM filtered_days
            ),
            target_summary AS (
                SELECT
                    stg.import_month AS month,
                    COALESCE(SUM(stg.target_value), 0) AS total_target
                FROM store_targets stg
                WHERE stg.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = stg.site_code
                  )
                GROUP BY stg.import_month
            ),
            month_meta AS (
                SELECT
                    snap.import_month,
                    COALESCE(snap.is_month_final, true) AS is_month_final,
                    EXTRACT(DAY FROM (
                        date_trunc('month', to_date(snap.import_month || '-01', 'YYYY-MM-DD'))
                        + INTERVAL '1 month - 1 day'
                    ))::INT AS days_in_month
                FROM import_snapshots snap
                WHERE snap.import_month = $1 AND snap.status = 'completed'
                ORDER BY snap.created_at DESC
                LIMIT 1
            ),

            cartele_summary AS (
                SELECT
                    COALESCE(SUM(c.qty_total), 0)::INT AS cartele_qty
                FROM v_cartele_monthly c
                WHERE c.import_month = $1
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.site_code = c.site_code
                        AND fd.agent = c.agent
                        AND fd.import_month = c.import_month
                  )
            ),
            SELECT
                ss.month,
                ss.total_sales,
                COALESCE(ts.total_target, 0) AS total_target,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS target_progress_pct,
                CASE
                    WHEN COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND(ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month, 2)
                    ELSE ss.total_sales
                END AS forecast_sales,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                         AND COALESCE(mm.is_month_final, true) = false
                         AND ls.last_sale_date IS NOT NULL
                         AND EXTRACT(DAY FROM ls.last_sale_date) > 0
                    THEN ROUND((ss.total_sales / EXTRACT(DAY FROM ls.last_sale_date) * mm.days_in_month) * 100.0 / ts.total_target, 2)
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS forecast_target_progress_pct,
                ss.total_quantity,
                ss.total_receipts,
                ss.proc_bon2acc,
                ss.prc_focus_acc_qty,
                ss.total_stores,
                ss.total_agents,
                ss.working_days,
                ss.daily_average,
                COALESCE(mm.is_month_final, true) AS is_month_final,
                ls.last_sale_date,
                CASE
                    WHEN ls.last_sale_date IS NOT NULL THEN EXTRACT(DAY FROM ls.last_sale_date)::INT
                    ELSE NULL
                END AS imported_day_of_month,
                mm.days_in_month,
                cs.cartele_qty
            FROM sales_summary ss
            LEFT JOIN target_summary ts ON ts.month = ss.month
            LEFT JOIN month_meta mm ON mm.import_month = ss.month
            LEFT JOIN last_sale ls ON true
            LEFT JOIN cartele_summary cs ON true
            """,
            *params,
            *scope_params,
        )
    if row is None:
        return DashboardSummary(
            month=month,
            total_sales=0,
            total_target=0,
            target_progress_pct=None,
            forecast_sales=None,
            forecast_target_progress_pct=None,
            total_quantity=0,
            total_receipts=0,
            proc_bon2acc=None,
            prc_focus_acc_qty=None,
            total_stores=0,
            total_agents=0,
            working_days=0,
            daily_average=None,
            is_month_final=True,
            last_sale_date=None,
            imported_day_of_month=None,
            days_in_month=None,
            cartele_qty=0,
        )
    return DashboardSummary(**dict(row))


@router.get("/all", response_model=DashboardAllResponse)
async def get_dashboard_all(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> DashboardAllResponse:
    """Returns all dashboard data except history in a single response.

    Runs agents, stores, and daily queries in parallel for speed.
    Calls get_summary directly for complete summary data (including targets).
    """
    pool = await get_pool()

    async def get_agents_data() -> list[AgentStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_agent_stats_rows(
                conn,
                user,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )
        return [AgentStats(**row) for row in rows]

    async def get_stores_data() -> list[StoreStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_store_stats_rows(
                conn,
                user,
                month,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )
        return [StoreStats(**dict(row)) for row in rows]

    async def get_daily_data() -> list[DailySalesPoint]:
        params, positions = _build_scoped_params(
            [month],
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        clauses, scope_params = scoped_clauses(
            user,
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
            scope_base_alias="agg",
            param_floor=len(params),
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    agg.sale_date,
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
                FROM reporting_agent_day agg
                WHERE {" AND ".join(clauses)}
                GROUP BY agg.sale_date
                ORDER BY agg.sale_date ASC
                """,
                *params,
                *scope_params,
            )
        return [DailySalesPoint(**dict(row)) for row in rows]

    async def get_period_comparison_data(
        cutoff_day: int,
    ) -> PeriodComparisonPayload:
        async with pool.acquire() as conn:
            return await _fetch_period_comparison(
                conn,
                user,
                month,
                cutoff_day,
                firma,
                regional,
                asm,
                site_code,
                agent,
            )

    async def get_category_mix_data() -> list[CategoryMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_category_mix(
                conn, user, month, firma, regional, asm, site_code, agent
            )

    async def get_receipt_bucket_mix_data() -> list[ReceiptBucketItem]:
        async with pool.acquire() as conn:
            return await _fetch_receipt_bucket_mix(
                conn, user, month, firma, regional, asm, site_code, agent
            )

    async def get_focus_subcategory_mix_data() -> list[CategoryMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_focus_subcategory_mix(
                conn, user, month, firma, regional, asm, site_code, agent
            )

    async def get_brand_mix_data() -> list[BrandMixItem]:
        async with pool.acquire() as conn:
            return await _fetch_brand_mix(
                conn, user, month, firma, regional, asm, site_code, agent
            )

    async def get_promo_incentive_data() -> PromoIncentiveSummary:
        async with pool.acquire() as conn:
            return await _fetch_promo_incentive_summary(
                conn, user, month, firma, regional, asm, site_code, agent
            )

    async def get_regional_data() -> list[RegionalStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_regional_stats(
                conn, user, month, firma, regional, asm, site_code, agent
            )
        return [RegionalStats(**row) for row in rows]

    async def get_asm_data() -> list[AsmStats]:
        async with pool.acquire() as conn:
            rows = await _fetch_asm_stats(
                conn, user, month, firma, regional, asm, site_code, agent
            )
        return [AsmStats(**row) for row in rows]

    # Run agents, stores, daily in parallel (each gets own connection)
    # Call get_summary directly for complete summary (targets, forecast, etc.)
    (
        agents,
        stores,
        daily,
        category_mix,
        receipt_bucket_mix,
        focus_subcategory_mix,
        brand_mix,
        promo_incentive,
        regionals,
        asms,
    ) = await asyncio.gather(
        get_agents_data(),
        get_stores_data(),
        get_daily_data(),
        get_category_mix_data(),
        get_receipt_bucket_mix_data(),
        get_focus_subcategory_mix_data(),
        get_brand_mix_data(),
        get_promo_incentive_data(),
        get_regional_data(),
        get_asm_data(),
    )
    summary = await get_summary(
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        user=user,
    )
    special_cards_response = await get_special_cards(
        month=month,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
        user=user,
    )
    cutoff_day = summary.imported_day_of_month or summary.days_in_month or 1
    period_comparison = await get_period_comparison_data(cutoff_day)

    return DashboardAllResponse(
        summary=summary,
        agents=agents,
        stores=stores,
        daily=daily,
        special_cards=special_cards_response.cards,
        period_comparison=period_comparison,
        category_mix=category_mix,
        receipt_bucket_mix=receipt_bucket_mix,
        focus_subcategory_mix=focus_subcategory_mix,
        brand_mix=brand_mix,
        promo_incentive=promo_incentive,
        regionals=regionals,
        asms=asms,
    )


@router.get("/daily", response_model=list[DailySalesPoint])
async def get_daily_sales(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> list[DailySalesPoint]:
    params, positions = _build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        month_alias="agg.import_month",
        month_position=1,
        scope_base_alias="agg",
        param_floor=len(params),
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                agg.sale_date,
                COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                COALESCE(SUM(agg.total_quantity), 0)::INT AS total_quantity,
                COALESCE(SUM(agg.receipt_count), 0)::INT AS receipt_count
            FROM reporting_agent_day agg
            WHERE {" AND ".join(clauses)}
            GROUP BY agg.sale_date
            ORDER BY agg.sale_date ASC
            """,
            *params,
            *scope_params,
        )
    return [DailySalesPoint(**dict(row)) for row in rows]


async def _get_special_cards_data(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    user: dict[str, Any],
) -> list[DashboardSpecialCard]:
    """Internal helper to build special cards data without HTTP dependencies."""
    config, config_error = load_special_cards_config()
    promotion_definition, promotion_error = parse_promotion_definition(config, month)
    incentive_definition, incentive_error = parse_incentive_definition(config, month)
    promotion_stats: dict[str, Any] | None = None
    incentive_stats: dict[str, Any] | None = None
    incentive_codes_error: str | None = None

    pool = await get_pool()

    if promotion_definition is not None and promotion_error is None:
        params: list[Any] = [
            month,
            promotion_definition["start_date"],
            promotion_definition["end_date"],
            promotion_definition["item_codes"],
        ]
        positions: dict[str, int] = {}
        for key, value in [
            ("firma", normalize_filter(firma)),
            ("regional", normalize_filter(regional)),
            ("asm", normalize_filter(asm)),
            ("site_code", normalize_filter(site_code)),
            ("agent", normalize_filter(agent)),
        ]:
            if value is not None:
                params.append(value)
                positions[key] = len(params)

        clauses = [
            "agg.import_month = $1",
            "agg.sale_date BETWEEN $2 AND $3",
            "agg.item_code = ANY($4::TEXT[])",
        ]
        query_clauses, scope_params = scoped_clauses(
            user,
            positions,
            site_alias="agg",
            store_alias="agg",
            agent_alias="agg",
            month_alias="agg.import_month",
            month_position=1,
            scope_base_alias="agg",
            param_floor=len(params),
        )
        clauses.extend(query_clauses)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    COALESCE(SUM(agg.total_sales), 0) AS total_sales,
                    COALESCE(SUM(agg.positive_quantity), 0) AS total_quantity,
                    COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.positive_quantity > 0) AS active_stores,
                    COUNT(DISTINCT agg.agent) FILTER (WHERE agg.positive_quantity > 0) AS active_agents
                FROM reporting_item_day agg
                WHERE {" AND ".join(clauses)}
                """,
                *params,
                *scope_params,
            )
            receipt_query_clauses, receipt_scope_params = scoped_clauses(
                user,
                positions,
                site_alias="st",
                store_alias="s",
                agent_alias="st",
                include_cartela_filter=True,
                scope_base_alias="st",
                param_floor=len(params),
            )
            receipt_row = await conn.fetchrow(
                f"""
                SELECT
                    COUNT(DISTINCT st.bon_nr) AS total_receipts
                FROM sales_transactions st
                JOIN stores s ON s.site_code = st.site_code
                WHERE st.import_month = $1
                  AND st.sale_date BETWEEN $2 AND $3
                  AND st.item_code = ANY($4::TEXT[])
                  {" ".join(f"AND {clause}" for clause in receipt_query_clauses)}
                """,
                *params,
                *receipt_scope_params,
            )
        promotion_stats = dict(row) if row else None
        if promotion_stats is not None:
            promotion_stats["total_receipts"] = int(
                (receipt_row["total_receipts"] if receipt_row else 0) or 0
            )

    if incentive_definition is not None and incentive_error is None:
        reward_map, incentive_codes_error = load_incentive_reward_map(incentive_definition)
        if reward_map is not None:
            incentive_codes = list(reward_map.keys())
            params = [month, incentive_codes]
            positions = {}
            for key, value in [
                ("firma", normalize_filter(firma)),
                ("regional", normalize_filter(regional)),
                ("asm", normalize_filter(asm)),
                ("site_code", normalize_filter(site_code)),
                ("agent", normalize_filter(agent)),
            ]:
                if value is not None:
                    params.append(value)
                    positions[key] = len(params)

            clauses = [
                "agg.import_month = $1",
                "agg.item_code = ANY($2::TEXT[])",
            ]
            query_clauses, scope_params = scoped_clauses(
                user,
                positions,
                site_alias="agg",
                store_alias="agg",
                agent_alias="agg",
                month_alias="agg.import_month",
                month_position=1,
                scope_base_alias="agg",
                param_floor=len(params),
            )
            clauses.extend(query_clauses)
            async with pool.acquire() as conn:
                item_rows = await conn.fetch(
                    f"""
                    SELECT
                        agg.site_code,
                        agg.item_code,
                        COALESCE(SUM(agg.net_quantity), 0)::INT AS net_quantity,
                        COALESCE(SUM(agg.positive_quantity), 0)::INT AS positive_quantity,
                        COALESCE(SUM(agg.return_quantity), 0)::INT AS return_quantity
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(clauses)}
                    GROUP BY agg.site_code, agg.item_code
                    """,
                    *params,
                    *scope_params,
                )
                meta_row = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(DISTINCT agg.site_code) FILTER (WHERE agg.positive_quantity > 0) AS active_stores,
                        COUNT(DISTINCT agg.agent) FILTER (WHERE agg.positive_quantity > 0) AS active_agents,
                        COUNT(DISTINCT agg.item_code) FILTER (WHERE agg.positive_quantity > 0) AS active_codes
                    FROM reporting_item_month agg
                    WHERE {" AND ".join(clauses)}
                    """,
                    *params,
                    *scope_params,
                )
                store_multipliers, _ = await _get_store_incentive_multipliers(
                    conn, user, month, firma, regional, asm, site_code
                )
            net_qty = sum(int(r["net_quantity"]) for r in item_rows)
            pos_qty = sum(int(r["positive_quantity"]) for r in item_rows)
            ret_qty = sum(int(r["return_quantity"]) for r in item_rows)
            incentive_value = sum(
                max(0, int(r["net_quantity"]))
                * reward_map.get(r["item_code"], 0)
                * store_multipliers.get(r["site_code"], 0)
                for r in item_rows
            )
            incentive_stats = {
                "net_quantity": net_qty,
                "positive_quantity": pos_qty,
                "return_quantity": ret_qty,
                "incentive_value": incentive_value,
                "active_stores": int(meta_row["active_stores"]) if meta_row else 0,
                "active_agents": int(meta_row["active_agents"]) if meta_row else 0,
                "active_codes": int(meta_row["active_codes"]) if meta_row else 0,
            }

    cards: list[DashboardSpecialCard] = []
    if promotion_definition is not None or config_error:
        cards.append(
            build_promotion_card(
                month,
                promotion_definition,
                promotion_stats,
                config_error=config_error,
                definition_error=promotion_error,
            )
        )
    if incentive_definition is not None or config_error:
        cards.append(
            build_incentive_card(
                month,
                incentive_definition,
                incentive_stats,
                config_error=config_error,
                definition_error=incentive_error,
                codes_error=incentive_codes_error,
            )
        )
    return cards


@router.get("/special-cards", response_model=DashboardSpecialCardsResponse)
async def get_special_cards(
    month: str = Query(...),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> DashboardSpecialCardsResponse:
    cards = await _get_special_cards_data(
        month, firma, regional, asm, site_code, agent, user
    )
    return DashboardSpecialCardsResponse(cards=cards)


@router.get("/history", response_model=DashboardHistoryResponse)
async def get_monthly_history(
    month: str = Query(...),
    months_back: int = Query(12, ge=2, le=24),
    firma: str | None = None,
    regional: str | None = None,
    asm: str | None = None,
    site_code: str | None = None,
    agent: str | None = None,
    user: dict[str, Any] = Depends(get_current_user),
) -> DashboardHistoryResponse:
    params: list[Any] = [month, months_back]
    positions: dict[str, int] = {}
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)

    sales_clauses, sales_scope_params = scoped_clauses(
        user,
        positions,
        site_alias="agg",
        store_alias="agg",
        agent_alias="agg",
        scope_base_alias="agg",
        param_floor=2,
    )
    sales_clauses.insert(
        0, "agg.import_month IN (SELECT import_month FROM recent_months)"
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH recent_months AS MATERIALIZED (
                SELECT import_month
                FROM (
                    SELECT DISTINCT import_month
                    FROM import_snapshots
                    WHERE import_month <= $1
                      AND status = 'completed'
                    ORDER BY import_month DESC
                    LIMIT $2
                ) months
            ),
            filtered_days AS MATERIALIZED (
                SELECT *
                FROM reporting_agent_day agg
                WHERE {" AND ".join(sales_clauses)}
            ),
            sales_summary AS (
                SELECT
                    fd.import_month AS month,
                    COALESCE(SUM(fd.total_sales), 0) AS total_sales,
                    COALESCE(SUM(fd.total_quantity), 0)::INT AS total_quantity,
                    COALESCE(SUM(fd.receipt_count), 0)::INT AS total_receipts,
                    ROUND(
                        COALESCE(SUM(fd.receipt_2plus_count), 0) * 100.0
                        / NULLIF(COALESCE(SUM(fd.receipt_count), 0), 0),
                        2
                    ) AS proc_bon2acc,
                    ROUND(
                        COALESCE(SUM(fd.focus_quantity), 0) * 100.0
                        / NULLIF(COALESCE(SUM(fd.total_quantity), 0), 0),
                        2
                    ) AS prc_focus_acc_qty,
                    COUNT(DISTINCT fd.site_code)::INT AS total_stores,
                    COUNT(DISTINCT fd.agent)::INT AS total_agents,
                    COUNT(DISTINCT fd.sale_date)::INT AS working_days,
                    ROUND(COALESCE(SUM(fd.total_sales), 0) / NULLIF(COUNT(DISTINCT fd.sale_date), 0), 2) AS daily_average
                FROM filtered_days fd
                GROUP BY fd.import_month
            ),
            target_summary AS (
                SELECT
                    stg.import_month AS month,
                    COALESCE(SUM(stg.target_value), 0) AS total_target
                FROM store_targets stg
                WHERE stg.import_month IN (SELECT import_month FROM recent_months)
                  AND EXISTS (
                      SELECT 1
                      FROM filtered_days fd
                      WHERE fd.import_month = stg.import_month
                        AND fd.site_code = stg.site_code
                  )
                GROUP BY stg.import_month
            )
            SELECT
                ss.month,
                ss.total_sales,
                COALESCE(ts.total_target, 0) AS total_target,
                CASE
                    WHEN COALESCE(ts.total_target, 0) > 0
                    THEN ROUND(ss.total_sales * 100.0 / ts.total_target, 2)
                    ELSE NULL
                END AS target_progress_pct,
                ss.total_quantity,
                ss.total_receipts,
                ss.proc_bon2acc,
                ss.prc_focus_acc_qty,
                ss.total_stores,
                ss.total_agents,
                ss.working_days,
                ss.daily_average
            FROM sales_summary ss
            LEFT JOIN target_summary ts ON ts.month = ss.month
            ORDER BY ss.month ASC
            """,
            *params,
            *sales_scope_params,
        )
    return DashboardHistoryResponse(
        history=[MonthlyHistoryPoint(**dict(row)) for row in rows]
    )
