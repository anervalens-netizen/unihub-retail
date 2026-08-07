from decimal import Decimal

from services.store_pnl import finalize_metrics, money, percent


def test_pnl_money_never_round_trips_through_binary_float() -> None:
    metrics = finalize_metrics({
        "revenue": Decimal("1000000000000000.005"),
        "cogs": Decimal("0.004"),
        "gross_margin": Decimal("0"),
        "operating_costs": Decimal("0.001"),
        "ebitda": Decimal("0"),
        "depreciation": Decimal("0.005"),
        "ebit": Decimal("0"),
    })
    assert metrics["revenue"] == Decimal("1000000000000000.01")
    assert metrics["gross_margin"] == Decimal("1000000000000000.00")
    assert metrics["ebit"] == Decimal("1000000000000000.00")
    assert money(Decimal("2.675")) == Decimal("2.68")
    assert percent(Decimal("33.335")) == Decimal("33.34")
