from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pandas as pd
import pytest

from db.connection import close_db_pool, get_pool
from services.importer import import_sales_dataframe, reserve_snapshot
from services.sales_generation import (
    build_sales_generation_manifest,
    canonical_json_sha256,
    canonical_sales_stage_rows_sha256,
    fenced_generation_heartbeat,
    stage_sales_generation_rows,
)
from services.sales_generation_flow import (
    claim_validated_sales_generation,
    persist_validated_sales_generation,
    promote_sales_generation,
    rollback_sales_generation,
)


TEST_MONTH = "2099-12"
MIGRATION_037 = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "037_sales_generation_stage_integrity.sql"
)


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
                "Brand": None,
                "Pret": Decimal("15.50"),
                "Valoare": Decimal("-15.50"),
                "Locatie": "Stage Întreg 😀",
                "Firma": "Mobiup",
                "ASM": "Manager",
                "Regional": "Regional",
                "Nr": "BON2",
                "Categorie": None,
                "SubCategorie": None,
                "Agent": "Agent 2",
                "is_cartela": True,
                "is_return": True,
            },
        ]
    )


async def cleanup(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "ALTER TABLE sales_generation_promotions DISABLE TRIGGER trg_sales_generation_promotions_immutable"
    )
    try:
        await conn.execute(
            "DELETE FROM sales_generation_promotions WHERE import_month = $1",
            TEST_MONTH,
        )
    finally:
        await conn.execute(
            "ALTER TABLE sales_generation_promotions ENABLE TRIGGER trg_sales_generation_promotions_immutable"
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
        "ALTER TABLE sales_import_stage_rows DISABLE TRIGGER trg_sales_stage_mutation"
    )
    try:
        await conn.execute(
            "DELETE FROM import_snapshots WHERE import_month = $1",
            TEST_MONTH,
        )
    finally:
        await conn.execute(
            "ALTER TABLE sales_import_stage_rows ENABLE TRIGGER trg_sales_stage_mutation"
        )


def test_stage_digest_preserves_order_and_duplicate_multiplicity() -> None:
    frame = sales_frame()
    digest = canonical_sales_stage_rows_sha256(frame, import_month=TEST_MONTH)

    assert digest != canonical_sales_stage_rows_sha256(
        frame.iloc[::-1].reset_index(drop=True),
        import_month=TEST_MONTH,
    )
    assert digest != canonical_sales_stage_rows_sha256(
        pd.concat([frame, frame], ignore_index=True),
        import_month=TEST_MONTH,
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
            assert staged.manifest is not None
            assert staged.manifest["stage_rows_sha256"] == stage_digest
            assert stage_digest == canonical_sales_stage_rows_sha256(
                sales_frame(),
                import_month=TEST_MONTH,
            )

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

            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                await conn.execute(
                    "DELETE FROM sales_import_stage_rows WHERE snapshot_id = $1",
                    staged.snapshot_id,
                )
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_validation_rejects_stage_changed_after_source_digest() -> None:
    """A matching set of coarse controls cannot replace the approved rows."""
    pool = await get_pool()
    generation_token = str(uuid4())
    owner_id = str(uuid4())
    try:
        async with pool.acquire() as conn:
            await cleanup(conn)
            frame = sales_frame()
            snapshot_id = await reserve_snapshot(
                conn,
                TEST_MONTH,
                "tampered-before-validation.xlsx",
                len(frame),
                source_sha256="c" * 64,
                cutoff_date=date(2099, 12, 2),
                generation_token=generation_token,
                owner_id=owner_id,
            )
            manifest = build_sales_generation_manifest(
                frame,
                source_sha256="c" * 64,
                cutoff_date=date(2099, 12, 2),
                rows_in_file=len(frame),
                rows_filtered=0,
            )
            manifest["anomalies"] = []
            manifest["generation_state"] = "validated"
            manifest["stage_rows_sha256"] = canonical_sales_stage_rows_sha256(
                frame,
                import_month=TEST_MONTH,
            )
            manifest_sha256 = canonical_json_sha256(manifest)

            async with conn.transaction():
                await fenced_generation_heartbeat(
                    conn,
                    snapshot_id=snapshot_id,
                    generation_token=generation_token,
                    owner_id=owner_id,
                    lease_seconds=2 * 60 * 60,
                )
                await stage_sales_generation_rows(
                    conn,
                    frame,
                    snapshot_id=snapshot_id,
                    import_month=TEST_MONTH,
                )
                await conn.execute(
                    "ALTER TABLE sales_import_stage_rows DISABLE TRIGGER trg_sales_stage_mutation"
                )
                await conn.execute(
                    """
                    WITH removed AS (
                        DELETE FROM sales_import_stage_rows
                        WHERE snapshot_id = $1 AND row_number = 1
                        RETURNING import_month, sale_date, site_code, locatie, firma,
                                  regional, asm, bon_nr, item_code, item_name, brand,
                                  category, subcategory, quantity, unit_price,
                                  total_value, agent, is_cartela, is_return
                    )
                    INSERT INTO sales_import_stage_rows (
                        snapshot_id, row_number, import_month, sale_date, site_code,
                        locatie, firma, regional, asm, bon_nr, item_code, item_name,
                        brand, category, subcategory, quantity, unit_price, total_value,
                        agent, is_cartela, is_return
                    )
                    SELECT $1, 1, import_month, sale_date, site_code, locatie, firma,
                           regional, asm, bon_nr, item_code, item_name, brand, category,
                           subcategory, quantity, unit_price, total_value,
                           agent || '-tampered', is_cartela, is_return
                    FROM removed
                    """,
                    snapshot_id,
                )
                await conn.execute(
                    "ALTER TABLE sales_import_stage_rows ENABLE TRIGGER trg_sales_stage_mutation"
                )
                with pytest.raises(
                    asyncpg.PostgresError,
                    match="manifest.*does not match staged rows",
                ):
                    await persist_validated_sales_generation(
                        conn,
                        snapshot_id=snapshot_id,
                        generation_token=generation_token,
                        owner_id=owner_id,
                        manifest=manifest,
                        manifest_sha256=manifest_sha256,
                        coverage_report={},
                    )
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_037_upgrade_verifies_legacy_controls_before_rollback_flow() -> None:
    """036 data is backfilled only after controls verify, then remains rollback-safe."""
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await cleanup(conn)
            first = await import_sales_dataframe(
                conn,
                sales_frame(),
                "036-first.xlsx",
                source_sha256="d" * 64,
                cutoff_date=date(2099, 12, 2),
                requested_by_sub="test:036-first",
            )
            second = await import_sales_dataframe(
                conn,
                sales_frame(),
                "036-second.xlsx",
                source_sha256="e" * 64,
                cutoff_date=date(2099, 12, 2),
                requested_by_sub="test:036-second",
            )

            await conn.execute(
                """
                DROP TRIGGER IF EXISTS trg_verify_sales_generation_head_target
                    ON sales_generation_heads;
                DROP TRIGGER IF EXISTS trg_sales_stage_mutation
                    ON sales_import_stage_rows;
                DROP TRIGGER IF EXISTS trg_import_snapshot_sales_provenance
                    ON import_snapshots;
                DROP FUNCTION IF EXISTS verify_sales_generation_head_target();
                DROP FUNCTION IF EXISTS guard_sales_stage_mutation();
                DROP FUNCTION IF EXISTS sales_snapshot_is_retained(INTEGER);
                DROP FUNCTION IF EXISTS guard_import_snapshot_sales_provenance();
                DROP FUNCTION IF EXISTS sales_stage_rows_sha256(INTEGER);
                DROP FUNCTION IF EXISTS sales_stage_digest_scalar(TEXT);
                ALTER TABLE import_snapshots
                    DROP CONSTRAINT IF EXISTS ck_import_snapshots_stage_rows_sha256;
                UPDATE import_snapshots
                SET manifest = manifest - 'stage_rows_sha256'
                WHERE import_month = '2099-12';
                ALTER TABLE import_snapshots DROP COLUMN stage_rows_sha256;
                """
            )
            await conn.execute(
                """
                UPDATE import_snapshots
                SET manifest = jsonb_set(manifest, '{rows_imported}', '999'::jsonb)
                WHERE id = $1
                """,
                first.snapshot_id,
            )
            with pytest.raises(
                asyncpg.PostgresError,
                match="cannot certify legacy sales staging",
            ):
                await conn.execute(MIGRATION_037.read_text(encoding="utf-8"))
            await conn.execute(
                """
                UPDATE import_snapshots
                SET manifest = jsonb_set(manifest, '{rows_imported}', '2'::jsonb)
                WHERE id = $1
                """,
                first.snapshot_id,
            )
            await conn.execute(MIGRATION_037.read_text(encoding="utf-8"))

            legacy_digests = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM import_snapshots
                WHERE id = ANY($1::integer[])
                  AND stage_rows_sha256 IS NOT NULL
                """,
                [first.snapshot_id, second.snapshot_id],
            )
            assert legacy_digests == 2

            third = await import_sales_dataframe(
                conn,
                sales_frame(),
                "037-third.xlsx",
                source_sha256="f" * 64,
                cutoff_date=date(2099, 12, 2),
                requested_by_sub="test:037-third",
            )
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_import_stage_rows WHERE snapshot_id = $1",
                first.snapshot_id,
            ) == len(sales_frame())
            assert third.generation_token is not None
            assert third.manifest_sha256 is not None
            rollback_snapshot_id, rollback_rows, rollback_revision = await rollback_sales_generation(
                conn,
                current_snapshot_id=third.snapshot_id,
                current_generation_token=third.generation_token,
                expected_manifest_sha256=third.manifest_sha256,
                requested_by_sub="test:037-upgrade-rollback",
                reason="Rollback dupa upgrade 036 la 037",
            )
            assert rollback_rows == len(sales_frame())
            assert rollback_revision == 4
            assert await conn.fetchval(
                "SELECT stage_rows_sha256 FROM import_snapshots WHERE id = $1",
                rollback_snapshot_id,
            ) is not None
    finally:
        async with pool.acquire() as conn:
            await cleanup(conn)
        await close_db_pool()
