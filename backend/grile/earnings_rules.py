"""V1 c131c21 commissions: Decimal arithmetic, whole-RON half-up rounding."""
from decimal import Decimal, ROUND_HALF_UP


def whole_ron(value: Decimal) -> Decimal:
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def monthly_commission(sales: Decimal, target: Decimal, divisor: int = 1) -> Decimal | None:
    if target <= 0 or divisor <= 0:
        return None
    if sales * divisor * 100 < target * 80:
        return Decimal(0)
    bonus = Decimal(0)
    if sales * divisor >= target:
        bonus = Decimal(200)
    if sales * divisor * 100 >= target * 120:
        bonus = Decimal(400)
    return whole_ron(sales * Decimal("0.03") + bonus)


def daily_commission(sales: Decimal, target: Decimal, divisor: int = 1) -> Decimal | None:
    if target <= 0 or divisor <= 0:
        return None
    if sales * divisor * 100 < target * 79:
        return Decimal(0)
    return whole_ron(sales * Decimal("0.03"))
