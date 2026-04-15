"""Unified filter helpers — normalizare, scope, where clauses.

Consolidat din routers/shared.py și routers/dashboard_filters.py.
Acestea nu erau "routers" — erau helpere SQL care se nimeriseră acolo
istoric. Mutate în services/ ca restul modulelor cu logică pură.

Zero schimbări funcționale față de versiunile vechi. Orice caller care
importa din routers.shared / routers.dashboard_filters acum importă de
aici.
"""
from __future__ import annotations

from typing import Any

_FILTER_SENTINELS = {
    "",
    "Toate",
    "Toti",
    "To\u021bi",
    "To\u00c8\u203aI",  # legacy mojibake value kept for backward compatibility
    "To\u00c3\u02c6\u20ac\u203aI",  # older corrupted variant seen in local state
}


def normalize_filter(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned in _FILTER_SENTINELS:
        return None
    return cleaned


def build_scope_filter(
    user: dict[str, Any],
    base_alias: str = "s",
    param_start: int = 1,
) -> tuple[str, list[Any]]:
    if user["role"] != "tl":
        return "", []
    site_column = f"{base_alias}.site_code" if base_alias else "site_code"
    return (
        f"{site_column} IN (SELECT site_code FROM tl_store_assignments WHERE user_id = ${param_start}::INTEGER)",
        [user["id"]],
    )


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
    user: dict[str, Any],
    positions: dict[str, int],
    site_alias: str,
    store_alias: str,
    agent_alias: str | None = None,
    month_alias: str | None = None,
    month_position: int | None = None,
    include_cartela_filter: bool = False,
    scope_base_alias: str = "",
    param_floor: int = 0,
) -> tuple[list[str], list[Any]]:
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

    scope_param_start = (
        max([param_floor, month_position or 0, *positions.values()], default=0) + 1
    )
    scope_sql, scope_params = build_scope_filter(
        user, base_alias=scope_base_alias, param_start=scope_param_start
    )
    if scope_sql:
        clauses.append(scope_sql)
    return clauses, scope_params


def where_clauses(
    user: dict[str, Any],
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
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="",
        store_alias="",
        agent_alias="" if include_agent else None,
        month_alias="import_month",
        month_position=1,
        include_cartela_filter=False,
        scope_base_alias="",
        param_floor=len(params),
    )
    return clauses, [*params, *scope_params]


def transaction_filter_parts(
    user: dict[str, Any],
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[list[str], list[Any], list[Any]]:
    params, positions = base_filter_values(
        month, firma, regional, asm, site_code, agent
    )
    clauses, scope_params = scoped_clauses(
        user,
        positions,
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        month_alias="st.import_month",
        month_position=1,
        include_cartela_filter=True,
        scope_base_alias="st",
        param_floor=len(params),
    )
    return clauses, params, scope_params
