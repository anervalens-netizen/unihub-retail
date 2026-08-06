"""Stable warning projection for Target responses."""

from __future__ import annotations


def unique_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in warnings if item.strip()))
