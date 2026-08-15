from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
from typing import Any, Literal
from uuid import UUID

import asyncpg
from dotenv import find_dotenv, load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from business_clock import business_now


MetricName = Literal["sales_value", "units"]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ForecastImportLineage:
    cohort_snapshot_id: UUID
    request_sha256: str
    raw_response_sha256: str
    response_sha256: str
    expected_pair_count: int
    model_pair_count: int
    fallback_pair_count: int
    precision_loss_count: int
    coverage_mode: Literal["fail_closed", "seasonal_fallback"]
    response_profile: Literal["point_only_v1", "point_quantiles_v1"]


def _canonical_json_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Manifestul de lineage AI nu este JSON canonic") from exc
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_lineage_target(target_month: str, raw: object) -> ForecastImportLineage:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", target_month):
        raise RuntimeError("Manifestul de lineage AI contine luna invalida")
    if not isinstance(raw, dict):
        raise RuntimeError("Lineage-ul unei luni trebuie sa fie obiect")
    lineage = _materialize_lineage_target(raw)
    _validate_lineage_hashes(lineage)
    _validate_lineage_counts(lineage)
    _validate_lineage_profiles(lineage)
    return lineage


def _materialize_lineage_target(raw: Any) -> ForecastImportLineage:
    try:
        count_values: dict[str, Any] = {
            name: raw[name]
            for name in (
                "expected_pair_count",
                "model_pair_count",
                "fallback_pair_count",
                "precision_loss_count",
            )
        }
        if any(isinstance(value, bool) or not isinstance(value, int) for value in count_values.values()):
            raise TypeError("lineage counts must be integers")
        return ForecastImportLineage(
            cohort_snapshot_id=UUID(str(raw["cohort_snapshot_id"])),
            request_sha256=str(raw["request_sha256"]),
            raw_response_sha256=str(raw["raw_response_sha256"]),
            response_sha256=str(raw["response_sha256"]),
            expected_pair_count=count_values["expected_pair_count"],
            model_pair_count=count_values["model_pair_count"],
            fallback_pair_count=count_values["fallback_pair_count"],
            precision_loss_count=count_values["precision_loss_count"],
            coverage_mode=str(raw["coverage_mode"]),  # type: ignore[arg-type]
            response_profile=str(raw["response_profile"]),  # type: ignore[arg-type]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Lineage-ul unei luni este incomplet") from exc


def _validate_lineage_hashes(lineage: ForecastImportLineage) -> None:
    if not all(
        SHA256_RE.fullmatch(value)
        for value in (
            lineage.request_sha256,
            lineage.raw_response_sha256,
            lineage.response_sha256,
        )
    ):
        raise RuntimeError("Hash-urile lineage AI trebuie sa fie SHA-256 lowercase")


def _validate_lineage_counts(lineage: ForecastImportLineage) -> None:
    if (
        lineage.expected_pair_count <= 0
        or lineage.model_pair_count < 0
        or lineage.fallback_pair_count < 0
        or lineage.precision_loss_count < 0
        or lineage.model_pair_count + lineage.fallback_pair_count
        != lineage.expected_pair_count
    ):
        raise RuntimeError("Contoarele lineage AI nu reconciliaza acoperirea exacta")


def _validate_lineage_profiles(lineage: ForecastImportLineage) -> None:
    if lineage.coverage_mode not in ("fail_closed", "seasonal_fallback"):
        raise RuntimeError("coverage_mode AI este invalid")
    if lineage.response_profile not in ("point_only_v1", "point_quantiles_v1"):
        raise RuntimeError("response_profile AI este invalid")
    if lineage.coverage_mode == "fail_closed" and lineage.fallback_pair_count:
        raise RuntimeError("fail_closed nu permite fallback")


def load_lineage_manifest(path: Path) -> tuple[dict[str, ForecastImportLineage], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Manifestul de lineage AI nu este JSON valid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("Manifestul de lineage AI are versiune invalida")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, dict) or not raw_targets:
        raise RuntimeError("Manifestul de lineage AI nu contine tinte")
    targets = {
        target_month: _parse_lineage_target(target_month, raw)
        for target_month, raw in raw_targets.items()
    }
    return targets, _canonical_json_sha256(payload)


def _check_target_month_format(target_month: str) -> None:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", target_month):
        raise RuntimeError("CSV-ul AI contine target_month invalid")


def _check_source_month_format(source_month: str) -> None:
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", source_month):
        raise RuntimeError("CSV-ul AI necesita source_month exact pe fiecare rand")


def _check_site_code(site_code: str) -> None:
    if not site_code or len(site_code) > 80:
        raise RuntimeError("CSV-ul AI contine site_code invalid")


def _check_method(method: str) -> None:
    if method != "model_xreg" and not method.startswith("fallback_"):
        raise RuntimeError("CSV-ul AI necesita metoda explicita model_xreg/fallback_*")


def _parse_forecast_value(raw_value: object, *, metric: MetricName) -> Decimal:
    if raw_value is None or str(raw_value).strip() == "":
        raise RuntimeError("CSV-ul AI contine forecast lipsa")
    try:
        value = Decimal(str(raw_value))
    except Exception as exc:
        raise RuntimeError("CSV-ul AI contine forecast invalid") from exc
    if not value.is_finite() or value < 0:
        raise RuntimeError("CSV-ul AI contine forecast ne-finit sau negativ")
    if metric == "units" and value != value.to_integral_value():
        raise RuntimeError("CSV-ul AI pentru units accepta numai valori integrale")
    return value


def _record_forecast_row(
    row: dict[str, str],
    *,
    seen: set[tuple[str, str]],
    source_by_target: dict[str, set[str]],
    metric: MetricName,
) -> None:
    target_month = (row.get("target_month") or "").strip()
    source_month = (row.get("source_month") or "").strip()
    site_code = (row.get("site_code") or "").strip()
    _check_target_month_format(target_month)
    _check_source_month_format(source_month)
    _check_site_code(site_code)
    key = (target_month, site_code)
    if key in seen:
        raise RuntimeError("CSV-ul AI contine pereche target_month/site_code duplicata")
    seen.add(key)
    source_by_target[target_month].add(source_month)
    _parse_forecast_value(row.get("forecast"), metric=metric)
    _check_method((row.get("method") or "").strip())


def validate_forecast_rows(
    rows: list[dict[str, str]],
    *,
    metric: MetricName,
    horizon: str,
    anchor_month: str | None,
) -> None:
    if not rows:
        raise RuntimeError("Forecastul AI nu contine randuri")
    seen: set[tuple[str, str]] = set()
    source_by_target: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        _record_forecast_row(
            row,
            seen=seen,
            source_by_target=source_by_target,
            metric=metric,
        )
    if any(len(sources) != 1 for sources in source_by_target.values()):
        raise RuntimeError("Fiecare luna tinta necesita o singura luna sursa")
    if anchor_month is not None and not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", anchor_month):
        raise RuntimeError("anchor_month trebuie sa fie YYYY-MM")
    if horizon == "rolling_12m" and not anchor_month:
        raise RuntimeError("rolling_12m necesita anchor_month")


def validate_row_counts(
    rows: list[dict[str, str]],
    *,
    lineage: ForecastImportLineage,
) -> None:
    model_count = sum(row["method"] == "model_xreg" for row in rows)
    fallback_count = sum(row["method"].startswith("fallback_") for row in rows)
    if (
        len(rows) != lineage.expected_pair_count
        or model_count != lineage.model_pair_count
        or fallback_count != lineage.fallback_pair_count
    ):
        raise RuntimeError("CSV-ul AI nu reconciliaza contoarele model/fallback din lineage")


async def validate_month_lineage(
    connection: asyncpg.Connection,
    *,
    target_month: str,
    rows: list[dict[str, str]],
    lineage: ForecastImportLineage,
) -> None:
    snapshot = await connection.fetchrow(
        """
        SELECT source_month, target_month, expected_pair_count, state
        FROM ai_forecast_cohort_snapshots
        WHERE id = $1
        """,
        lineage.cohort_snapshot_id,
    )
    if snapshot is None or snapshot["state"] != "sealed":
        raise RuntimeError("Importul AI necesita cohorta sigilata")
    source_months = {str(row["source_month"]) for row in rows}
    if (
        snapshot["target_month"] != target_month
        or source_months != {str(snapshot["source_month"])}
        or int(snapshot["expected_pair_count"]) != lineage.expected_pair_count
    ):
        raise RuntimeError("Lineage-ul AI nu corespunde cohortei/lunilor")
    cohort_rows = await connection.fetch(
        """
        SELECT site_code, is_operating, confidence
        FROM ai_forecast_cohort_rows
        WHERE snapshot_id = $1
        """,
        lineage.cohort_snapshot_id,
    )
    if any(str(row["confidence"]) != "confirmed" for row in cohort_rows):
        raise RuntimeError("Cohorta AI contine autoritate necunoscuta/ambigua")
    expected_sites = {
        str(row["site_code"])
        for row in cohort_rows
        if bool(row["is_operating"])
    }
    actual_sites = {str(row["site_code"]) for row in rows}
    if actual_sites != expected_sites or len(rows) != lineage.expected_pair_count:
        raise RuntimeError("CSV-ul AI nu acopera exact perechile cohortei")


def month_dates(month: str) -> list[date]:
    year, month_number = map(int, month.split("-"))
    start = date(year, month_number, 1)
    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    days = (end - start).days
    return [start + timedelta(days=offset) for offset in range(days)]


def metric_value(value: Decimal, metric: MetricName) -> Decimal:
    quantizer = Decimal("1") if metric == "units" else Decimal("0.01")
    return value.quantize(quantizer, rounding=ROUND_HALF_UP)


def parse_decimal(value: str | None) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def weekday_occurrence(day: date) -> int:
    occurrence = 0
    for month_day in month_dates(day.strftime("%Y-%m")):
        if month_day > day:
            break
        if month_day.weekday() == day.weekday():
            occurrence += 1
    return occurrence


async def fetch_daily_weights(
    conn: asyncpg.Connection,
    *,
    reference_month: str,
    forecast_month: str,
    site_codes: list[str],
    metric: MetricName,
) -> dict[str, list[tuple[date, Decimal]]]:
    forecast_dates = month_dates(forecast_month)
    metric_column = "total_quantity" if metric == "units" else "total_sales"
    rows = await conn.fetch(
        f"""
        SELECT site_code, sale_date, COALESCE(SUM({metric_column}), 0)::NUMERIC(14, 2) AS total_metric
        FROM reporting_agent_day
        WHERE import_month = $1
          AND site_code = ANY($2::TEXT[])
        GROUP BY site_code, sale_date
        """,
        reference_month,
        site_codes,
    )
    by_site_day: dict[str, dict[date, Decimal]] = defaultdict(dict)
    for row in rows:
        by_site_day[row["site_code"]][row["sale_date"]] = row["total_metric"]

    weights: dict[str, list[tuple[date, Decimal]]] = {}
    uniform = Decimal("1") / Decimal(len(forecast_dates))
    for site_code in site_codes:
        reference_values = by_site_day.get(site_code, {})
        if sum(reference_values.values(), Decimal("0")) <= 0:
            weights[site_code] = [(day, uniform) for day in forecast_dates]
            continue

        by_weekday_occurrence: dict[tuple[int, int], Decimal] = {}
        weekday_totals: dict[int, Decimal] = defaultdict(Decimal)
        weekday_counts: dict[int, int] = defaultdict(int)
        for reference_date, value in reference_values.items():
            weekday = reference_date.weekday()
            by_weekday_occurrence[(weekday, weekday_occurrence(reference_date))] = value
            weekday_totals[weekday] += value
            weekday_counts[weekday] += 1

        projected_values: list[tuple[date, Decimal]] = []
        for forecast_date in forecast_dates:
            weekday = forecast_date.weekday()
            occurrence = weekday_occurrence(forecast_date)
            projected = by_weekday_occurrence.get((weekday, occurrence))
            if projected is None and weekday_counts[weekday] > 0:
                projected = weekday_totals[weekday] / Decimal(weekday_counts[weekday])
            projected_values.append((forecast_date, projected or Decimal("0")))

        projected_total = sum((value for _, value in projected_values), Decimal("0"))
        if projected_total <= 0:
            weights[site_code] = [(day, uniform) for day in forecast_dates]
            continue

        site_weights: list[tuple[date, Decimal]] = []
        for forecast_date, value in projected_values:
            site_weights.append((forecast_date, value / projected_total))
        weights[site_code] = site_weights
    return weights


def load_forecast_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    forecast_rows: list[dict[str, str]] = []
    with Path(args.csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_metric = row.get("metric")
            if row_metric and row_metric != args.metric:
                continue
            if row.get("target_month"):
                target_month = row["target_month"]
                if args.start_month and target_month < args.start_month:
                    continue
                if args.end_month and target_month > args.end_month:
                    continue
                forecast_value = row.get("forecast") or row.get("forecast_sales")
                if forecast_value is None:
                    continue
                forecast_rows.append(
                    {
                        **row,
                        "target_month": target_month,
                        "forecast": forecast_value,
                    }
                )
            elif row.get("scenario") == args.scenario and row.get("mode") == args.mode:
                if not args.forecast_month:
                    raise RuntimeError("--forecast-month este necesar pentru CSV-ul legacy fara target_month")
                forecast_rows.append(
                    {
                        **row,
                        "target_month": args.forecast_month,
                        "forecast": row["forecast"],
                    }
                )
    if not forecast_rows:
        raise RuntimeError("Nu am gasit randuri de forecast pentru filtrele cerute.")
    return forecast_rows


_LINEAGE_TUPLE_FIELDS: tuple[str, ...] = (
    "cohort_snapshot_id",
    "request_sha256",
    "raw_response_sha256",
    "response_sha256",
    "expected_pair_count",
    "model_pair_count",
    "fallback_pair_count",
    "precision_loss_count",
    "coverage_mode",
    "response_profile",
)


def _resolve_database_url() -> str:
    load_dotenv(find_dotenv())
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL lipseste din .env")
    return database_url


def _group_rows_by_target_month(
    forecast_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    rows_by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in forecast_rows:
        rows_by_month[row["target_month"]].append(row)
    return rows_by_month


def _assert_lineage_matches_rows(
    args: argparse.Namespace,
    *,
    rows_by_month: dict[str, list[dict[str, str]]],
    lineage_by_month: dict[str, "ForecastImportLineage"],
    lineage_manifest_sha256: str,
) -> None:
    if args.expected_lineage_sha256 and args.expected_lineage_sha256 != lineage_manifest_sha256:
        raise RuntimeError("Hash-ul manifestului lineage AI nu corespunde")
    if set(rows_by_month) != set(lineage_by_month):
        raise RuntimeError("Lunile CSV si manifestul lineage AI trebuie sa coincida exact")
    if args.source_month is not None and any(
        {str(row["source_month"]) for row in rows} != {args.source_month}
        for rows in rows_by_month.values()
    ):
        raise RuntimeError("--source-month nu corespunde sursei exacte din CSV")


async def _fetch_existing_forecast_run(
    conn: asyncpg.Connection,
    *,
    target_month: str,
    args: argparse.Namespace,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT id, cohort_snapshot_id, request_sha256,
               raw_response_sha256, response_sha256,
               expected_pair_count, model_pair_count,
               fallback_pair_count, precision_loss_count,
               coverage_mode, response_profile
        FROM ai_forecast_runs
        WHERE forecast_month = $1
          AND model_name = $2
          AND model_mode = $3
          AND variant = $4
          AND metric = $5
          AND horizon = $6
          AND status = 'completed'
        ORDER BY generated_at DESC, id DESC
        LIMIT 1
        """,
        target_month,
        args.model_name,
        args.mode,
        args.variant,
        args.metric,
        args.horizon,
    )


def _existing_lineage_tuple(record: asyncpg.Record) -> tuple[Any, ...]:
    return tuple(record[name] for name in _LINEAGE_TUPLE_FIELDS)


def _requested_lineage_tuple(lineage: "ForecastImportLineage") -> tuple[Any, ...]:
    return (
        lineage.cohort_snapshot_id,
        lineage.request_sha256,
        lineage.raw_response_sha256,
        lineage.response_sha256,
        lineage.expected_pair_count,
        lineage.model_pair_count,
        lineage.fallback_pair_count,
        lineage.precision_loss_count,
        lineage.coverage_mode,
        lineage.response_profile,
    )


async def _reuse_existing_run_if_duplicate(
    conn: asyncpg.Connection,
    *,
    target_month: str,
    args: argparse.Namespace,
    lineage: "ForecastImportLineage",
) -> int | None:
    existing = await _fetch_existing_forecast_run(
        conn,
        target_month=target_month,
        args=args,
    )
    if existing is None:
        return None
    if _existing_lineage_tuple(existing) != _requested_lineage_tuple(lineage):
        raise RuntimeError("Forecast existent cu lineage diferit; reimportul este interzis")
    print(f"Forecast AI identic deja importat pentru {target_month}: run_id={existing['id']}")
    return int(existing["id"])


async def _fetch_daily_weights_if_current(
    conn: asyncpg.Connection,
    *,
    args: argparse.Namespace,
    target_month: str,
    site_codes: list[str],
) -> dict[str, list[tuple[date, Decimal]]]:
    if args.horizon != "current_month":
        return {}
    return await fetch_daily_weights(
        conn,
        reference_month=args.daily_profile_month,
        forecast_month=target_month,
        site_codes=site_codes,
        metric=args.metric,
    )


def _build_import_metadata(
    args: argparse.Namespace,
    *,
    csv_path: Path,
    csv_sha256: str,
    lineage_manifest_sha256: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "imported_from": csv_path.name,
        "csv_sha256": csv_sha256,
        "lineage_manifest": args.lineage_manifest.name,
        "lineage_manifest_sha256": lineage_manifest_sha256,
        "scenario": args.scenario,
        "metric": args.metric,
        "horizon": args.horizon,
    }
    if args.anchor_month:
        metadata["anchor_month"] = args.anchor_month
    if args.horizon == "current_month":
        metadata["daily_profile_month"] = args.daily_profile_month
        metadata["daily_profile_method"] = "weekday_occurrence_share"
    return metadata


async def _insert_forecast_run(
    conn: asyncpg.Connection,
    *,
    target_month: str,
    args: argparse.Namespace,
    source_month: str,
    lineage: "ForecastImportLineage",
    metadata: dict[str, Any],
) -> int:
    return int(await conn.fetchval(
        """
        INSERT INTO ai_forecast_runs (
            forecast_month, source_month, metric, horizon, model_name, model_mode,
            variant, status, generated_at, metadata,
            cohort_snapshot_id, request_sha256, raw_response_sha256,
            response_sha256, expected_pair_count, model_pair_count,
            fallback_pair_count, precision_loss_count, coverage_mode,
            response_profile
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, 'completed', $8, $9::JSONB,
            $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
        )
        RETURNING id
        """,
        target_month,
        source_month,
        args.metric,
        args.horizon,
        args.model_name,
        args.mode,
        args.variant,
        business_now(),
        json.dumps(metadata),
        lineage.cohort_snapshot_id,
        lineage.request_sha256,
        lineage.raw_response_sha256,
        lineage.response_sha256,
        lineage.expected_pair_count,
        lineage.model_pair_count,
        lineage.fallback_pair_count,
        lineage.precision_loss_count,
        lineage.coverage_mode,
        lineage.response_profile,
    ))


def _build_daily_allocations(
    forecast_sales: Decimal,
    site_weights: list[tuple[date, Decimal]],
    *,
    metric: MetricName,
) -> list[tuple[date, Decimal]]:
    daily_allocations: list[tuple[date, Decimal]] = []
    running = Decimal("0")
    for forecast_date, weight in site_weights[:-1]:
        value = metric_value(forecast_sales * weight, metric)
        running += value
        daily_allocations.append((forecast_date, value))
    last_date, _ = site_weights[-1]
    daily_allocations.append((last_date, metric_value(forecast_sales - running, metric)))
    return daily_allocations


async def _persist_store_rows(
    conn: asyncpg.Connection,
    *,
    run_id: int,
    args: argparse.Namespace,
    month_rows: list[dict[str, str]],
    weights: dict[str, list[tuple[date, Decimal]]],
) -> None:
    for row in month_rows:
        site_code = row["site_code"]
        forecast_sales = metric_value(parse_decimal(row["forecast"]), args.metric)
        await conn.execute(
            """
            INSERT INTO ai_forecast_store_month (run_id, site_code, forecast_sales, metadata)
            VALUES ($1, $2, $3, $4::JSONB)
            """,
            run_id,
            site_code,
            forecast_sales,
            json.dumps({"locatie": row.get("locatie"), "firma": row.get("firma")}),
        )
        if args.horizon == "current_month":
            daily_allocations = _build_daily_allocations(
                forecast_sales,
                weights[site_code],
                metric=args.metric,
            )
            await conn.executemany(
                """
                INSERT INTO ai_forecast_store_day (run_id, forecast_date, site_code, forecast_sales)
                VALUES ($1, $2, $3, $4)
                """,
                [(run_id, forecast_date, site_code, value) for forecast_date, value in daily_allocations],
            )


async def _reconcile_persisted_count(
    conn: asyncpg.Connection,
    *,
    run_id: int,
    expected: int,
) -> None:
    persisted_count = await conn.fetchval(
        "SELECT count(*) FROM ai_forecast_store_month WHERE run_id = $1",
        run_id,
    )
    if int(persisted_count) != expected:
        raise RuntimeError("Persistenta AI nu reconciliaza numarul asteptat de perechi")


async def _persist_target_month(
    conn: asyncpg.Connection,
    *,
    args: argparse.Namespace,
    target_month: str,
    month_rows: list[dict[str, str]],
    lineage: "ForecastImportLineage",
    csv_path: Path,
    csv_sha256: str,
    lineage_manifest_sha256: str,
) -> int:
    validate_row_counts(month_rows, lineage=lineage)
    await validate_month_lineage(
        conn,
        target_month=target_month,
        rows=month_rows,
        lineage=lineage,
    )
    site_codes = [row["site_code"] for row in month_rows]
    existing_run_id = await _reuse_existing_run_if_duplicate(
        conn,
        target_month=target_month,
        args=args,
        lineage=lineage,
    )
    if existing_run_id is not None:
        return existing_run_id

    weights = await _fetch_daily_weights_if_current(
        conn,
        args=args,
        target_month=target_month,
        site_codes=site_codes,
    )
    metadata = _build_import_metadata(
        args,
        csv_path=csv_path,
        csv_sha256=csv_sha256,
        lineage_manifest_sha256=lineage_manifest_sha256,
    )
    source_month = str(month_rows[0]["source_month"])
    run_id = await _insert_forecast_run(
        conn,
        target_month=target_month,
        args=args,
        source_month=source_month,
        lineage=lineage,
        metadata=metadata,
    )
    await _persist_store_rows(
        conn,
        run_id=run_id,
        args=args,
        month_rows=month_rows,
        weights=weights,
    )
    await _reconcile_persisted_count(conn, run_id=run_id, expected=lineage.expected_pair_count)
    return run_id


async def _persist_forecast_runs(
    database_url: str,
    *,
    args: argparse.Namespace,
    rows_by_month: dict[str, list[dict[str, str]]],
    lineage_by_month: dict[str, "ForecastImportLineage"],
    csv_path: Path,
    csv_sha256: str,
    lineage_manifest_sha256: str,
) -> list[int]:
    conn = await asyncpg.connect(database_url)
    imported_run_ids: list[int] = []
    try:
        async with conn.transaction():
            for target_month in sorted(rows_by_month):
                run_id = await _persist_target_month(
                    conn,
                    args=args,
                    target_month=target_month,
                    month_rows=rows_by_month[target_month],
                    lineage=lineage_by_month[target_month],
                    csv_path=csv_path,
                    csv_sha256=csv_sha256,
                    lineage_manifest_sha256=lineage_manifest_sha256,
                )
                imported_run_ids.append(run_id)
    finally:
        await conn.close()
    return imported_run_ids


async def import_forecast(args: argparse.Namespace) -> int:
    database_url = _resolve_database_url()
    if args.replace:
        raise RuntimeError("Run-urile AI cu lineage sunt append-only; --replace este interzis")

    forecast_rows = load_forecast_rows(args)
    validate_forecast_rows(
        forecast_rows,
        metric=args.metric,
        horizon=args.horizon,
        anchor_month=args.anchor_month,
    )
    rows_by_month = _group_rows_by_target_month(forecast_rows)
    lineage_by_month, lineage_manifest_sha256 = load_lineage_manifest(args.lineage_manifest)
    _assert_lineage_matches_rows(
        args,
        rows_by_month=rows_by_month,
        lineage_by_month=lineage_by_month,
        lineage_manifest_sha256=lineage_manifest_sha256,
    )
    csv_path = Path(args.csv)
    csv_sha256 = _file_sha256(csv_path)

    imported_run_ids = await _persist_forecast_runs(
        database_url,
        args=args,
        rows_by_month=rows_by_month,
        lineage_by_month=lineage_by_month,
        csv_path=csv_path,
        csv_sha256=csv_sha256,
        lineage_manifest_sha256=lineage_manifest_sha256,
    )

    print(f"Importat forecast AI run_ids={imported_run_ids}, randuri={len(forecast_rows)}")
    return imported_run_ids[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa un forecast AI lunar in tabelele Retail.")
    parser.add_argument("--csv", required=True, help="CSV-ul cu randuri per magazin")
    parser.add_argument("--forecast-month", default=None)
    parser.add_argument("--start-month", default=None)
    parser.add_argument("--end-month", default=None)
    parser.add_argument("--source-month", default=None)
    parser.add_argument("--anchor-month", default=None)
    parser.add_argument("--metric", choices=["sales_value", "units"], default="sales_value")
    parser.add_argument("--horizon", choices=["current_month", "rolling_12m"], default="current_month")
    parser.add_argument("--scenario", default="forecast_2026_07_june_scaled")
    parser.add_argument("--mode", default="xreg + timesfm")
    parser.add_argument("--variant", default="monthly_xreg_june_scaled")
    parser.add_argument("--model-name", default="timesfm-2.5-200m-pytorch")
    parser.add_argument("--daily-profile-month", default="2025-07")
    parser.add_argument(
        "--lineage-manifest",
        type=Path,
        required=True,
        help="Manifestul canonic cu cohorta, hash-urile raspunsului si contoarele per luna.",
    )
    parser.add_argument(
        "--expected-lineage-sha256",
        default=None,
        help="Hash SHA-256 optional, calculat peste JSON-ul canonic al manifestului.",
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    asyncio.run(import_forecast(args))


if __name__ == "__main__":
    main()
