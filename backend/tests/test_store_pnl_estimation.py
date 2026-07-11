from datetime import date

from scripts.estimate_store_pnl import predict_amount


def test_variable_cost_scales_with_sales() -> None:
    history = [(date(2025, 1, 1), 100.0), (date(2025, 2, 1), 200.0)]
    sales = {date(2025, 1, 1): 1000.0, date(2025, 2, 1): 2000.0}
    assert predict_amount("c11", date(2025, 3, 1), history, sales, {}, 3000.0, 0.0) == 300.0


def test_salary_cost_uses_observed_gross_to_net_ratio() -> None:
    history = [(date(2025, 1, 1), 150.0), (date(2025, 2, 1), 300.0)]
    salaries = {date(2025, 1, 1): 100.0, date(2025, 2, 1): 200.0}
    assert predict_amount("c3", date(2025, 3, 1), history, {}, salaries, 0.0, 300.0) == 450.0
