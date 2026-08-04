from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import asyncpg
import pandas as pd
import pytest

from db.connection import close_db_pool, get_pool
from services.importer import import_sales_dataframe
from services.sales_generation_flow import (
    claim_validated_sales_generation,
    promote_sales_generation,
)


TEST_MONTH = "2099-12"


def sales_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Data": date(2099, 12, 1),
                "SiteCode": "STAGEA",
                "ItemCode": "ITEM01",
                "ItemName": "Produs 1",
                "Cantitate": 2,
                "Brand": "Brand",
                "Pret": 10,
                "Valoare": 20,
                "Locatie": "Stage Integrity A",
                "Firma": "Mobiup",
                "ASM": "Manager",
                "Regional": "Regional",
                "Nr": "BON1",
                "Categorie": "Accesorii",
                "SubCategorie": "Test",
                "Agent": "Agent 1",
                "is_cartela": False,
                "is_return": False,
            },
            {
                "Data": date(2099, 12, 2),
                "SiteCode": "STAGEB",
                "ItemCode": "ITEM02",
                "ItemName": "Produs 2",
                "Cantitate": 1,
                "Brand": "Brand",
                "Pret": 15,
                "Valoare": 15,
                "Locatie": "Stage Integrity B",
                "Firma": "Mobiup",
                "ASM": "Manager",
                "Regional": "Regional",
                "Nr": "BON2",
                "Categorie": "Accesorii",
                "SubCategorie": "Test",
                "Agent": "Agent 2",
                "is_cartela": False,
                "is_return": False,
            },
        ]
    )


async def cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "DELETE FROM sales_generation_promotions WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(
        "DELETE FROM sales_generation_heads WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(
        "DELETE FROM sales_transactions WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(
        "UPDATE import_snapshots SET previous_snapshot_id = NULL WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(
        "DELETE FROM import_snapshots WHERE import_month = $1",
        TEST_MONTH,
    )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_validated_stage_digest_is_immutable_and_required_by_head() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await cleanup(conn)
            staged = await import_sales_dataframe(
                conn,
                sales_frame(),
                "stage-integrity.xlsx",
                source_sha256="a" * 64,
                cutoff_date=date(2099, 12, 2),
                stage_only=True,
                requested_by_sub="test:stage-integrity",
            )
            assert staged.generation_state == "validated"
            assert staged.generation_token is not None
            assert staged.owner_id is not None
            assert staged.manifest_sha256 is not None

            stage_digest = await conn.fetchval(
                "SELECT stage_rows_sha256 FROM import_snapshots WHERE id = $1",
                staged.snapshot_id,
            )
            assert isinstance(stage_digest, str)
            assert len(stage_digest) == 64

            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                await conn.execute(
                    """
                    UPDATE sales_import_stage_rows
                    SET agent = agent || '-tampered'
                    WHERE snapshot_id = $1 AND row_number = 1
                    """,
                    staged.snapshot_id,
                )

            with pytest.raises(asyncpg.PostgresError, match="provenance"):
                await conn.execute(
                    "UPDATE import_snapshots SET source_sha256 = $2 WHERE id = $1",
                    staged.snapshot_id,
                    "b" * 64,
                )

            promoter_owner = str(uuid4())
            await claim_validated_sales_generation(
                conn,
                snapshot_id=staged.snapshot_id,
                generation_token=staged.generation_token,
                expected_manifest_sha256=staged.manifest_sha256,
                new_owner_id=promoter_owner,
            )
            rows_imported, revision = await promote_sales_generation(
                conn,
                snapshot_id=staged.snapshot_id,
                generation_token=staged.generation_token,
                owner_id=promoter_owner,
                expected_manifest_sha256=staged.manifest_sha256,
                requested_by_sub="test:promote-stage-integrity",
            )
            assert rows_imported == 2
            assert revision == 1

            with pytest.raises(asyncpg.PostgresError, match="retained sales staging"):
                await conn.execute(
                    "DELETE FROM sales_import_stage_rows WHERE snapshot_id = $1",
                    staged.snapshot_id,
                )
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()
