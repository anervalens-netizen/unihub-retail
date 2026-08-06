"""Incentive source normalization helpers."""

from __future__ import annotations

from typing import Any


def incentive_item_codes(campaign: dict[str, Any] | None) -> list[str]:
    if campaign is None:
        return []
    codes = [
        str(product["item_code"])
        for period in campaign.get("periods", [])
        for product in period.get("products", [])
    ]
    if codes:
        return sorted(set(codes))
    return sorted({str(code) for code in campaign.get("item_codes") or campaign.get("reward_map", {}).keys()})
