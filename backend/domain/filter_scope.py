"""Pure normalization and SQL-clause policies for Retail filter scopes."""
from __future__ import annotations

from typing import Any

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


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned.casefold() in _FILTER_SENTINELS:
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
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[Any], dict[str, int]]:
    params = list(initial_params)
    positions: dict[str, int] = {}
    normalized_site_code = normalize_filter(site_code)
    for key, value in [
        ("firma", None if normalized_site_code else normalize_filter(firma)),
        ("regional", None if normalized_site_code else normalize_filter(regional)),
        ("asm", None if normalized_site_code else normalize_filter(asm)),
        ("site_code", normalized_site_code),
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

    def col(alias: str | None, name: str) -> str:
        return f"{alias}.{name}" if alias else name

    clauses.append(distribution_location_clause(store_alias))
    if month_alias and month_position:
        clauses.append(f"{month_alias} = ${month_position}")
    if include_cartela_filter:
        clauses.append(cartela_exclusion_clause(site_alias))
    has_site_scope = "site_code" in positions

    if "firma" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'firma')} = ANY(string_to_array(${positions['firma']}::TEXT, ','))")
    if "regional" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'regional')} = ANY(string_to_array(${positions['regional']}::TEXT, ','))")
    if "asm" in positions and not has_site_scope:
        clauses.append(f"{col(store_alias, 'asm')} = ANY(string_to_array(${positions['asm']}::TEXT, ','))")
    if "site_code" in positions:
        clauses.append(f"{col(site_alias, 'site_code')} = ANY(string_to_array(${positions['site_code']}::TEXT, ','))")
    if "agent" in positions and agent_alias is not None:
        clauses.append(f"{col(agent_alias, 'agent')} = ANY(string_to_array(${positions['agent']}::TEXT, ','))")

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
