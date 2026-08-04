"""Isolated PostgreSQL proof for P&L authoritative-generation fencing."""
from __future__ import annotations

import asyncio
import os
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import services.store_pnl_import as store_pnl_import_module

from db.connection import close_db_pool, get_pool
from services.store_pnl_import import (
    PnlGenerationConflict,
    PnlRow,
    apply_generation,
    coverage_sha256,
    parse_authority_manifest,
    rollback_generation,
    stage_generation,
)


PERIOD = date(2197, 10, 1)
COMPANIES = ("Mobicell", "Mobiup")


def _candidate(company: str, amount: str, revision: str) -> PnlRow:
    return PnlRow(
        company_name=company,
        period=PERIOD,
        source_site_code="P0B-CAS",
        source_location_name="P0B CAS test",
        category_code="v1",
        category_name="Venit",
        amount=Decimal(amount),
        source_file=f"{company}-{revision}.xls",
        source_sha256=("a" if company == "Mobicell" else "b") * 64,
    )


def _authority(rows: list[PnlRow], revision: str):
    return parse_authority_manifest({
        "version": 1,
        "approval_id": f"P0B-{revision}",
        "scopes": [
            {
                "company_name": item.company_name,
                "period": item.period.isoformat(),
                "revision_id": f"{revision}:{item.company_name}",
                "parent_revision_id": "legacy",
        "cutoff": "2197-10-31",
                "source_path": item.source_file,
                "source_sha256": item.source_sha256,
                "complete_snapshot": True,
                "expected_row_count": 1,
                "expected_total_amount": str(item.amount),
                "coverage_sha256": coverage_sha256([item]),
            }
            for item in rows
        ],
    })


async def _set_finance_role(connection) -> None:
    await connection.execute("SET ROLE unihub_finance_import")


async def _reset_role(connection) -> None:
    await connection.execute("RESET ROLE")


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL after migration 039 is in the immutable manifest",
)
async def test_authoritative_generation_cas_and_inverse_rollback_preserve_estimates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two promotions sharing a preimage race; exactly one wins and rollback is inverse."""
    monkeypatch.setattr(
        store_pnl_import_module,
        "verify_database_connection_authority",
        AsyncMock(),
    )
    pool = await get_pool()
    try:
        async with pool.acquire() as connection:
            # The release role is intentionally not provisioned by the app
            # runtime.  The isolated DB supplies it explicitly for this proof.
            await connection.execute(
                "DO $$ BEGIN CREATE ROLE unihub_finance_import NOLOGIN; "
                "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
            )
            await connection.execute(
                "DO $$ BEGIN EXECUTE format('GRANT unihub_finance_import TO %I', current_user); END $$"
            )
            await connection.execute(
                "GRANT SELECT, INSERT ON store_pnl_generations TO unihub_finance_import"
            )
            await connection.execute(
                "GRANT SELECT ON store_pnl_generation_heads TO unihub_finance_import"
            )
            await connection.execute(
                "GRANT SELECT, INSERT ON store_pnl_generation_scopes, store_pnl_generation_rows, "
                "store_pnl_generation_ledger TO unihub_finance_import"
            )
            await connection.execute(
                "GRANT SELECT, INSERT, DELETE ON store_pnl_monthly TO unihub_finance_import"
            )
            await connection.execute(
                "GRANT USAGE, SELECT ON SEQUENCE store_pnl_monthly_id_seq, "
                "store_pnl_generation_ledger_id_seq TO unihub_finance_import"
            )
            for company in COMPANIES:
                await connection.execute(
                    """
                    INSERT INTO store_pnl_monthly (
                        company_name, period, source_site_code, source_location_name,
                        category_code, category_name, amount, data_kind, source_file, source_sha256
                    ) VALUES ($1,$2,'P0B-CAS','P0B CAS test','v1','Venit',100.00,'actual','legacy.xls',$3),
                             ($1,$2,'P0B-CAS','P0B CAS test','v1','Venit',999.00,'estimated','estimate.xls',$3)
                    """,
                    company,
                    PERIOD,
                    "c" * 64,
                )

            first_rows = [_candidate(company, "200.00", "r1") for company in COMPANIES]
            second_rows = [_candidate(company, "300.00", "r2") for company in COMPANIES]
            await _set_finance_role(connection)
            try:
                first = await stage_generation(
                    connection, _authority(first_rows, "r1"),
                    {(item.company_name, item.period): [item] for item in first_rows},
                )
                second = await stage_generation(
                    connection, _authority(second_rows, "r2"),
                    {(item.company_name, item.period): [item] for item in second_rows},
                )
            finally:
                await _reset_role(connection)

        async def promote(result):
            async with pool.acquire() as connection:
                await _set_finance_role(connection)
                try:
                    await apply_generation(
                        connection, result.generation_id, result.generation_manifest_sha256
                    )
                    return result
                finally:
                    await _reset_role(connection)

        outcomes = await asyncio.gather(promote(first), promote(second), return_exceptions=True)
        winners = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
        losers = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(winners) == len(losers) == 1
        assert isinstance(losers[0], PnlGenerationConflict)
        winner = winners[0]

        async with pool.acquire() as connection:
            estimates = await connection.fetch(
                """
                SELECT company_name, amount FROM store_pnl_monthly
                WHERE period = $1 AND source_site_code = 'P0B-CAS' AND data_kind = 'estimated'
                ORDER BY company_name
                """,
                PERIOD,
            )
            assert [(record["company_name"], record["amount"]) for record in estimates] == [
                ("Mobicell", Decimal("999.00")), ("Mobiup", Decimal("999.00"))
            ]
            await _set_finance_role(connection)
            try:
                inverse = await rollback_generation(
                    connection, winner.generation_id, winner.generation_manifest_sha256
                )
            finally:
                await _reset_role(connection)
            assert inverse.generation_id != winner.generation_id
            actuals = await connection.fetch(
                """
                SELECT company_name, amount FROM store_pnl_monthly
                WHERE period = $1 AND source_site_code = 'P0B-CAS' AND data_kind = 'actual'
                ORDER BY company_name
                """,
                PERIOD,
            )
            assert [(record["company_name"], record["amount"]) for record in actuals] == [
                ("Mobicell", Decimal("100.00")), ("Mobiup", Decimal("100.00"))
            ]
    finally:
        await close_db_pool()
