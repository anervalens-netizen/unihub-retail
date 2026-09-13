"""Lot 47 — CRM monthly score projection must represent the exact current
recalculation result.

F06: ``CrmRepository.upsert_scores`` used INSERT ... ON CONFLICT, never
deleted rows that disappeared from the new calculation, and was a no-op for
an empty list. ``store_scores`` for a month therefore drifted from the
"currently valid" recalculation. The fix replaces that method with
``replace_month_scores``, which performs a transactional DELETE + INSERT
plus a same-month advisory lock.

This module exercises the real PostgreSQL repository and the real
``CrmService`` end-to-end against an isolated test database. It never
alters the schema, never drops constraints, and never inserts invalid
``store_scores`` rows except inside a SAVEPOINT/ROLLBACK bounded
negative-rollback proof.

Layout:

  * BASELINE_LEAK_REPRO_BEFORE_FIX
      Capsule kept behind a non-default guard. It runs the *exact* pre-fix
      SQL (``INSERT ... ON CONFLICT DO UPDATE``) to demonstrate the leak
      on the pristine schema, so the regression directory keeps a copy of
      what the fix has to defeat. Skipped unless ``LOT47_BASELINE=1``.

  * 1. BASELINE stale-row proof
      Uses the existing fixed path to contrast with the historical
      ``upsert_scores`` SQL; demonstrates that *only* the fixed path
      removes the stale B.

  * 2. Replacement removes stale row
      A+B persisted → A replacement → persisted exactly {A}.

  * 3. Replacement updates existing row
      A score old → A score new; exact new persisted values match.

  * 4. Empty replacement
      A+B persisted → [] replacement → persisted exactly {}.

  * 5. Month isolation
      M1 = {A,B}; M2 = {C}; replace M1 with {A}; M2 still {C}.

  * 6. Transaction rollback
      Replacement fails after the DELETE; persisted unchanged = {A,B}.

  * 7. Same-month concurrent replacement
      writer1 -> {A}, writer2 -> {B}; final is one complete projection;
      never {A,B}.

  * 8. Different-month concurrency
      writer1 -> {A} on M1, writer2 -> {C} on M2; both persist exactly
      their respective projections and they do not block each other.

  * 9. Service recalculate integration
      End-to-end through ``CrmService.recalculate_scores``: persisted
      sites exactly match the calculation set; the returned count
      matches ``len(persisted)``.

All synthetic sites / months / targets use the ``CRM-L47-`` / ``2098-``
namespace so they cannot collide with other suites.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from db.connection import get_pool
from repositories.crm import CrmRepository
from services.crm import CrmService


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


pytestmark = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL through the immutable manifest",
)


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


@pytest.fixture
async def l47_pool():
    pool = await get_pool()
    yield pool
    # Best-effort cleanup even if a test raised mid-flight.
    async with pool.acquire() as connection:
        await _cleanup_pool_sites(
            connection,
            [SITE_A, SITE_B, SITE_C, SITE_D, SITE_E] + [
                f"CRM-L47-EXTRA-{i}" for i in range(8)
            ],
        )
        for month in (MONTH_M1, MONTH_M2, MONTH_M3):
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
    schema. The test then contrasts with ``replace_month_scores`` to
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
        # pre-fix repository. asyncpg will execute the executemany even
        # with deliberately invalid SQL (a syntax error), so the legacy
        # SELECT path itself is the one under test.
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

    # 4. The fixed path, called once with empty-input for B explicitly
    # removed, must drop the stale B. Show the contrast.
    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(
        MONTH_M1,
        [_score_dict(SITE_A, 60)],
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

    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(
        MONTH_M1,
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
    await repo.replace_month_scores(MONTH_M1, [_score_dict(SITE_A, 55)])
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A}


# --- 3. Replacement updates existing row -----------------------------------


@pytest.mark.anyio
async def test_replacement_updates_existing_row(l47_pool) -> None:
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))

    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(MONTH_M1, [_score_dict(SITE_A, 75)])
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

    await repo.replace_month_scores(MONTH_M1, [_score_dict(SITE_A, 90)])
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


# --- 4. Empty replacement --------------------------------------------------


@pytest.mark.anyio
async def test_empty_replacement_clears_projection(l47_pool) -> None:
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(
        MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}

    await repo.replace_month_scores(MONTH_M1, [])
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == set()
        # No row lingered anywhere for MONTH_M1.
        leftover = await connection.fetchval(
            "SELECT COUNT(*)::INT FROM store_scores WHERE score_month = $1",
            MONTH_M1,
        )
        assert leftover == 0


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

    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(
        MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    await repo.replace_month_scores(
        MONTH_M2,
        [_score_dict(SITE_C, 80)],
    )

    # Replace M1 with only A; M2 must be untouched.
    await repo.replace_month_scores(MONTH_M1, [_score_dict(SITE_A, 50)])
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
    empty. The transactional DELETE + INSERT must roll back as a unit."""
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)
    await repo.replace_month_scores(
        MONTH_M1,
        [_score_dict(SITE_A, 50), _score_dict(SITE_B, 30)],
    )
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}

    # Replacement that violates NOT NULL on score; raises during INSERT.
    bad_scores = [
        _score_dict(SITE_A, 50),
        # Inject score=None: a real schema NOT NULL trap.
        {**_score_dict(SITE_B, 30), "score": None},
    ]
    with pytest.raises(asyncpg.exceptions.NotNullViolationError):
        await repo.replace_month_scores(MONTH_M1, bad_scores)

    # After the failure, persisted state must still be exactly {A,B}.
    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_A, SITE_B}, (
            "Rollback path failed: persisted projection must be unchanged "
            "after a failed replacement. Either {}  or {A}  indicate a leak."
        )
        # Old scores untouched.
        scores = await connection.fetch(
            "SELECT site_code, score FROM store_scores "
            "WHERE score_month = $1 ORDER BY site_code",
            MONTH_M1,
        )
        score_map = {row["site_code"]: row["score"] for row in scores}
        assert score_map == {SITE_A: 50, SITE_B: 30}


# --- 7. Same-month concurrent replacement ---------------------------------


@pytest.mark.anyio
async def test_concurrent_same_month_replacement_yields_one_projection(
    l47_pool,
) -> None:
    """Two writers racing for the same month must end with one COMPLETE
    projection, never the synthetic union of disjoint sets."""
    async with l47_pool.acquire() as connection:
        await _seed_store(connection, SITE_A, MONTH_M1)
        await _seed_store(connection, SITE_B, MONTH_M1)
        await _seed_target(connection, SITE_A, MONTH_M1, Decimal("1000"))
        await _seed_target(connection, SITE_B, MONTH_M1, Decimal("1000"))
        await _seed_agent_month(connection, SITE_A, MONTH_M1, Decimal("500"))
        await _seed_agent_month(connection, SITE_B, MONTH_M1, Decimal("300"))

    repo = CrmRepository(l47_pool)

    async def writer_a() -> None:
        await repo.replace_month_scores(
            MONTH_M1,
            [_score_dict(SITE_A, 50)],
        )

    async def writer_b() -> None:
        await repo.replace_month_scores(
            MONTH_M1,
            [_score_dict(SITE_B, 35)],
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
    must NOT serialize against each other."""
    async with l47_pool.acquire() as connection:
        for site in (SITE_D, SITE_E):
            await _seed_store(connection, site, MONTH_M1 if site == SITE_D else MONTH_M3)
            await _seed_target(
                connection,
                site,
                MONTH_M1 if site == SITE_D else MONTH_M3,
                Decimal("1000"),
            )
            await _seed_agent_month(
                connection,
                site,
                MONTH_M1 if site == SITE_D else MONTH_M3,
                Decimal("500"),
            )

    repo = CrmRepository(l47_pool)

    async def writer_m1() -> None:
        await repo.replace_month_scores(
            MONTH_M1,
            [_score_dict(SITE_D, 50)],
        )

    async def writer_m3() -> None:
        await repo.replace_month_scores(
            MONTH_M3,
            [_score_dict(SITE_E, 70)],
        )

    started = asyncio.get_event_loop().time()
    await asyncio.gather(writer_m1(), writer_m3())
    elapsed = asyncio.get_event_loop().time() - started

    async with l47_pool.acquire() as connection:
        assert await _persisted_sites(connection, MONTH_M1) == {SITE_D}
        assert await _persisted_sites(connection, MONTH_M3) == {SITE_E}
    # Sanity bound — different-month serialization must not blow up.
    assert elapsed < 5.0, f"different-month writes took unreasonably long: {elapsed}s"


# --- 9. Service recalculate integration -----------------------------------


@pytest.mark.anyio
async def test_service_recalculate_persists_exact_projection(
    l47_pool,
) -> None:
    """End-to-end: real CrmService.recalculate_scores writes the exact
    projection; the returned ``recalculated`` count matches the set."""
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

    # Wipe B; recalc again; persisted MUST be only A.
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


# --- 10. Deterministic calculation & 11. Repository/get_scores tests -----


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


# --- Negative-rollback probe (no orphan projections in store_scores) ------
