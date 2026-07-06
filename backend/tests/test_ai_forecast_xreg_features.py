from __future__ import annotations

from decimal import Decimal

from scripts.run_ai_forecast_xreg import StoreInfo, build_payload, month_range


def test_v2_payload_adds_calendar_business_covariates() -> None:
    store = StoreInfo(
        site_code="S001",
        locatie="Store 1",
        firma="Mobiup",
        regional="RM 1",
        asm="ASM 1",
    )
    history_months = month_range("2023-10", "2026-06")
    sales = {("S001", month): Decimal("100") for month in history_months}

    payload, meta_rows, skipped = build_payload(
        stores=[store],
        sales=sales,
        target_months=["2026-07"],
        source_month="2026-06",
        history_start_month="2023-10",
        min_context=33,
        metric="sales_value",
        feature_profile="v2",
    )

    assert not skipped
    assert meta_rows[0]["context_months"] == 33
    assert payload["feature_profile"] == "v2"
    assert set(payload["dynamic_categorical_covariates"]) == {"month", "quarter", "season", "price_regime"}
    assert "year" not in payload["dynamic_categorical_covariates"]
    assert payload["dynamic_categorical_covariates"]["season"][0][-1] == "summer"
    assert payload["dynamic_categorical_covariates"]["price_regime"][0][-1] == "post_price_change"
    assert payload["dynamic_numerical_covariates"]["is_summer"][0][-1] == 1.0
    assert payload["dynamic_numerical_covariates"]["months_since_opening"][0][0] == 1.0
    assert payload["dynamic_numerical_covariates"]["months_since_opening"][0][-1] == 34.0
    assert payload["static_categorical_covariates"]["store_age_bucket"] == ["24_47m"]


def test_v1_payload_keeps_legacy_covariate_schema() -> None:
    store = StoreInfo(
        site_code="S001",
        locatie="Store 1",
        firma="Mobiup",
        regional="RM 1",
        asm="ASM 1",
    )
    history_months = month_range("2023-10", "2026-06")
    sales = {("S001", month): Decimal("100") for month in history_months}

    payload, _, skipped = build_payload(
        stores=[store],
        sales=sales,
        target_months=["2026-07"],
        source_month="2026-06",
        history_start_month="2023-10",
        min_context=33,
        metric="sales_value",
    )

    assert not skipped
    assert payload["feature_profile"] == "v1"
    assert set(payload["dynamic_categorical_covariates"]) == {"month", "quarter", "year"}
    assert set(payload["static_categorical_covariates"]) == {"firma", "regional", "asm"}
    assert "is_summer" not in payload["dynamic_numerical_covariates"]
