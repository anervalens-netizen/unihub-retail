"""Fail-closed request, response and coverage boundary for AI forecasts."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from typing import Any, Literal, Mapping, Sequence


MetricName = Literal["sales_value", "units"]
ResponseProfile = Literal["point_only_v1", "point_quantiles_v1"]
CoverageMode = Literal["fail_closed", "seasonal_fallback"]
QUANTILE_KEYS = ("q10", "q20", "q50", "q80", "q90")


class ForecastContractError(ValueError):
    """Input or model output cannot be accepted as forecast evidence."""


@dataclass(frozen=True, slots=True)
class ForecastRequestContract:
    series_ids: tuple[str, ...]
    context_lengths: tuple[int, ...]
    horizon: int
    request_sha256: str

    @property
    def expected_pair_count(self) -> int:
        return len(self.series_ids) * self.horizon


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    point: Decimal
    quantiles: tuple[Decimal, Decimal, Decimal, Decimal, Decimal] | None


@dataclass(frozen=True, slots=True)
class ForecastResponseContract:
    predictions: Mapping[str, tuple[ForecastPoint, ...]]
    missing_series_ids: tuple[str, ...]
    raw_response_sha256: str
    response_sha256: str
    expected_pair_count: int
    model_pair_count: int
    fallback_pair_count: int
    precision_loss_count: int
    coverage_mode: CoverageMode
    response_profile: ResponseProfile


def canonical_json_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ForecastContractError("forecast evidence is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _decimal(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ForecastContractError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ForecastContractError(f"{field} must be numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ForecastContractError(f"{field} must be finite and nonnegative")
    return parsed


def _sequence(value: Any, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ForecastContractError(f"{field} must be a list")
    return value


def _parse_request_horizon(payload: Mapping[str, Any]) -> int:
    horizon = payload.get("horizon")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 12:
        raise ForecastContractError("horizon must be an integer in 1..12")
    return horizon


def _parse_request_series_ids(payload: Mapping[str, Any]) -> list[str]:
    raw_ids = _sequence(payload.get("series_ids"), field="series_ids")
    if not raw_ids:
        raise ForecastContractError("series_ids must be nonempty")
    series_ids: list[str] = []
    for value in raw_ids:
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ForecastContractError("series_ids must contain trimmed nonempty strings")
        series_ids.append(value)
    if len(set(series_ids)) != len(series_ids):
        raise ForecastContractError("series_ids must be unique")
    return series_ids


def _parse_request_inputs(
    payload: Mapping[str, Any],
    *,
    series_count: int,
) -> list[int]:
    inputs = _sequence(payload.get("inputs"), field="inputs")
    if len(inputs) != series_count:
        raise ForecastContractError("inputs count must equal series_ids count")
    context_lengths: list[int] = []
    for series_index, context in enumerate(inputs):
        values = _sequence(context, field=f"inputs[{series_index}]")
        if not values:
            raise ForecastContractError("every series requires nonempty context")
        for value_index, value in enumerate(values):
            _decimal(value, field=f"inputs[{series_index}][{value_index}]")
        context_lengths.append(len(values))
    return context_lengths


def _check_dynamic_covariates_row(
    *,
    values: list[Any],
    group_name: str,
    covariate_name: str,
    series_index: int,
    expected_length: int,
) -> None:
    if len(values) != expected_length:
        raise ForecastContractError(f"{group_name}.{covariate_name} inner count differs")
    if group_name == "dynamic_numerical_covariates":
        for value_index, value in enumerate(values):
            _decimal(
                value,
                field=(
                    f"{group_name}.{covariate_name}"
                    f"[{series_index}][{value_index}]"
                ),
            )
    elif any(value is None or isinstance(value, (list, dict)) for value in values):
        raise ForecastContractError("categorical covariates must be scalar")


def _parse_dynamic_covariates_group(
    payload: Mapping[str, Any],
    *,
    group_name: str,
    series_count: int,
    context_lengths: Sequence[int],
    horizon: int,
) -> None:
    group = payload.get(group_name, {})
    if not isinstance(group, dict):
        raise ForecastContractError(f"{group_name} must be an object")
    for covariate_name, outer in group.items():
        if not isinstance(covariate_name, str) or not covariate_name:
            raise ForecastContractError(f"{group_name} names must be nonempty")
        rows = _sequence(outer, field=f"{group_name}.{covariate_name}")
        if len(rows) != series_count:
            raise ForecastContractError(f"{group_name}.{covariate_name} outer count differs")
        for series_index, row in enumerate(rows):
            values = _sequence(
                row,
                field=f"{group_name}.{covariate_name}[{series_index}]",
            )
            _check_dynamic_covariates_row(
                values=values,
                group_name=group_name,
                covariate_name=covariate_name,
                series_index=series_index,
                expected_length=context_lengths[series_index] + horizon,
            )


def _parse_dynamic_covariates(
    payload: Mapping[str, Any],
    *,
    series_count: int,
    context_lengths: Sequence[int],
    horizon: int,
) -> None:
    for group_name in (
        "dynamic_categorical_covariates",
        "dynamic_numerical_covariates",
    ):
        _parse_dynamic_covariates_group(
            payload,
            group_name=group_name,
            series_count=series_count,
            context_lengths=context_lengths,
            horizon=horizon,
        )


def _parse_static_covariates(
    payload: Mapping[str, Any],
    *,
    series_count: int,
) -> None:
    static_group = payload.get("static_categorical_covariates", {})
    if not isinstance(static_group, dict):
        raise ForecastContractError("static_categorical_covariates must be an object")
    for covariate_name, values in static_group.items():
        rows = _sequence(values, field=f"static_categorical_covariates.{covariate_name}")
        if len(rows) != series_count:
            raise ForecastContractError(
                f"static_categorical_covariates.{covariate_name} count differs"
            )
        if any(value is None or isinstance(value, (list, dict)) for value in rows):
            raise ForecastContractError("static categorical covariates must be scalar")


def validate_forecast_request(payload: Mapping[str, Any]) -> ForecastRequestContract:
    horizon = _parse_request_horizon(payload)
    series_ids = _parse_request_series_ids(payload)
    context_lengths = _parse_request_inputs(payload, series_count=len(series_ids))
    _parse_dynamic_covariates(
        payload,
        series_count=len(series_ids),
        context_lengths=context_lengths,
        horizon=horizon,
    )
    _parse_static_covariates(payload, series_count=len(series_ids))
    return ForecastRequestContract(
        series_ids=tuple(series_ids),
        context_lengths=tuple(context_lengths),
        horizon=horizon,
        request_sha256=canonical_json_sha256(payload),
    )


def _quantiles(
    values: Any,
    *,
    metric: MetricName,
    field: str,
) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal, Decimal], int]:
    row = _sequence(values, field=field)
    if len(row) == 9:
        indexes = (0, 1, 4, 7, 8)
    elif len(row) == 10:
        indexes = (1, 2, 5, 8, 9)
    else:
        raise ForecastContractError("quantile row must contain exactly 9 or 10 values")
    parsed = [_decimal(value, field=f"{field}[{index}]") for index, value in enumerate(row)]
    selected = (
        parsed[indexes[0]],
        parsed[indexes[1]],
        parsed[indexes[2]],
        parsed[indexes[3]],
        parsed[indexes[4]],
    )
    if tuple(sorted(selected)) != selected:
        raise ForecastContractError("quantiles must satisfy q10 <= q20 <= q50 <= q80 <= q90")
    quantizer = Decimal("0.01") if metric == "sales_value" else Decimal("1")
    quantized = (
        selected[0].quantize(quantizer, rounding=ROUND_HALF_UP),
        selected[1].quantize(quantizer, rounding=ROUND_HALF_UP),
        selected[2].quantize(quantizer, rounding=ROUND_HALF_UP),
        selected[3].quantize(quantizer, rounding=ROUND_HALF_UP),
        selected[4].quantize(quantizer, rounding=ROUND_HALF_UP),
    )
    precision_loss = sum(raw != final for raw, final in zip(selected, quantized, strict=True))
    return quantized, precision_loss


def _validate_response_params(
    metric: MetricName,
    response_profile: ResponseProfile,
    coverage_mode: CoverageMode,
) -> None:
    if metric not in ("sales_value", "units"):
        raise ForecastContractError("unsupported metric")
    if response_profile not in ("point_only_v1", "point_quantiles_v1"):
        raise ForecastContractError("response_profile is mandatory")
    if coverage_mode not in ("fail_closed", "seasonal_fallback"):
        raise ForecastContractError("coverage_mode is mandatory")


def _extract_response_row_quantiles(
    raw_row: dict[str, Any],
    row_index: int,
    *,
    request: ForecastRequestContract,
    response_profile: ResponseProfile,
) -> tuple[list[Any], list[Any] | None]:
    raw_points = _sequence(
        raw_row.get("point_forecast"),
        field=f"series[{row_index}].point_forecast",
    )
    if len(raw_points) != request.horizon:
        raise ForecastContractError("point_forecast length must equal horizon")
    if response_profile == "point_only_v1":
        if "quantile_forecast" in raw_row:
            raise ForecastContractError("point_only_v1 forbids quantile_forecast")
        return raw_points, None
    raw_quantile_rows = _sequence(
        raw_row.get("quantile_forecast"),
        field=f"series[{row_index}].quantile_forecast",
    )
    if len(raw_quantile_rows) != request.horizon:
        raise ForecastContractError("quantile_forecast length must equal horizon")
    return raw_points, raw_quantile_rows


def _quantize_response_points(
    raw_points: list[Any],
    raw_quantile_rows: list[Any] | None,
    *,
    row_index: int,
    metric: MetricName,
    quantizer: Decimal,
) -> tuple[list[ForecastPoint], int]:
    points: list[ForecastPoint] = []
    precision_loss_count = 0
    for point_index, raw_value in enumerate(raw_points):
        value = _decimal(
            raw_value,
            field=f"series[{row_index}].point_forecast[{point_index}]",
        )
        point = value.quantize(quantizer, rounding=ROUND_HALF_UP)
        precision_loss_count += value != point
        quantiles = None
        if raw_quantile_rows is not None:
            quantiles, quantile_loss = _quantiles(
                raw_quantile_rows[point_index],
                metric=metric,
                field=f"series[{row_index}].quantile_forecast[{point_index}]",
            )
            precision_loss_count += quantile_loss
        points.append(ForecastPoint(point=point, quantiles=quantiles))
    return points, precision_loss_count


def _resolve_response_coverage(
    request: ForecastRequestContract,
    parsed_by_id: dict[str, tuple[ForecastPoint, ...]],
    *,
    coverage_mode: CoverageMode,
) -> tuple[tuple[str, ...], dict[str, tuple[ForecastPoint, ...]]]:
    missing = tuple(series_id for series_id in request.series_ids if series_id not in parsed_by_id)
    if missing and coverage_mode == "fail_closed":
        raise ForecastContractError("response is missing requested series")
    ordered_predictions = {
        series_id: parsed_by_id[series_id]
        for series_id in request.series_ids
        if series_id in parsed_by_id
    }
    return missing, ordered_predictions


def _build_quantized_payload(
    ordered_predictions: dict[str, tuple[ForecastPoint, ...]],
) -> dict[str, Any]:
    return {
        "series": [
            {
                "series_id": series_id,
                "points": [
                    {
                        "point": str(point.point),
                        **(
                            {
                                name: str(value)
                                for name, value in zip(
                                    QUANTILE_KEYS,
                                    point.quantiles,
                                    strict=True,
                                )
                            }
                            if point.quantiles is not None
                            else {}
                        ),
                    }
                    for point in points
                ],
            }
            for series_id, points in ordered_predictions.items()
        ]
    }


def validate_forecast_response(
    response: Mapping[str, Any],
    *,
    request: ForecastRequestContract,
    metric: MetricName,
    response_profile: ResponseProfile,
    coverage_mode: CoverageMode = "fail_closed",
) -> ForecastResponseContract:
    _validate_response_params(metric, response_profile, coverage_mode)
    series_rows = _sequence(response.get("series"), field="series")
    requested = set(request.series_ids)
    parsed_by_id: dict[str, tuple[ForecastPoint, ...]] = {}
    precision_loss_count = 0
    quantizer = Decimal("0.01") if metric == "sales_value" else Decimal("1")

    for row_index, raw_row in enumerate(series_rows):
        if not isinstance(raw_row, dict):
            raise ForecastContractError("series rows must be objects")
        series_id = raw_row.get("series_id")
        if not isinstance(series_id, str) or series_id not in requested:
            raise ForecastContractError("response contains an unknown series_id")
        if series_id in parsed_by_id:
            raise ForecastContractError("response contains a duplicate series_id")
        raw_points, raw_quantile_rows = _extract_response_row_quantiles(
            raw_row,
            row_index,
            request=request,
            response_profile=response_profile,
        )
        points, row_loss = _quantize_response_points(
            raw_points,
            raw_quantile_rows,
            row_index=row_index,
            metric=metric,
            quantizer=quantizer,
        )
        precision_loss_count += row_loss
        parsed_by_id[series_id] = tuple(points)

    missing, ordered_predictions = _resolve_response_coverage(
        request,
        parsed_by_id,
        coverage_mode=coverage_mode,
    )
    quantized_payload = _build_quantized_payload(ordered_predictions)
    return ForecastResponseContract(
        predictions=ordered_predictions,
        missing_series_ids=missing,
        raw_response_sha256=canonical_json_sha256(response),
        response_sha256=canonical_json_sha256(quantized_payload),
        expected_pair_count=request.expected_pair_count,
        model_pair_count=sum(len(points) for points in ordered_predictions.values()),
        fallback_pair_count=len(missing) * request.horizon,
        precision_loss_count=precision_loss_count,
        coverage_mode=coverage_mode,
        response_profile=response_profile,
    )


def merge_missing_series_fallback(
    contract: ForecastResponseContract,
    fallback: Mapping[str, list[Any]],
    *,
    metric: MetricName,
) -> ForecastResponseContract:
    if contract.coverage_mode != "seasonal_fallback":
        raise ForecastContractError("fallback requires seasonal_fallback coverage mode")
    if set(fallback) != set(contract.missing_series_ids):
        raise ForecastContractError("fallback must cover exactly the missing series")
    quantizer = Decimal("0.01") if metric == "sales_value" else Decimal("1")
    predictions = dict(contract.predictions)
    loss_count = contract.precision_loss_count
    for series_id in contract.missing_series_ids:
        values = _sequence(fallback[series_id], field=f"fallback.{series_id}")
        expected_horizon = contract.fallback_pair_count // max(len(fallback), 1)
        if len(values) != expected_horizon:
            raise ForecastContractError("fallback length must equal horizon")
        points: list[ForecastPoint] = []
        for index, raw_value in enumerate(values):
            value = _decimal(raw_value, field=f"fallback.{series_id}[{index}]")
            quantized = value.quantize(quantizer, rounding=ROUND_HALF_UP)
            loss_count += value != quantized
            points.append(ForecastPoint(point=quantized, quantiles=None))
        predictions[series_id] = tuple(points)
    return ForecastResponseContract(
        predictions=predictions,
        missing_series_ids=(),
        raw_response_sha256=contract.raw_response_sha256,
        response_sha256=contract.response_sha256,
        expected_pair_count=contract.expected_pair_count,
        model_pair_count=contract.model_pair_count,
        fallback_pair_count=contract.fallback_pair_count,
        precision_loss_count=loss_count,
        coverage_mode=contract.coverage_mode,
        response_profile=contract.response_profile,
    )
