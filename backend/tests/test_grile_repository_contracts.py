from __future__ import annotations

import asyncio
import re
from pathlib import Path

from repositories.grile import GrileRepository


REPOSITORY_ROOT = Path(__file__).resolve().parents[1] / "repositories"
PERSISTED_GRILE_TABLES = (
    "grile_monthly_operations",
    "grile_monthly_reset_items",
    "grile_monthly_manifests",
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


def test_latest_grile_month_prefers_sales_and_uses_targets_only_as_fallback() -> None:
    class Connection:
        async def fetchval(self, query: str) -> str:
            normalized = " ".join(query.split())
            assert normalized.startswith("SELECT COALESCE(")
            assert normalized.index("reporting_item_month") < normalized.index(
                "store_targets"
            )
            assert "UNION ALL" not in normalized
            return "2026-07"

    class Acquire:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    repo = GrileRepository(Pool())  # type: ignore[arg-type]
    assert asyncio.run(repo.get_latest_data_month()) == "2026-07"
