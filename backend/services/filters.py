"""Unified filter helpers — normalizare + where clauses.

Zero scope la nivel de utilizator — sistemul de autentificare a fost eliminat.
"""
from __future__ import annotations

from typing import Any

_FILTER_SENTINELS = {
    "",
    "Toate",
    "Toti",
    "To\u021bi",
    "To\u00c8\u203aI",
    "To\u00c3\u02c6\u20ac\u203aI",
}


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned in _FILTER_SENTINELS:
        return None
    return cleaned


def base_filter_values(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[Any], dict[str, int]]:
    params: list[Any] = [month]
    positions: dict[str, int] = {}
    for key, value in [
        ("firma", normalize_filter(firma)),
        ("regional", normalize_filter(regional)),
        ("asm", normalize_filter(asm)),
        ("site_code", normalize_filter(site_code)),
        ("agent", normalize_filter(agent)),
    ]:
        if value is not None:
            params.append(value)
            positions[key] = len(params)
    return params, positions


def scoped_clauses(
    positions: dict[str, int],
    site_alias: str,
    store_alias: str,
    agent_alias: str | None = None,
    month_alias: str | None = None,
    month_position: int | None = None,
    include_cartela_filter: bool = False,
) -> list[str]:
    clauses: list[str] = []

    def col(alias: str, name: str) -> str:
        return f"{alias}.{name}" if alias else name

    if month_alias and month_position:
        clauses.append(f"{month_alias} = ${month_position}")
    if include_cartela_filter:
        clauses.append(f"NOT {col(site_alias, 'is_cartela')}")
    if "firma" in positions:
        clauses.append(f"{col(store_alias, 'firma')} = ${positions['firma']}")
    if "regional" in positions:
        clauses.append(f"{col(store_alias, 'regional')} = ${positions['regional']}")
    if "asm" in positions:
        clauses.append(f"{col(store_alias, 'asm')} = ${positions['asm']}")
    if "site_code" in positions:
        clauses.append(f"{col(site_alias, 'site_code')} = ${positions['site_code']}")
    if "agent" in positions and agent_alias is not None:
        clauses.append(f"{col(agent_alias, 'agent')} = ${positions['agent']}")

    return clauses


def where_clauses(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None = None,
    include_agent: bool = False,
) -> tuple[list[str], list[Any]]:
    params, positions = base_filter_values(
        month, firma, regional, asm, site_code, agent
    )
    clauses = scoped_clauses(
        positions,
        site_alias="",
        store_alias="",
        agent_alias="" if include_agent else None,
        month_alias="import_month",
        month_position=1,
    )
    return clauses, params


def transaction_filter_parts(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[str], list[Any]]:
    params, positions = base_filter_values(
        month, firma, regional, asm, site_code, agent
    )
    clauses = scoped_clauses(
        positions,
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        month_alias="st.import_month",
        month_position=1,
        include_cartela_filter=True,
    )
    return clauses, params
