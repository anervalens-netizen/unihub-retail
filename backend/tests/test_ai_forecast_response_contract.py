"""Adversarial exact request/response contract for AI forecasts."""
from __future__ import annotations

from decimal import Decimal

import pytest
import httpx

from services.ai_forecast_contract import (
    ForecastContractError,
    merge_missing_series_fallback,
    validate_forecast_request,
    validate_forecast_response,
)
from services.forecast_http import ForecastTimeoutError, post_forecast


def request_payload(*, horizon: int = 2) -> dict[str, object]:
    return {
        "horizon": horizon,
        "series_ids": ["S001", "S002"],
        "inputs": [[10.0, 20.0], [30.0]],
        "dynamic_numerical_covariates": {
            "month": [[1, 2, *range(3, 3 + horizon)], [2, *range(3, 3 + horizon)]],
        },
        "dynamic_categorical_covariates": {
            "season": [["a", "b", *(["c"] * horizon)], ["b", *(["c"] * horizon)]],
        },
        "static_categorical_covariates": {"firma": ["A", "B"]},
    }


def quantile_row(point: int, *, layout: int = 9) -> list[float]:
    if layout == 9:
        return [point - 4, point - 3, point - 2, point - 1, point, point + 1, point + 2, point + 3, point + 4]
    return [999, point - 4, point - 3, point - 2, point - 1, point, point + 1, point + 2, point + 3, point + 4]


def response(*, include_second: bool = True) -> dict[str, object]:
    rows: list[dict[str, object]] = [
        {
            "series_id": "S001",
            "point_forecast": [100.005, 110.004],
            "quantile_forecast": [quantile_row(100), quantile_row(110, layout=10)],
        }
    ]
    if include_second:
        rows.append(
            {
                "series_id": "S002",
                "point_forecast": [200, 210],
                "quantile_forecast": [quantile_row(200), quantile_row(210)],
            }
        )
    return {"series": rows}


def test_request_and_both_response_profiles_are_exact() -> None:
    request = validate_forecast_request(request_payload())
    assert request.series_ids == ("S001", "S002")
    assert request.context_lengths == (2, 1)
    assert request.expected_pair_count == 4

    parsed = validate_forecast_response(
        response(),
        request=request,
        metric="sales_value",
        response_profile="point_quantiles_v1",
    )
    assert parsed.model_pair_count == 4
    assert parsed.fallback_pair_count == 0
    assert parsed.predictions["S001"][0].point == Decimal("100.01")
    assert parsed.predictions["S001"][1].point == Decimal("110.00")
    assert parsed.predictions["S001"][0].quantiles == (
        Decimal("96.00"),
        Decimal("97.00"),
        Decimal("100.00"),
        Decimal("103.00"),
        Decimal("104.00"),
    )
    assert len(parsed.raw_response_sha256) == len(parsed.response_sha256) == 64

    point_only = {
        "series": [
            {"series_id": "S001", "point_forecast": [1, 2]},
            {"series_id": "S002", "point_forecast": [3, 4]},
        ]
    }
    parsed_point = validate_forecast_response(
        point_only,
        request=request,
        metric="sales_value",
        response_profile="point_only_v1",
    )
    assert parsed_point.precision_loss_count == 0
    assert parsed_point.predictions["S001"][0].quantiles is None


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(horizon=0), "horizon"),
        (lambda value: value.update(horizon=13), "horizon"),
        (lambda value: value.update(series_ids=[]), "nonempty"),
        (lambda value: value.update(series_ids=["S001", "S001"]), "unique"),
        (lambda value: value.update(inputs=[[1]]), "inputs count"),
        (lambda value: value["inputs"][0].__setitem__(0, float("nan")), "finite"),
        (lambda value: value["inputs"][0].__setitem__(0, -1), "nonnegative"),
        (
            lambda value: value["dynamic_numerical_covariates"]["month"].__setitem__(0, [1]),
            "inner count",
        ),
        (
            lambda value: value["dynamic_categorical_covariates"]["season"].pop(),
            "outer count",
        ),
        (
            lambda value: value["static_categorical_covariates"]["firma"].pop(),
            "count differs",
        ),
    ],
)
def test_request_adversarial_shapes_fail_closed(mutation, message: str) -> None:
    payload = request_payload()
    mutation(payload)
    with pytest.raises(ForecastContractError, match=message):
        validate_forecast_request(payload)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(series=[]), "missing requested"),
        (
            lambda value: value["series"].append(value["series"][0].copy()),
            "duplicate",
        ),
        (
            lambda value: value["series"][0].update(series_id="UNKNOWN"),
            "unknown",
        ),
        (
            lambda value: value["series"][0].update(point_forecast=[1]),
            "length",
        ),
        (
            lambda value: value["series"][0].update(point_forecast=[1, 2, 3]),
            "length",
        ),
        (
            lambda value: value["series"][0]["point_forecast"].__setitem__(0, float("nan")),
            "finite",
        ),
        (
            lambda value: value["series"][0]["point_forecast"].__setitem__(0, float("inf")),
            "finite",
        ),
        (
            lambda value: value["series"][0]["point_forecast"].__setitem__(0, -1),
            "nonnegative",
        ),
        (
            lambda value: value["series"][0].update(quantile_forecast=[]),
            "length",
        ),
        (
            lambda value: value["series"][0]["quantile_forecast"].__setitem__(0, [1] * 8),
            "exactly 9 or 10",
        ),
        (
            lambda value: value["series"][0]["quantile_forecast"].__setitem__(0, [100, 90, 1, 1, 80, 1, 1, 70, 60]),
            "q10 <=",
        ),
        (
            lambda value: value["series"][0]["quantile_forecast"][0].__setitem__(4, float("inf")),
            "finite",
        ),
    ],
)
def test_response_adversarial_values_fail_closed(mutation, message: str) -> None:
    payload = response()
    mutation(payload)
    with pytest.raises(ForecastContractError, match=message):
        validate_forecast_response(
            payload,
            request=validate_forecast_request(request_payload()),
            metric="sales_value",
            response_profile="point_quantiles_v1",
        )


def test_profile_declaration_cannot_be_inferred_or_violated() -> None:
    request = validate_forecast_request(request_payload())
    with pytest.raises(ForecastContractError, match="mandatory"):
        validate_forecast_response(
            response(),
            request=request,
            metric="sales_value",
            response_profile="quantiles_v1",  # type: ignore[arg-type]
        )
    with pytest.raises(ForecastContractError, match="forbids"):
        validate_forecast_response(
            response(),
            request=request,
            metric="sales_value",
            response_profile="point_only_v1",
        )
    point_only = {
        "series": [
            {"series_id": "S001", "point_forecast": [1, 2]},
            {"series_id": "S002", "point_forecast": [3, 4]},
        ]
    }
    with pytest.raises(ForecastContractError, match="quantile_forecast"):
        validate_forecast_response(
            point_only,
            request=request,
            metric="sales_value",
            response_profile="point_quantiles_v1",
        )


def test_units_are_quantized_once_and_precision_loss_is_recorded() -> None:
    request = validate_forecast_request(request_payload(horizon=1))
    parsed = validate_forecast_response(
        {
            "series": [
                {"series_id": "S001", "point_forecast": [1.5]},
                {"series_id": "S002", "point_forecast": [2.49]},
            ]
        },
        request=request,
        metric="units",
        response_profile="point_only_v1",
    )
    assert parsed.predictions["S001"][0].point == Decimal("2")
    assert parsed.predictions["S002"][0].point == Decimal("2")
    assert parsed.precision_loss_count == 2


def test_only_missing_series_may_use_exact_seasonal_fallback() -> None:
    request = validate_forecast_request(request_payload())
    parsed = validate_forecast_response(
        response(include_second=False),
        request=request,
        metric="sales_value",
        response_profile="point_quantiles_v1",
        coverage_mode="seasonal_fallback",
    )
    assert parsed.missing_series_ids == ("S002",)
    assert parsed.model_pair_count == 2
    assert parsed.fallback_pair_count == 2

    completed = merge_missing_series_fallback(
        parsed,
        {"S002": [50, 60]},
        metric="sales_value",
    )
    assert completed.missing_series_ids == ()
    assert completed.predictions["S002"][1].point == Decimal("60.00")
    with pytest.raises(ForecastContractError, match="exactly"):
        merge_missing_series_fallback(
            parsed,
            {"S001": [1, 2]},
            metric="sales_value",
        )


def test_timeout_has_a_typed_fallback_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(*_args, **_kwargs):
        raise httpx.ReadTimeout("late")

    monkeypatch.setattr(httpx, "post", timeout)
    with pytest.raises(ForecastTimeoutError, match="timed out"):
        post_forecast(
            "https://forecast.example.test/predict",
            "test-key",
            {"horizon": 1},
            1,
        )


def test_non_timeout_transport_error_is_not_typed_as_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def transport_error(*_args, **_kwargs):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(httpx, "post", transport_error)
    with pytest.raises(RuntimeError, match="request failed") as error:
        post_forecast(
            "https://forecast.example.test/predict",
            "test-key",
            {"horizon": 1},
            1,
        )
    assert not isinstance(error.value, ForecastTimeoutError)
