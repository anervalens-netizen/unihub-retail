"""Pure normalization and SQL-clause policies for Retail filter scopes."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeAlias

from retail_filters import cartela_exclusion_clause, distribution_location_clause

_FILTER_SENTINELS = frozenset(
    value.casefold()
    for value in (
        "",
        "Toate",
        "Toti",
        "Toți",
        # Historical mojibake variants may still exist in saved URLs.
        "ToÈ›I",
        "ToÃˆâ€ºI",
    )
)

FilterInput: TypeAlias = str | Sequence[str] | None


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned.casefold() in _FILTER_SENTINELS:
        return None
    return cleaned


def normalize_filter_values(value: FilterInput) -> list[str] | None:
    """Canonicalize an exact scalar or repeated query values.

    Commas are ordinary data. Multi-select values must arrive as a sequence,
    which maps to repeated query parameters at the HTTP boundary.
    """
    raw_values: Sequence[str] = [value] if isinstance(value, str) else (value or [])
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_value in raw_values:
        item = normalize_filter(raw_value)
        if item is None or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized or None


def base_filter_values(
    month: str,
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
) -> tuple[list[Any], dict[str, int]]:
    return build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )


def build_scoped_params(
    initial_params: list[Any],
    *,
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
) -> tuple[list[Any], dict[str, int]]:
    params = list(initial_params)
    positions: dict[str, int] = {}
    normalized_site_code = normalize_filter_values(site_code)
    for key, value in [
        ("firma", None if normalized_site_code else normalize_filter_values(firma)),
        ("regional", None if normalized_site_code else normalize_filter_values(regional)),
        ("asm", None if normalized_site_code else normalize_filter_values(asm)),
        ("site_code", normalized_site_code),
        ("agent", normalize_filter_values(agent)),
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

    def col(alias: str | None, name: str) -> str:
        return f"{alias}.{name}" if alias else name

    clauses.append(distribution_location_clause(store_alias))
    if month_alias and month_position:
        clauses.append(f"{month_alias} = ${month_position}")
    if include_cartela_filter:
        clauses.append(cartela_exclusion_clause(site_alias))
    has_site_scope = "site_code" in positions

    if "firma" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'firma')} = ANY(${positions['firma']}::TEXT[])")
    if "regional" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'regional')} = ANY(${positions['regional']}::TEXT[])")
    if "asm" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'asm')} = ANY(${positions['asm']}::TEXT[])")
    if "site_code" in positions:
        clauses.append(f"{col(site_alias, 'site_code')} = ANY(${positions['site_code']}::TEXT[])")
    if "agent" in positions and agent_alias is not None:
        clauses.append(f"{col(agent_alias, 'agent')} = ANY(${positions['agent']}::TEXT[])")

    return clauses


def where_clauses(
    month: str,
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput = None,
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
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
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
