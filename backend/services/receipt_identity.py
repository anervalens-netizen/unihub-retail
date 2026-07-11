from __future__ import annotations

import re

_SQL_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def canonical_receipt_identity_sql(alias: str) -> str:
    """Return the canonical PostgreSQL tuple used to identify one receipt.

    The alias is validated because the returned fragment is interpolated into
    static repository SQL. Runtime/user-provided values must never be passed as
    aliases.
    """

    if not _SQL_ALIAS_RE.fullmatch(alias):
        raise ValueError(f"Invalid SQL alias: {alias!r}")

    return (
        "("
        f"{alias}.sale_date, "
        f"{alias}.site_code, "
        f"COALESCE(NULLIF(BTRIM({alias}.agent), ''), '<unknown>'), "
        f"{alias}.bon_nr"
        ")"
    )
