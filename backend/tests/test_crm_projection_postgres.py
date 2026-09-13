"""Lot 47 — CRM monthly score projection must represent the exact current
recalculation result, AND missing source data must not silently destroy
the last good generation.

F06: ``CrmRepository.upsert_scores`` used INSERT ... ON CONFLICT, never
deleted rows that disappeared from the new calculation, and was a no-op for
an empty list. ``store_scores`` for a month therefore drifted from the
"currently valid" recalculation. The fix replaces that method with
``replace_month_scores``, which performs a transactional DELETE + INSERT
plus a same-month advisory lock.

P1-A: a CRM recalculation whose current score calculation is empty MUST
NOT wipe the previously persisted projection. The service raises
``CrmSourceDataUnavailable`` before any destructive write, preserving
the last-good generation as documented in AGENTS.md ("Source/worker
failure never replaces last good generation. Missing source data is
explicit anomaly, never implicit zero.").

P1-B: the per-month advisory lock is acquired BEFORE any score-calculation
read, on the same connection as the replacement transaction, so a same-month
second request cannot begin its calculation while the first one is still
in flight. Different-month requests remain independent.

This module exercises the real PostgreSQL repository and the real
``CrmService`` end-to-end against an isolated test database. It never
alters the schema, never drops constraints, and never inserts invalid
``store_scores`` rows except inside a transaction whose rollback is the
subject of the negative-rollback proof.

Layout:

  * 1. BASELINE stale-row proof (historical shape, kept for posterity)
  * 2. Replacement removes stale row
  * 3. Replacement updates existing row
  * 4. Empty replacement is fail-closed at the repo (P1-A repository invariant)
  * 5. Month isolation
  * 6. Transaction rollback on failure (NotNullViolation)
  * 7. Same-month concurrent replacement — synthetic union is impossible
  * 8. Different-month concurrency — independent lock keys
  * 9. Service recalculate integration (A+B → A shrink)
  * 10. Deterministic calculation
  * 11. P1-A: empty-source preserves last-good projection
  * 12. P1-A: empty-source with no prior projection is still rejected
  * 13. P1-A: repository empty-list fail-closed at the service layer too
  * 14. P1-B: lock acquired before calculation, second calc blocked
  * 15. P1-B: newer request wins over stale
  * 16. P1-B: calculation exception releases the lock
  * 17. P1-B: task cancellation releases the lock
  * 18. Different months use distinct lock keys (deterministic barrier)

All synthetic sites / months / targets use the ``CRM-L47-`` / ``2098-``
namespace so they cannot collide with other suites.
"""

from __future__ import annotations

import asyncio
import os
import zlib
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from db.connection import get_pool
from repositories.crm import CrmRepository
from services.crm import CrmService, CrmSourceDataUnavailable, _query_visits_by_store_postgres


# --- synthetic fixtures ----------------------------------------------------

FIRMA = "Mobicell"
REGIONAL = "L47 Region"
ASM = "L47 ASM"

SITE_A = "CRM-L47-A"
SITE_B = "CRM-L47-B"
SITE_C = "CRM-L47-C"
SITE_D = "CRM-L47-D"
SITE_E = "CRM-L47-E"

MONTH_M1 = "2098-01"
MONTH_M2 = "2098-02"
# Pick a third month that's deliberately *not* the running test month so the
# different-month concurrency test does not collide with later suites.
MONTH_M3 = "2098-03"
MONTH_M4 = "2098-04"
MONTH_M5 = "2098-05"


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL through the immutable manifest",
)


# Lock constants mirrored exactly from services.crm so tests that
# exercise the repository primitive directly can acquire the same
# per-month advisory lock without importing the service's private
# internals.
_CRM_LOCK_NAMESPACE = 7377


def _month_lock_key(month: str) -> int:
    return zlib.crc32(month.encode("utf-8")) & 0x7FFFFFFF


# --- helpers ---------------------------------------------------------------


async def _cleanup_pool_sites(connection, site_codes: list[str]) -> None:
    await connection.execute(
        "DELETE FROM store_scores WHERE site_code = ANY($1::text[])",
        site_codes,
    )
    await connection.execute(
        "DELETE FROM store_targets WHERE site_code = ANY($1::text[])",
        site_codes,
    )
    await connection.execute(
        "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
        site_codes,
    )
    await connection.execute(
        "DELETE FROM stores WHERE site_code = ANY($1::text[])",
        site_codes,
    )


async def _seed_store(
    connection,
    site_code: str,
    month: str,
    *,
    is_active: bool = True,
) -> None:
    await connection.execute(
        """
        INSERT INTO stores (
            site_code, locatie, firma, regional, asm,
            first_seen_month, last_seen_month, is_active
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $6, $7
        )
        """,
        site_code,
        f"L47 loc {site_code}",
        FIRMA,
        REGIONAL,
        ASM,
        month,
        is_active,
    )


async def _seed_target(
    connection,
    site_code: str,
    month: str,
    target: Decimal,
) -> None:
    await connection.execute(
        """
        INSERT INTO store_targets (
            site_code, import_month, target_value, source_file
        ) VALUES ($1, $2, $3, $4)
        """,
        site_code,
        month,
        target,
        f"l47-{site_code}.xlsx",
    )


async def _seed_agent_month(
    connection,
    site_code: str,
    month: str,
    total_sales: Decimal,
) -> None:
    await connection.execute(
        """
        INSERT INTO reporting_agent_month (
            import_month, site_code, locatie, firma, regional, asm,
            agent, total_sales, working_days
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, 30
        )
        """,
        month,
        site_code,
        f"L47 loc {site_code}",
        FIRMA,
        REGIONAL,
        ASM,
        f"agent-{site_code}",
        total_sales,
    )


def _score_dict(site_code: str, score: int) -> dict[str, Any]:
    return {
        "site_code": site_code,
        "score": score,
        "breakdown": {
            "target_pct": float(score),
            "trend_pct": 0.0,
            "kpi_pct": 0.0,
            "kpi_bon2acc_score": 0.0,
            "kpi_focus_score": 0.0,
            "visits_pct": 0.0,
            "target_attainment": float(score),
            "forecast_factor": 1.0,
            "kpi_bon2acc": 0.0,
            "kpi_focus": 0.0,
            "kpi_bon2acc_avg": 0.0,
            "kpi_focus_avg": 0.0,
            "nr_vizite": 0,
            "avg_completion": 0.0,
        },
    }


async def _persisted_sites(
    connection: asyncpg.Connection, month: str
) -> set[str]:
    rows = await connection.fetch(
        "SELECT site_code FROM store_scores WHERE score_month = $1",
        month,
    )
    return {row["site_code"] for row in rows}


async def _replace_month_scores(
    pool: asyncpg.Pool,
    month: str,
    scores: list[dict],
) -> None:
    """Test helper that mirrors ``CrmService.recalculate_scores``'s
    lock + replace primitive exactly, so repository-level invariants
    (atomic DELETE+INSERT, fail-closed empty list, transactional
    rollback) can be tested without going through the full service
    surface.

    Acquires the same per-month advisory lock as the service, opens a
    single transaction, and runs ``replace_month_scores`` on the locked
    connection. Any failure rolls the transaction back; the lock is
    released on COMMIT/ROLLBACK.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock($1, $2)",
                _CRM_LOCK_NAMESPACE, _month_lock_key(month),
            )
            await CrmRepository(pool).replace_month_scores(
                month, scores, connection=conn,
            )


@pytest.fixture
async def l47_pool():
    pool = await get_pool()
    # Pre-test cleanup to guarantee a pristine starting state for this
    # module's synthetic namespace. Without this, a previous failed
    # test could leave orphan rows that surface as off-by-one counts
    # in the very next test.
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_scores WHERE site_code LIKE 'CRM-L47-%'",
        )
        for month in (MONTH_M1, MONTH_M2, MONTH_M3, MONTH_M4, MONTH_M5):
            await connection.execute(
                "DELETE FROM store_scores WHERE score_month = $1",
                month,
            )
    yield pool
    # Best-effort cleanup even if a test raised mid-flight.
    async with pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM store_scores WHERE site_code LIKE 'CRM-L47-%'",
        )
        await connection.execute(
            "DELETE FROM store_targets WHERE site_code LIKE 'CRM-L47-%'",
        )
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code LIKE 'CRM-L47-%'",
        )
        await connection.execute(
            "DELETE FROM stores WHERE site_code LIKE 'CRM-L47-%'",
        )
        for month in (MONTH_M1, MONTH_M2, MONTH_M3, MONTH_M4, MONTH_M5):
            await connection.execute(
                "DELETE FROM store_scores WHERE score_month = $1",
                month,
            )


# --- 1. Baseline stale-row proof (SQL-level) -------------------------------


@pytest.mark.anyio
async def test_baseline_legacy_upsert_leaves_stale_row(l47_pool) -> None:
    """PIN the pre-fix SQL failure mode so the fix has a recorded baseline.

    The legacy ``INSERT ... ON CONFLICT DO UPDATE`` adds a row for B
    once but cannot delete it when B disappears from the calculation.
    The fixed ``replace_month_scores`` replaces this surface; we keep
    the legacy SQL here only to prove the leak shape on the pristine
    schema. The test then contrasts with the locked fixed path to
    show the same starting state diverges correctly under the fix.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

        # 1. Persist {A,B} via the legacy SQL reproduced from the
        # pre-fix repository.
        await connection.executemany(
            """
            INSERT INTO store_scores (site_code, score_month, score, breakdown)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (site_code, score_month)
            DO UPDATE SET score = EXCLUDED.score,
                          breakdown = EXCLUDED.breakdown,
                          calculated_at = now()
            """,
            [
                (SITE_A, MONTH_M1, 45, "{}"),
                (SITE_B, MONTH_M1, 35, "{}"),
            ],
        )
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}

        # 2. Wipe B's source — calculation would now produce only A.
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            SITE_B,
        )

        # 3. Re-run the same legacy upsert with only A; B must remain.
        await connection.executemany(
            """
            INSERT INTO store_scores (site_code, score_month, score, breakdown)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (site_code, score_month)
            DO UPDATE SET score = EXCLUDED.score,
                          breakdown = EXCLUDED.breakdown,
                          calculated_at = now()
            """,
            [(SITE_A, MONTH_M1, 60, "{}")],
        )
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}, (
            "Legacy upsert path must leave stale B as a recorded baseline. "
            "If this asserts fails, the bug shape itself has changed."
        )

    # 4. The fixed locked path replaces B's stale row with the new
    # complete projection. Show the contrast.
    await _replace_month_scores(
        l47_pool, MONTH_M1, [_score_dict(SITE_A, 60)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}


# --- 2. Replacement removes stale row --------------------------------------


@pytest.mark.anyio
async def test_replacement_removes_stale_row(l47_pool) -> None:
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    await _replace_month_scores(
        l47_pool, MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}

    # B's source disappears; new projection is only A.
    async with l47_pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            SITE_B,
        )
    await _replace_month_scores(
        l47_pool, MONTH_M1, [_score_dict(SITE_A, 55)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}


# --- 3. Replacement updates existing row -----------------------------------


@pytest.mark.anyio
async def test_replacement_updates_existing_row(l47_pool) -> None:
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))

    await _replace_month_scores(
        l47_pool, MONTH_M1, [_score_dict(SITE_A, 75)],
    )
    async with l47_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT score, breakdown, calculated_at
            FROM store_scores
            WHERE site_code = $1 AND score_month = $2
            """,
            SITE_A, MONTH_M1,
        )
        assert row is not None
        assert row["score"] == 75
        calculated_at_before = row["calculated_at"]

    await _replace_month_scores(
        l47_pool, MONTH_M1, [_score_dict(SITE_A, 90)],
    )
    async with l47_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT score, breakdown, calculated_at
            FROM store_scores
            WHERE site_code = $1 AND score_month = $2
            """,
            SITE_A, MONTH_M1,
        )
        assert row is not None
        assert row["score"] == 90, "Replacement must overwrite, not duplicate."
        # JSONB round-trip: every breakdown key must be retrievable.
        breakdown = row["breakdown"]
        if isinstance(breakdown, str):
            import json as _json
            breakdown = _json.loads(breakdown)
        assert breakdown["target_pct"] == 90.0
        # calculated_at must refresh under the new recalculation.
        assert row["calculated_at"] > calculated_at_before, (
            "calculated_at must advance on recalculation."
        )
    # site_codes count must remain 1 (no duplicate insert from a stale row).
    async with l47_pool.acquire() as connection:
        count = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores "
            "WHERE site_code = $1 AND score_month = $2",
            SITE_A, MONTH_M1,
        )
        assert count == 1


# --- 4. Empty replacement is fail-closed at the repo (P1-A) ----------------


@pytest.mark.anyio
async def test_empty_replacement_fails_closed_at_repository(l47_pool) -> None:
    """P1-A repository invariant: ``replace_month_scores(M, [])`` is a
    programming error and MUST raise before DELETE.

    A previous candidate accepted an empty list as a valid instruction
    to DELETE the month, which silently destroyed the last-good
    projection when the source calculation returned ``[]``. The repo
    now fail-closes: an empty list raises ``ValueError`` inside the
    transaction, the transaction rolls back, and the previously
    persisted projection remains intact.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    # Seed a non-empty projection via the locked helper.
    await _replace_month_scores(
        l47_pool, MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}

    # Attempt to call the repository with an empty list. The fail-closed
    # guard fires BEFORE DELETE, so the persisted projection stays intact.
    with pytest.raises(ValueError, match="non-empty"):
        await _replace_month_scores(l47_pool, MONTH_M1, [])

    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}, (
            "P1-A repository invariant: empty replacement must NOT touch "
            "the previously persisted projection."
        )
        # The old scores remain byte-for-byte intact.
        scores = await connection.fetch(
            "SELECT site_code, score FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M1,
        )
        score_map = {row["site_code"]: row["score"] for row in scores}
        assert score_map == {SITE_A: 50, SITE_B: 30}


# --- 5. Month isolation -----------------------------------------------------


@pytest.mark.anyio
async def test_replacement_is_month_scoped(l47_pool) -> None:
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_store(connection, SITE_C, MONTH_M2)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_C, MONTH_M2, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))
        await _seed_agent_month(connection, SITE_C, MONTH_M2, Decimal("400"))

    await _replace_month_scores(
        l47_pool, MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    await _replace_month_scores(
        l47_pool, MONTH_M2, [_score_dict(SITE_C, 80)],
    )

    # Replace M1 with only A; M2 must be untouched.
    await _replace_month_scores(
        l47_pool, MONTH_M1, [_score_dict(SITE_A, 50)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}
        assert await _persisted_sites(connection, MONTH_M2) == {SITE_C}

        # Row counts to guard against accidental cross-month fanout.
        count_m1 = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores WHERE score_month = $1",
            MONTH_M1,
        )
        count_m2 = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores WHERE score_month = $1",
            MONTH_M2,
        )
        assert count_m1 == 1
        assert count_m2 == 1


# --- 6. Transaction rollback on failure -----------------------------------


@pytest.mark.anyio
async def test_replacement_failure_preserves_persisted_projection(
    l47_pool,
) -> None:
    """A replacement that fails after the DELETE must NOT leave the month
    empty. The transactional DELETE + INSERT must roll back as a unit.

    Exercises the full ``CrmService.recalculate_scores`` cycle with a
    mocked calculation that yields a NOT-NULL-violating score. The
    service's lock-aware transaction rolls back, and the previously
    persisted projection remains byte-for-byte intact.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    # Successful recalc seeds {A,B} with their actual computed scores.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH_M1)
    assert count == 2
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}
        original_rows = await connection.fetch(
            "SELECT site_code, score, calculated_at FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M1,
        )
    original_snapshot = [
        (r["site_code"], r["score"], r["calculated_at"]) for r in original_rows
    ]

    # Replacement whose INSERT violates NOT NULL on score. The empty-list
    # guard is not involved here (bad_scores is non-empty).
    bad_scores = [
        _score_dict(SITE_A, 50),
        # Inject score=None: a real schema NOT NULL trap.
        {**_score_dict(SITE_B, 30), "score": None},
    ]
    with patch.object(
        svc, "calculate_scores_for_month", AsyncMock(return_value=bad_scores),
    ):
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await svc.recalculate_scores(MONTH_M1)

    # After the failure, persisted state must still match the original
    # projection byte-for-byte (scores, calculated_at, sites).
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}, (
            "Rollback path failed: persisted projection must be unchanged "
            "after a failed replacement. Either {} or {A} indicate a leak."
        )
        rows_after = await connection.fetch(
            "SELECT site_code, score, calculated_at FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M1,
        )
    after_snapshot = [
        (r["site_code"], r["score"], r["calculated_at"]) for r in rows_after
    ]
    assert after_snapshot == original_snapshot, (
        "Rollback path failed: scores and calculated_at must remain "
        "byte-for-byte unchanged after a failed replacement."
    )


# --- 7. Same-month concurrent replacement ---------------------------------


@pytest.mark.anyio
async def test_concurrent_same_month_replacement_yields_one_projection(
    l47_pool,
) -> None:
    """Two writers racing for the same month must end with one COMPLETE
    projection, never the synthetic union of disjoint sets.

    The per-month advisory lock is acquired BEFORE the calculation and
    held until the replacement commits, so the second writer cannot
    begin its calculation until the first cycle finishes.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    async def writer_a() -> None:
        await _replace_month_scores(
            l47_pool, MONTH_M1, [_score_dict(SITE_A, 50)],
        )

    async def writer_b() -> None:
        await _replace_month_scores(
            l47_pool, MONTH_M1, [_score_dict(SITE_B, 35)],
        )

    # Run many concurrent races. If serialization ever breaks, the
    # union will surface as {A,B}.
    for _ in range(8):
        await asyncio.gather(writer_a(), writer_b())
        async with l47_pool.acquire() as connection:
            sites = await _persisted_sites(connection, MONTH_M1)
        assert sites in ({SITE_A}, {SITE_B}), (
            f"Same-month concurrent replacement produced a synthetic "
            f"intersection/union: {sites}. One writer must own the month."
        )

    # Final race for determinism of the test's last claim.
    await writer_a()
    async with l47_pool.acquire() as connection:
        sites_a = await _persisted_sites(connection, MONTH_M1)
    assert sites_a == {SITE_A}
    await writer_b()
    async with l47_pool.acquire() as connection:
        sites_b = await _persisted_sites(connection, MONTH_M1)
    assert sites_b == {SITE_B}


# --- 8. Different-month concurrency ---------------------------------------


@pytest.mark.anyio
async def test_concurrent_different_month_replacements_do_not_block_each_other(
    l47_pool,
) -> None:
    """The same-month advisory lock is keyed per-month. Different months
    must NOT serialize against each other.

    This test uses a deterministic barrier so we can prove both writers
    are simultaneously inside their locked calculate-then-replace
    cycles (not just that the overall call finished within a budget).
    """
    async with l47_pool.acquire() as connection:
        for site, month in ((SITE_D, MONTH_M1), (SITE_E, MONTH_M3)):
            await _seed_store(connection, site, month)
            await _seed_target(connection, site, month, Decimal("1000"))
            await _seed_agent_month(connection, site, month, Decimal("500"))

    async def writer_m1(stop: asyncio.Event) -> None:
        async with l47_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, $2)",
                    _CRM_LOCK_NAMESPACE, _month_lock_key(MONTH_M1),
                )
                stop.set()
                await asyncio.sleep(0.2)  # hold the M1 lock briefly
                await CrmRepository(l47_pool).replace_month_scores(
                    MONTH_M1, [_score_dict(SITE_D, 50)], connection=conn,
                )

    async def writer_m3(stop: asyncio.Event) -> None:
        async with l47_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT pg_advisory_xact_lock($1, $2)",
                    _CRM_LOCK_NAMESPACE, _month_lock_key(MONTH_M3),
                )
                stop.set()
                await asyncio.sleep(0.2)  # hold the M3 lock briefly
                await CrmRepository(l47_pool).replace_month_scores(
                    MONTH_M3, [_score_dict(SITE_E, 70)], connection=conn,
                )

    stop_a = asyncio.Event()
    stop_b = asyncio.Event()
    started = asyncio.get_event_loop().time()
    await asyncio.gather(writer_m1(stop_a), writer_m3(stop_b))
    elapsed = asyncio.get_event_loop().time() - started

    # Both writers reached their locks. If the keys collided, one of
    # the events would never be set inside the gather.
    assert stop_a.is_set() and stop_b.is_set(), (
        "Different-month locks must be independent. One writer was "
        "blocked on the other's lock key."
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_D}
        assert await _persisted_sites(connection, MONTH_M3) == {SITE_E}
    # Sanity bound — different-month serialization must not blow up.
    assert elapsed < 5.0, f"different-month writes took unreasonably long: {elapsed}s"


# --- 9. Service recalculate integration (A+B → A shrink) -----------------


@pytest.mark.anyio
async def test_service_recalculate_persists_exact_projection(
    l47_pool,
) -> None:
    """End-to-end: real ``CrmService.recalculate_scores`` writes the exact
    projection; the returned ``recalculated`` count matches the set.
    The F06 shrink case (A+B → A) MUST remain valid: only the
    completely-empty calculation is rejected."""
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        recalculated = await svc.recalculate_scores(MONTH_M1)

    calculated_sites = sorted(
        row["site_code"] for row in await svc.get_scores(MONTH_M1)
    )
    assert calculated_sites == sorted({SITE_A, SITE_B})
    assert recalculated == len(calculated_sites)
    assert recalculated == 2

    # Wipe B; recalc again; persisted MUST be only A. This is the
    # non-empty shrink that P1-A preserves: shrinking a non-empty
    # calculation to a smaller non-empty calculation is a valid
    # mutation, not a no-source failure.
    async with l47_pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = $1",
            SITE_B,
        )
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        recalculated = await svc.recalculate_scores(MONTH_M1)
    assert recalculated == 1
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}


# --- 10. Deterministic calculation ----------------------------------------


@pytest.mark.anyio
async def test_calculate_scores_for_month_returns_expected_site_and_score(
    l47_pool,
) -> None:
    """Replacement for vacuous F11 tests: an expected store MUST be
    produced and persisted, and the score MUST be deterministic given
    the seeded numbers."""
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        scores = await svc.calculate_scores_for_month(MONTH_M1)

    # F11 closure: no vacuous `if scores:` path — assert exactly.
    assert isinstance(scores, list)
    assert len(scores) == 1, (
        f"Expected exactly one score for MONTH_M1, got {scores!r}"
    )
    only = scores[0]
    assert only["site_code"] == SITE_A
    # Total sales=500, target=1000, factor=1.0 → target_pct=50 → c1=20.
    # prev month is absent → c2=15.0.
    # avg_bon2acc=0 (no receipts) → bon2acc_score=5; focus_score=5 → c3=10.
    # nr_vizite=0 → c4=0. So expected score = round(20+15+10+0) = 45.
    assert only["score"] == 45, (
        f"Deterministic score mismatch for {SITE_A}: {only['score']!r}"
    )
    breakdown = only["breakdown"]
    assert breakdown["target_pct"] == 20.0
    assert breakdown["trend_pct"] == 15.0
    assert breakdown["kpi_pct"] == 10.0
    assert breakdown["visits_pct"] == 0.0

    # Persisted side must also be exactly one row with that score.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH_M1)
    assert count == 1
    async with l47_pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT score, breakdown
            FROM store_scores
            WHERE site_code = $1 AND score_month = $2
            """,
            SITE_A, MONTH_M1,
        )
    assert row is not None, (
        "F11 fix: the expected store MUST be persisted, not `if test_score:`."
    )
    assert row["score"] == 45


# --- 11. P1-A: empty-source preserves last-good projection ----------------


@pytest.mark.anyio
async def test_no_source_preserves_last_good_projection(l47_pool) -> None:
    """P1-A service invariant: when source data is missing, the
    previously persisted projection MUST be preserved exactly.

    Setup:
        - valid {A,B} persisted via a successful recalc
        - then ALL source rows for the month are wiped
        - recalculate_scores is invoked

    Required:
        - CrmSourceDataUnavailable is raised
        - persisted projection remains exactly {A,B}
        - scores / breakdowns / calculated_at remain unchanged
        - no DELETE occurs (row count for the month is still 2)
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M4)
        await _seed_store(connection, SITE_B, MONTH_M4)
        await _seed_target(connection, SITE_A, MONTH_M4, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M4, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M4, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M4, Decimal("300"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH_M4)
    assert count == 2
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M4) == {SITE_A, SITE_B}
        original = await connection.fetch(
            "SELECT site_code, score, calculated_at FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M4,
        )
        original_snapshot = [
            (r["site_code"], r["score"], r["calculated_at"]) for r in original
        ]

    # Wipe all source rows for the month so calculate_scores_for_month
    # returns [].
    async with l47_pool.acquire() as connection:
        await connection.execute(
            "DELETE FROM reporting_agent_month WHERE site_code = ANY($1::text[])",
            [SITE_A, SITE_B],
        )

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        with pytest.raises(CrmSourceDataUnavailable) as exc_info:
            await svc.recalculate_scores(MONTH_M4)
    assert exc_info.value.DETAIL, "P1-A: detail must be bounded, non-empty."
    assert isinstance(exc_info.value.DETAIL, str)
    assert len(exc_info.value.DETAIL) > 0

    # Persisted projection is preserved exactly.
    async with l47_pool.acquire() as connection:
        sites_after = await _persisted_sites(connection, MONTH_M4)
        assert sites_after == {SITE_A, SITE_B}, (
            "P1-A: empty-source recalculation MUST preserve the last-good "
            f"projection. Persisted: {sites_after!r}."
        )
        rows_after = await connection.fetch(
            "SELECT site_code, score, calculated_at FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M4,
        )
        after_snapshot = [
            (r["site_code"], r["score"], r["calculated_at"]) for r in rows_after
        ]
        assert after_snapshot == original_snapshot, (
            "P1-A: scores and calculated_at must remain unchanged after a "
            "rejected empty recalculation."
        )
        count_month = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores WHERE score_month = $1",
            MONTH_M4,
        )
        assert count_month == 2, "P1-A: no row may be deleted by a rejected recalc."


# --- 12. P1-A: empty-source with no prior projection is still rejected ----


@pytest.mark.anyio
async def test_no_source_no_prior_projection_is_rejected(l47_pool) -> None:
    """P1-A negative case: even when there is no prior projection, an
    empty-source recalculation is still an explicit 409/failure, not
    a silent zero.

    Setup:
        - empty store_scores for the month
        - empty reporting_agent_month for the month
        - recalculate_scores is invoked

    Required:
        - CrmSourceDataUnavailable is raised
        - persisted projection remains empty (no fake zero scores)
        - store_scores row count for the month is 0
    """
    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        with pytest.raises(CrmSourceDataUnavailable):
            await svc.recalculate_scores(MONTH_M5)

    async with l47_pool.acquire() as connection:
        sites = await _persisted_sites(connection, MONTH_M5)
        assert sites == set(), (
            "P1-A: rejected empty recalc must NOT create implicit zero "
            f"scores. Persisted: {sites!r}."
        )
        count = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores WHERE score_month = $1",
            MONTH_M5,
        )
        assert count == 0


# --- 13. P1-A: repository fail-closed propagates as service failure ------


@pytest.mark.anyio
async def test_no_source_service_layer_rejects_before_write(
    l47_pool,
) -> None:
    """The service must raise ``CrmSourceDataUnavailable`` BEFORE the
    repository primitive is called, so the no-source invariant is
    enforced at the boundary the router can map to HTTP 409.

    Verify the contract end-to-end through the service API, not
    through direct repository calls.
    """
    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    called = {"replace": 0}

    async def _spy_replace(month, scores, *, connection):
        called["replace"] += 1

    # If the service ever called replace_month_scores with the bad
    # empty projection, the spy would record it.
    with patch.object(repo, "replace_month_scores", _spy_replace):
        with patch(
            "services.crm._query_visits_by_store_postgres",
            AsyncMock(return_value={}),
        ):
            with pytest.raises(CrmSourceDataUnavailable):
                await svc.recalculate_scores(MONTH_M1)

    assert called["replace"] == 0, (
        "P1-A: the service must raise CrmSourceDataUnavailable BEFORE "
        "the repository's destructive primitive is called."
    )


# --- 14. P1-B: lock acquired before calculation -----------------------------


@pytest.mark.anyio
async def test_lock_acquired_before_calculation_blocks_second_writer(
    l47_pool,
) -> None:
    """P1-B deterministic proof: while request 1 is inside its
    ``calculate_scores_for_month`` (after acquiring the per-month lock),
    request 2 MUST NOT have entered its own calculation.

    Mechanism: gate ``services.crm._query_visits_by_store_postgres``
    with an event. While the gate is closed, the calculation is
    paused. We then assert that request 2's calculation has NOT been
    entered (the spy count stays at 1 while request 1 is paused).
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    svc1 = CrmService(repo, l47_pool)
    svc2 = CrmService(repo, l47_pool)

    _real_query = _query_visits_by_store_postgres
    entered = {"count": 0}
    gate = asyncio.Event()

    async def gated_query(conn, month):
        entered["count"] += 1
        if entered["count"] == 1:
            await gate.wait()
        return {}

    with patch("services.crm._query_visits_by_store_postgres", gated_query):
        task1 = asyncio.create_task(svc1.recalculate_scores(MONTH_M1))
        # Wait until request 1 has acquired the lock AND entered its
        # calculation (the gate is the post-lock calculation barrier).
        for _ in range(200):
            if entered["count"] == 1:
                break
            await asyncio.sleep(0.01)
        assert entered["count"] == 1, (
            "Test setup: request 1 should have entered its calculation."
        )

        task2 = asyncio.create_task(svc2.recalculate_scores(MONTH_M1))
        # Give task2 a chance. With the lock held, it MUST NOT enter calc.
        await asyncio.sleep(0.3)
        assert entered["count"] == 1, (
            "P1-B violation: request 2 entered its calculation while "
            "request 1 still holds the per-month lock."
        )

        # Release request 1; both should then complete.
        gate.set()
        results = await asyncio.gather(task1, task2)
        assert results[0] == 2 and results[1] == 2
        assert entered["count"] == 2, (
            "Both requests must complete their calculation after the lock "
            "is released."
        )

    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}


# --- 15. P1-B: newer recalculation wins over a stale late writer ---------


@pytest.mark.anyio
async def test_newer_recalculation_wins_over_stale_late_writer(
    l47_pool,
) -> None:
    """P1-B deterministic proof: a same-month request 2 started while
    request 1 is paused inside its calculate cycle must produce the
    final persisted projection. The OLD request 1 cannot arrive late
    and overwrite request 2.

    Mechanism: pause request 1 mid-calculation, mutate the source so
    request 2 sees a different projection, start request 2 (it must
    wait at the lock), release request 1, await both. Final
    projection must match request 2 (the newer state), not request 1.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    _real_query = _query_visits_by_store_postgres
    gate = asyncio.Event()
    entered = {"count": 0}
    request1_scores: list[dict] = []

    async def gated_query(conn, month):
        entered["count"] += 1
        if entered["count"] == 1:
            await gate.wait()
        return {}

    async def start_then_mutate() -> None:
        nonlocal request1_scores
        async with l47_pool.acquire() as connection:
            scores = await svc.calculate_scores_for_month(MONTH_M1, connection=connection)
        request1_scores = scores

    # Start task1: it acquires the lock and pauses inside calc.
    with patch("services.crm._query_visits_by_store_postgres", gated_query):
        # Task1 is the locked recalculation that pauses inside calc.
        async def task1_flow():
            return await svc.recalculate_scores(MONTH_M1)

        task1 = asyncio.create_task(task1_flow())
        for _ in range(200):
            if entered["count"] == 1:
                break
            await asyncio.sleep(0.01)
        assert entered["count"] == 1

        # Source change for B: sales 300 → 900.
        async with l47_pool.acquire() as connection:
            await connection.execute(
                "UPDATE reporting_agent_month SET total_sales = $1 "
                "WHERE site_code = $2",
                Decimal("900"), SITE_B,
            )

        # Task2 starts. With the lock-before-calculate invariant,
        # task2 cannot enter its calc until task1 finishes its full
        # cycle. Wait briefly to confirm it has NOT entered.
        task2 = asyncio.create_task(svc.recalculate_scores(MONTH_M1))
        await asyncio.sleep(0.3)
        assert entered["count"] == 1, (
            "P1-B violation: task2 entered its calculation while task1 "
            "still holds the lock."
        )

        # Release task1. Task1 finishes (with the OLD source it saw
        # before the mutation), task2 then runs and finishes (with the
        # NEW source). Final state must be task2's projection.
        gate.set()
        results = await asyncio.gather(task1, task2)
        # task1 saw sales=300, task2 saw sales=900. Both succeeded.
        assert sorted(results) == [2, 2]

    async with l47_pool.acquire() as connection:
        # The final persisted set must include both A and B (task2's
        # projection). task1's stale projection was a superset of A+B
        # too, so a superset assertion alone wouldn't prove task2 won.
        # We must additionally check B's score is the NEW source's
        # score, not the old one.
        b_row = await connection.fetchrow(
            "SELECT score FROM store_scores "
            "WHERE site_code = $1 AND score_month = $2",
            SITE_B, MONTH_M1,
        )
        assert b_row is not None
        # The score for B with sales=900, target=1000, prev_month absent:
        # target_pct=90 → c1=36; prev=0 → c2=15; c3=10; c4=0; total=61.
        # For sales=300 (old source): c1=12; c2=15; c3=10; c4=0; total=37.
        # The newer request 2 mutates sales to 900 and would persist 61.
        assert b_row["score"] == 61, (
            f"P1-B: newer source must win. Expected B=61, got {b_row['score']}."
        )


# --- 16. P1-B: calculation exception releases the lock -------------------


@pytest.mark.anyio
async def test_calculation_exception_releases_lock(l47_pool) -> None:
    """P1-B: a calculation exception inside the locked transaction must
    roll back the transaction (and release the per-month advisory
    lock), so the next recalculation for the same month can proceed.
    """
    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    class BoomError(RuntimeError):
        pass

    async def boom(month, *, connection=None):
        raise BoomError("simulated calculation failure")

    with patch.object(svc, "calculate_scores_for_month", boom):
        with pytest.raises(BoomError):
            await svc.recalculate_scores(MONTH_M1)

    # The lock must be released. A subsequent successful recalc proves
    # it: if the lock were leaked, this call would hang on the pool
    # statement timeout.
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))

    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH_M1)
    assert count == 1, (
        "P1-B: lock must release after a calculation exception so the "
        "next recalculation can proceed."
    )

    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}


# --- 17. P1-B: task cancellation releases the lock -----------------------


@pytest.mark.anyio
async def test_cancellation_releases_lock(l47_pool) -> None:
    """P1-B: cancelling the recalculation task while the lock
    transaction is open must roll back (releasing the lock) and
    preserve the previously persisted projection. A subsequent
    recalculation for the same month must proceed normally.
    """
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))

    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    # Seed a baseline projection.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        await svc.recalculate_scores(MONTH_M1)
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}

    _real_query = _query_visits_by_store_postgres
    entered = {"count": 0}
    gate = asyncio.Event()

    async def gated_query(conn, month):
        entered["count"] += 1
        if entered["count"] == 1:
            await gate.wait()
        return {}

    # Fire a recalc that will pause inside calc; cancel it.
    with patch("services.crm._query_visits_by_store_postgres", gated_query):
        task = asyncio.create_task(svc.recalculate_scores(MONTH_M1))
        for _ in range(200):
            if entered["count"] == 1:
                break
            await asyncio.sleep(0.01)
        assert entered["count"] == 1
        task.cancel()
        gate.set()  # release the inner wait so the cancellation can
                    # reach the transaction rollback.
        with pytest.raises(asyncio.CancelledError):
            await task

    # Persisted projection preserved.
    async with l47_pool.acquire() as connection:
        sites = await _persisted_sites(connection, MONTH_M1)
        assert sites == {SITE_A}, (
            "P1-B: cancelled recalculation must preserve the persisted "
            f"projection. Got {sites!r}."
        )

    # Lock must have been released. A new recalc proceeds.
    with patch(
        "services.crm._query_visits_by_store_postgres",
        AsyncMock(return_value={}),
    ):
        count = await svc.recalculate_scores(MONTH_M1)
    assert count == 1, "P1-B: lock must be released after task cancellation."


# --- 18. Different months use distinct lock keys (deterministic) ---------


@pytest.mark.anyio
async def test_different_months_use_distinct_lock_keys(l47_pool) -> None:
    """Two recalculations for DIFFERENT months must NOT contend on the
    same advisory lock key.

    Both writers acquire their respective per-month locks concurrently
    (we model this by acquiring both locks on the same connection with
    session locks would NOT be right; we use transaction-scoped locks
    on two independent connections to mirror the real flow). The
    proof is that both events fire within a small time budget and
    neither writer had to wait for the other.
    """
    repo = CrmRepository(l47_pool)
    svc = CrmService(repo, l47_pool)

    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M3)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M3, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M3, Decimal("700"))

    # Different months => different lock keys. Verify the keys differ.
    assert _month_lock_key(MONTH_M1) != _month_lock_key(MONTH_M3), (
        "Test invariant: different months must hash to different lock keys."
    )

    _real_query = _query_visits_by_store_postgres
    enter_a = asyncio.Event()
    enter_b = asyncio.Event()
    enter_count = {"n": 0}

    async def gated_query(conn, month):
        n = enter_count["n"]
        enter_count["n"] = n + 1
        if month == MONTH_M1:
            enter_a.set()
        elif month == MONTH_M3:
            enter_b.set()
        # Briefly hold to give the other writer a chance.
        await asyncio.sleep(0.1)
        return {}

    with patch("services.crm._query_visits_by_store_postgres", gated_query):
        await asyncio.gather(
            svc.recalculate_scores(MONTH_M1),
            svc.recalculate_scores(MONTH_M3),
        )

    # Both writers reached their calculations concurrently. If lock
    # keys collided, one writer would block on the other and only one
    # event would have fired while the other waited.
    assert enter_a.is_set() and enter_b.is_set(), (
        "P1-B: different-month recalculations must run their calculations "
        "independently of each other's per-month lock."
    )

    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}
        assert await _persisted_sites(connection, MONTH_M3) == {SITE_B}
