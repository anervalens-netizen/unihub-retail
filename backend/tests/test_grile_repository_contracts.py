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
    "grile_store_refreshes",
    "grile_store_observations",
    "grile_store_current_status",
)


def test_persisted_grile_reads_use_explicit_column_contracts() -> None:
    sources = [REPOSITORY_ROOT / "grile.py"]
    sources.extend(sorted(REPOSITORY_ROOT.glob("grile_monthly_*.py")))
    source = "\n".join(path.read_text(encoding="utf-8") for path in sources)

    for table in PERSISTED_GRILE_TABLES:
        assert re.search(rf"SELECT\s+\*\s+FROM\s+{table}\b", source, re.IGNORECASE) is None

    assert re.search(r"RETURNING\s+\*", source, re.IGNORECASE) is None


def test_reconciliation_update_qualifies_returning_columns() -> None:
    source = (REPOSITORY_ROOT / "grile_monthly_reconciliation.py").read_text(
        encoding="utf-8"
    )
    start = source.index("async def claim_reconciliation_candidates")
    end = source.index("async def mark_reconciliation_result", start)
    claim_source = source[start:end]

    assert "FROM candidates" in claim_source
    assert "RETURNING\n                    operation.id" in claim_source
    assert "RETURNING {_OPERATION_COLUMNS}" not in claim_source


def test_reconciliation_does_not_rollback_successful_completed_clears() -> None:
    source = (REPOSITORY_ROOT / "grile_monthly_reconciliation.py").read_text(
        encoding="utf-8"
    )
    assert "FROM grile_monthly_operations AS operation" in source
    assert "item.status <> 'completed'" in source
    assert "operation.status = 'running'" in source


def test_reset_rollback_can_recover_uncertain_checkpoint() -> None:
    source = (REPOSITORY_ROOT / "grile_monthly_reset_items.py").read_text(
        encoding="utf-8"
    )
    start = source.index("async def prepare_reset_rollback")
    end = source.index("async def confirm_reset_rollback", start)
    prepare_source = source[start:end]

    assert "checkpoint_phase IN ('clear_intent', 'clear_verified', 'recovery_required')" in prepare_source


def test_monthly_transition_table_has_one_authority() -> None:
    backend_root = REPOSITORY_ROOT.parent
    authorities = [
        path
        for path in backend_root.rglob("*.py")
        if "tests" not in path.parts
        if "_ALLOWED_TRANSITIONS" in path.read_text(encoding="utf-8")
    ]

    assert authorities == [backend_root / "grile" / "domain" / "monthly_state.py"]


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


def test_active_grile_reads_require_both_sheet_and_store_to_be_active() -> None:
    queries: list[str] = []

    class Connection:
        async def fetch(self, query: str, *_args: object):
            queries.append(" ".join(query.split()))
            return []

        async def fetchval(self, query: str, *_args: object) -> int:
            queries.append(" ".join(query.split()))
            return 0

    class Acquire:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class Pool:
        def acquire(self) -> Acquire:
            return Acquire()

    repo = GrileRepository(Pool())  # type: ignore[arg-type]
    asyncio.run(repo.get_active_sheets("2026-07"))
    asyncio.run(repo.count_active_sheets("2026-07"))
    asyncio.run(repo.get_sheet_map("2026-07"))

    assert len(queries) == 3
    for query in queries:
        assert "JOIN stores s ON s.site_code = gs.site_code" in query
        assert "gs.is_active = true" in query
        assert "s.is_active = true" in query
        assert "gs.active_from_month" in query
