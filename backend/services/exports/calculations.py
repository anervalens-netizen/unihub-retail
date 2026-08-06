"""Pure business calculations used by report and daily-comparison planning."""
from decimal import Decimal


def ratio(value: Decimal, base: int | Decimal) -> Decimal | None:
    base_decimal = Decimal(base)
    return None if base_decimal == 0 else (value / base_decimal).quantize(Decimal("0.01"))


def pct(value: Decimal, base: Decimal) -> Decimal | None:
    return None if base == 0 else ((value * Decimal(100)) / base).quantize(Decimal("0.01"))
