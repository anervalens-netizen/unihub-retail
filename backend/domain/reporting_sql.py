"""Validated SQL fragments shared by repositories and application services."""
from __future__ import annotations

import re

_SQL_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SQL_PARAMETER_RE = re.compile(r"^\$[1-9][0-9]*$")
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validated_parameter(value: str) -> str:
    if not _SQL_PARAMETER_RE.fullmatch(value):
        raise ValueError(f"Invalid SQL parameter placeholder: {value!r}")
    return value


def _validated_identifier(value: str) -> str:
    if not _SQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid SQL identifier: {value!r}")
    return value


def canonical_receipt_identity_sql(alias: str) -> str:
    """Return the canonical PostgreSQL tuple used to identify one receipt."""
    if not _SQL_ALIAS_RE.fullmatch(alias):
        raise ValueError(f"Invalid SQL alias: {alias!r}")
    return (
        "("
        f"{alias}.sale_date, "
        f"{alias}.site_code, "
        f"COALESCE(NULLIF(BTRIM({alias}.agent), ''), '<unknown>'), "
        f"{alias}.bon_nr"
        ")"
    )


def business_forecast_factor_ctes(
    month_parameter: str = "$1",
    *,
    result_name: str = "forecast_meta",
    cutoff_parameter: str | None = None,
) -> str:
    """Canonical SQL CTEs for the business-calendar forecast factor.

    Only positional PostgreSQL placeholders and validated identifiers are
    accepted because this function deliberately returns an interpolated SQL
    fragment for static repository queries.
    """
    month_parameter = _validated_parameter(month_parameter)
    result_name = _validated_identifier(result_name)
    if cutoff_parameter is not None:
        cutoff_parameter = _validated_parameter(cutoff_parameter)

    if cutoff_parameter is None:
        month_meta_sql = f"""
            SELECT
                COALESCE(BOOL_OR(snap.is_month_final), true) AS is_final,
                MAX(rid.sale_date) AS last_sale_date
            FROM import_snapshots snap
            LEFT JOIN (
                SELECT MAX(sale_date) AS sale_date
                FROM reporting_item_day
                WHERE import_month = {month_parameter}
            ) rid ON true
            WHERE snap.import_month = {month_parameter}
        """
    else:
        month_meta_sql = f"""
            SELECT
                false AS is_final,
                MAX(sale_date) AS last_sale_date
            FROM reporting_item_day
            WHERE import_month = {month_parameter}
              AND sale_date <= {cutoff_parameter}
        """
    return f"""
        forecast_month_meta AS (
            {month_meta_sql}
        ),
        forecast_latest_business_run AS (
            SELECT run.id
            FROM ai_forecast_runs run
            WHERE run.status = 'completed'
              AND run.metric = 'sales_value'
              AND run.horizon = 'current_month'
              AND run.forecast_month = {month_parameter}
            ORDER BY run.generated_at DESC, run.id DESC
            LIMIT 1
        ),
        forecast_business_weights AS (
            SELECT
                SUM(GREATEST(day.forecast_sales, 0)) AS total_weight,
                SUM(GREATEST(day.forecast_sales, 0)) FILTER (
                    WHERE day.forecast_date <= month_meta.last_sale_date
                ) AS elapsed_weight
            FROM ai_forecast_store_day day
            JOIN forecast_latest_business_run run ON run.id = day.run_id
            CROSS JOIN forecast_month_meta month_meta
        ),
        {result_name} AS (
            SELECT
                CASE
                    WHEN NOT month_meta.is_final
                     AND weights.total_weight > 0
                     AND weights.elapsed_weight > 0
                    THEN GREATEST(1::NUMERIC, weights.total_weight / weights.elapsed_weight)
                    ELSE 1::NUMERIC
                END AS forecast_factor
            FROM forecast_month_meta month_meta
            CROSS JOIN forecast_business_weights weights
        )
    """
