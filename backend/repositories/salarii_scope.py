"""Canonical salary reporting scope construction."""
from __future__ import annotations

from typing import Any

from domain.filter_scope import FilterInput, normalize_filter_values


MIN_SALARY_FOR_AVERAGE = 2000


def _salary_scope(
    *,
    salary_alias: str,
    company_name: str | None = None,
    site_code: FilterInput = None,
    regional: str | None = None,
    asm: str | None = None,
    year: int | None = None,
    month: int | None = None,
    q: str | None = None,
    initial_params: list[Any] | None = None,
    initial_conditions: list[str] | None = None,
    lower_company: bool = True,
    where_prefix: bool = True,
) -> tuple[str, str, list[Any]]:
    params = list(initial_params or [])
    conditions = list(initial_conditions or [])
    # Organizational scope is a semi-join: it filters salary components but
    # never changes their cardinality. A report component is identified by its
    # persisted salary row/provenance, not its business-valued columns.
    join_block = ""

    def col(name: str) -> str:
        return f"{salary_alias}.{name}" if salary_alias else name

    def add(condition: str, value: Any) -> None:
        params.append(value)
        conditions.append(condition.format(position=len(params)))

    if q:
        add(f"{col('full_name')} ILIKE ${{position}}", f"%{q}%")
    site_codes = normalize_filter_values(site_code)
    if company_name and not site_codes:
        if lower_company:
            add(f"LOWER({col('company_name')}) = ${{position}}", company_name.lower())
        else:
            add(f"{col('company_name')} = ${{position}}", company_name)
    if site_codes:
        add(f"{col('site_code')} = ANY(${{position}}::TEXT[])", site_codes)
    store_conditions: list[str] = []
    if regional and not site_codes:
        params.append(regional)
        store_conditions.append(f"st.regional = ${len(params)}")
    if asm and not site_codes:
        params.append(asm)
        store_conditions.append(f"st.asm = ${len(params)}")
    if store_conditions:
        conditions.append(
            "EXISTS (SELECT 1 FROM stores st "
            f"WHERE st.site_code = {col('site_code')} AND "
            + " AND ".join(store_conditions)
            + ")"
        )
    if year is not None:
        add(f"{col('year')} = ${{position}}", year)
    if month is not None:
        add(f"{col('month')} = ${{position}}", month)

    if not conditions:
        return join_block, "", params
    operator = "WHERE " if where_prefix else ""
    return join_block, operator + " AND ".join(conditions), params
