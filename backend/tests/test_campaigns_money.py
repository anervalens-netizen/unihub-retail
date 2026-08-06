from decimal import Decimal

from services.campaigns.money import (
    allocate_currency_targets,
    money,
)


def test_money_quantizes_without_binary_float_drift() -> None:
    assert money(Decimal("10.005")) == Decimal("10.01")
    assert money(Decimal("-0.005")) == Decimal("-0.01")


def test_currency_allocator_preserves_store_total_at_cent() -> None:
    result = allocate_currency_targets(
        {
            ("S1", "Ana"): Decimal("0.005"),
            ("S1", "Bogdan"): Decimal("0.005"),
        },
        {"S1": Decimal("0.01")},
    )
    assert sum(result.values(), Decimal("0")) == Decimal("0.01")
    assert all(value == value.quantize(Decimal("0.01")) for value in result.values())
