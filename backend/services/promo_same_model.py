"""Pure receipt aggregation for same-model screen and camera promotions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any


def same_model_receipts(
    rows: list[Any],
    screen_code_models: dict[str, set[str]],
    camera_code_models: dict[str, set[str]],
) -> dict[tuple[date, str, str, str], dict[str, Any]]:
    receipts: dict[tuple[date, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if int(row["quantity"] or 0) <= 0:
            continue
        key = (
            row["sale_date"],
            str(row["site_code"]),
            str(row["agent"]),
            str(row["bon_nr"]),
        )
        receipt = receipts.setdefault(
            key,
            {"screen_models": set(), "camera_lines": []},
        )
        item_code = str(row["item_code"])
        receipt["screen_models"].update(screen_code_models.get(item_code, ()))
        camera_models = camera_code_models.get(item_code)
        if camera_models:
            receipt["camera_lines"].append(
                (
                    row["unit_price"],
                    item_code,
                    int(row["id"]),
                    frozenset(camera_models),
                )
            )
    return receipts


def same_model_discounted_rows(
    receipts: dict[tuple[date, str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregated: dict[tuple[str, str, str], tuple[int, Decimal]] = {}
    for (_date, site, agent, _receipt), receipt in receipts.items():
        candidates = [
            line
            for line in receipt["camera_lines"]
            if receipt["screen_models"].intersection(line[3])
        ]
        if not candidates:
            continue
        unit_price, item_code, _row_id, _models = min(
            candidates,
            key=lambda line: (line[0], line[1], line[2]),
        )
        key = (site, agent, item_code)
        units, gross_value = aggregated.get(key, (0, Decimal("0")))
        aggregated[key] = (units + 1, gross_value + Decimal(str(unit_price)))
    return [
        {
            "site_code": site,
            "agent": agent,
            "item_code": item_code,
            "units": units,
            "gross_value": gross_value,
        }
        for (site, agent, item_code), (units, gross_value) in aggregated.items()
    ]
