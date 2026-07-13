from __future__ import annotations

import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1] / "repositories"
PERSISTED_GRILE_TABLES = (
    "grile_monthly_operations",
    "grile_monthly_reset_items",
    "grile_runs",
    "grile_store_status",
)


def test_persisted_grile_reads_use_explicit_column_contracts() -> None:
    source = "\n".join(
        (REPOSITORY_ROOT / name).read_text(encoding="utf-8")
        for name in ("grile.py", "grile_monthly_operations.py")
    )

    for table in PERSISTED_GRILE_TABLES:
        assert re.search(rf"SELECT\s+\*\s+FROM\s+{table}\b", source, re.IGNORECASE) is None

    assert re.search(r"RETURNING\s+\*", source, re.IGNORECASE) is None
