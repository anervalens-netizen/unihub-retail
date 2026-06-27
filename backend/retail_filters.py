from __future__ import annotations


DISTRIBUTION_LOCATION_PREFIX = "TR "


def _qualified_column(alias: str | None, column: str) -> str:
    return f"{alias}.{column}" if alias else column


def distribution_location_clause(alias: str | None = None, column: str = "locatie") -> str:
    qualified = _qualified_column(alias, column)
    return f"{qualified} NOT ILIKE '{DISTRIBUTION_LOCATION_PREFIX}%'"


def cartela_exclusion_clause(alias: str | None = None, column: str = "is_cartela") -> str:
    qualified = _qualified_column(alias, column)
    return f"NOT {qualified}"


def retail_exclusion_clauses(
    *,
    site_alias: str | None,
    store_alias: str | None,
) -> list[str]:
    return [
        distribution_location_clause(store_alias),
        cartela_exclusion_clause(site_alias),
    ]
