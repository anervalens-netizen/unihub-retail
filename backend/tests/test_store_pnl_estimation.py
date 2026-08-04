from datetime import date
from decimal import Decimal

from scripts.estimate_store_pnl import (
    CATEGORY_NAMES,
    REVENUE_CODES,
    build_estimates,
    all_missing_targets,
    estimate_replacement_scopes,
    predict_amount,
)


def test_variable_cost_scales_with_sales() -> None:
    history = [(date(2025, 1, 1), 100.0), (date(2025, 2, 1), 200.0)]
    sales = {date(2025, 1, 1): 1000.0, date(2025, 2, 1): 2000.0}
    assert predict_amount("c11", date(2025, 3, 1), history, sales, {}, 3000.0, 0.0) == 300.0


def test_salary_cost_uses_observed_gross_to_net_ratio() -> None:
    history = [(date(2025, 1, 1), 150.0), (date(2025, 2, 1), 300.0)]
    salaries = {date(2025, 1, 1): 100.0, date(2025, 2, 1): 200.0}
    assert predict_amount("c3", date(2025, 3, 1), history, {}, salaries, 0.0, 300.0) == 450.0


def test_existing_finance_store_month_is_never_supplemented() -> None:
    period = date(2026, 3, 1)
    actual = [{
        "company_name": "Mobicell", "period": period, "source_site_code": "ACTUAL",
        "source_location_name": "Actual store", "site_code": "ACTUAL", "category_code": "v11",
        "category_name": CATEGORY_NAMES["v11"], "amount": Decimal("100.00"),
    }]
    sales = [{"company_name": "Mobicell", "period": period, "site_code": "ACTUAL", "amount": 1_000.0}]
    stores = [{"site_code": "ACTUAL", "locatie": "Actual store", "firma": "MobiCell"}]

    estimates = build_estimates(actual, sales, [], stores, {("Mobicell", period, "ACTUAL")}, causal=False)

    assert estimates == []


def test_all_missing_targets_keeps_sales_for_stores_without_finance_actual() -> None:
    period = date(2026, 3, 1)
    actual = [
        {
            "company_name": "Mobicell",
            "period": period,
            "site_code": "ACTUAL",
        }
    ]
    sales = [
        {"company_name": "Mobicell", "period": period, "site_code": "ACTUAL", "amount": 1_000},
        {"company_name": "Mobicell", "period": period, "site_code": "MISSING", "amount": 2_000},
    ]

    assert all_missing_targets(actual, sales, input_cutoff=date(2026, 4, 1)) == {
        ("Mobicell", period, "MISSING")
    }


def test_missing_store_revenue_equals_sales_without_vat() -> None:
    reference_period = date(2026, 2, 1)
    target_period = date(2026, 3, 1)
    actual = [
        {
            "company_name": "Mobicell", "period": reference_period, "source_site_code": "REFERENCE",
            "source_location_name": "Reference", "site_code": "REFERENCE", "category_code": category,
            "category_name": CATEGORY_NAMES[category], "amount": Decimal("100.00"),
        }
        for category in CATEGORY_NAMES
    ]
    sales = [
        {"company_name": "Mobicell", "period": reference_period, "site_code": "REFERENCE", "amount": 1_200.0},
        {"company_name": "Mobicell", "period": target_period, "site_code": "MISSING", "amount": 1_000.0},
    ]
    stores = [
        {"site_code": "REFERENCE", "locatie": "Reference", "firma": "MobiCell"},
        {"site_code": "MISSING", "locatie": "Missing", "firma": "MobiCell"},
    ]

    estimates = build_estimates(actual, sales, [], stores, {("Mobicell", target_period, "MISSING")}, causal=False)

    assert sum(item.amount for item in estimates if item.category_code in REVENUE_CODES) == Decimal("1000.00")


def test_estimate_replacement_scope_keeps_company_boundary() -> None:
    targets = {
        ("Mobiup", date(2026, 3, 1), "SITE-A"),
        ("Mobiup", date(2026, 3, 1), "SITE-B"),
        ("Mobicell", date(2026, 4, 1), "SITE-C"),
    }

    assert estimate_replacement_scopes(targets) == [
        ("Mobicell", date(2026, 4, 1)),
        ("Mobiup", date(2026, 3, 1)),
    ]
