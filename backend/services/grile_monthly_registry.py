"""Registry normalization for monthly Grile operations."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from services.grile_monthly_integrity import MonthlyIntegrityError
from services.grile_monthly_types import StoreEntry


RegistryReader = Callable[..., Awaitable[list[dict[str, Any]]]]


def company_from_values(registry_key: str | None, fallback: str | None) -> str:
    raw = (registry_key or "").split("/", 1)[0].strip() or (fallback or "").strip()
    normalized = raw.casefold()
    if normalized == "mobicell":
        return "Mobicell"
    if normalized == "mobiup":
        return "Mobiup"
    raise MonthlyIntegrityError(
        "unknown_company",
        "Grile registry company is missing or unsupported",
    )


def store_from_values(registry_key: str | None, fallback: str | None) -> str:
    if registry_key and "/" in registry_key:
        return registry_key.split("/", 1)[1].strip()
    return (fallback or "").strip()


async def load_entries(
    pool: Any,
    only: str | None,
    *,
    month: str | None,
    fetch_registry: RegistryReader,
) -> list[StoreEntry]:
    rows = await fetch_registry(pool, month=month)
    entries = [_entry(row) for row in rows]
    if only:
        needle = only.casefold()
        entries = [
            entry
            for entry in entries
            if needle
            in (
                f"{entry.company}/{entry.store}/"
                f"{entry.site_code}/{entry.manager}"
            ).casefold()
        ]
    if not entries:
        raise RuntimeError("No active grile matched the requested filter.")
    return entries


def _entry(row: dict[str, Any]) -> StoreEntry:
    location = str(row.get("locatie") or "")
    manager = str(row.get("asm") or "Neatribuit").strip() or "Neatribuit"
    return StoreEntry(
        company=company_from_values(row.get("registry_key"), row.get("firma")),
        store=store_from_values(row.get("registry_key"), location),
        sheet_id=str(row["sheet_id"]),
        site_code=str(row["site_code"]),
        manager=manager,
        is_closed=location.strip().upper().startswith("INCHIS "),
        template_version=str(row.get("template_version") or "v2"),
    )
