"""Pure history projection helpers for Dashboard."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from schemas.dashboard import YearHistoryPoint

_RO_MONTHS = {
    1: "Ian", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mai", 6: "Iun",
    7: "Iul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def project_year_history(
    year: int,
    rows: list[dict[str, Any]],
    aggregate_row: dict[str, Any] | None,
) -> list[YearHistoryPoint]:
    """Project repository rows into the stable year-history response."""
    visible_rows = [
        row
        for row in rows
        if row["total_sales"] > 0
        or row["total_target"] > 0
        or row["total_quantity"] > 0
    ]
    points: list[YearHistoryPoint] = []
    has_monthly_sales = any(
        row["total_sales"] > 0 or row["total_quantity"] > 0
        for row in visible_rows
    )
    if year <= 2023 and aggregate_row and not has_monthly_sales and aggregate_row["total_sales"] > 0:
        points.append(
            YearHistoryPoint(
                label="Ian-Aug" if year == 2023 else str(year),
                sort_key=f"{year}-00",
                total_sales=aggregate_row["total_sales"],
                total_target=Decimal(0),
                total_quantity=aggregate_row["total_quantity"],
                is_aggregate=True,
            )
        )
    for row in visible_rows:
        month_num = int(row["import_month"][5:7])
        points.append(
            YearHistoryPoint(
                label=_RO_MONTHS[month_num],
                sort_key=row["import_month"],
                total_sales=row["total_sales"],
                total_target=row["total_target"],
                total_quantity=row["total_quantity"],
                is_aggregate=False,
            )
        )
    return points
