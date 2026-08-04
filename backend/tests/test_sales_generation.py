from __future__ import annotations

import os
from datetime import date
from uuid import uuid4
from unittest.mock import AsyncMock

import pandas as pd
import pytest

import services.importer as importer
import services.sales_generation_flow as sales_generation_flow
from db.connection import close_db_pool, get_pool
from services.importer import import_sales_dataframe
from services.sales_generation import (
    SalesGenerationConflictError,
    SalesAnomalyClassification,
    SalesPolicyValidationError,
    build_sales_generation_manifest,
    compare_sales_generation_manifests,
    manifest_requires_override,
)
from services.sales_generation_flow import (
    claim_validated_sales_generation,
    promote_sales_generation,
    rollback_sales_generation,
)


TEST_MONTH = "2099-11"


def sales_frame(*, include_second_row: bool = False) -> pd.DataFrame:
    rows = [
        {
            "Data": date(2099, 11, 1),
            "SiteCode": "GENA",
            "ItemCode": "ITEM01",
            "ItemName": "Produs 1",
            "Cantitate": 2,
            "Brand": "Brand",
            "Pret": 10,
            "Valoare": 20,
            "Locatie": "Generation A",
            "Firma": "Mobiup",
            "ASM": "Manager",
            "Regional": "Regional",
            "Nr": "BON1",
            "Categorie": "Accesorii",
            "SubCategorie": "Test",
            "Agent": "Agent 1",
            "is_cartela": False,
            "is_return": False,
        }
    ]
    if include_second_row:
        rows.append(
            {
                **rows[0],
                "Data": date(2099, 11, 2),
                "SiteCode": "GENB",
                "Locatie": "Generation B",
                "Nr": "BON1",
                "ItemCode": "ITEM02",
                "ItemName": "Produs 2",
                "Cantitate": 1,
                "Valoare": 10,
            }
        )
    return pd.DataFrame(rows)


def manifest(frame: pd.DataFrame, *, cutoff: date) -> dict:
    return build_sales_generation_manifest(
        frame,
        source_sha256="a" * 64,
        cutoff_date=cutoff,
        rows_in_file=len(frame),
        rows_filtered=0,
    )


def test_business_hash_preserves_duplicate_row_multiplicity() -> None:
    single = sales_frame()
    duplicate = pd.concat([single, single], ignore_index=True)

    single_manifest = manifest(single, cutoff=date(2099, 11, 1))
    duplicate_manifest = manifest(duplicate, cutoff=date(2099, 11, 1))

    assert single_manifest["rows_imported"] == 1
    assert duplicate_manifest["rows_imported"] == 2
    assert duplicate_manifest["business_sha256"] != single_manifest["business_sha256"]
    assert duplicate_manifest["receipt_count"] == 1


def test_authoritative_replace_classifies_snapshot_differences_as_informational() -> None:
    previous = manifest(sales_frame(include_second_row=True), cutoff=date(2099, 11, 2))
    missing_site_day = manifest(sales_frame(), cutoff=date(2099, 11, 2))
    regressed_cutoff = manifest(sales_frame(), cutoff=date(2099, 11, 1))

    assert previous["receipt_count"] == 2
    missing_anomalies = compare_sales_generation_manifests(missing_site_day, previous)
    assert {item["code"] for item in missing_anomalies} >= {
        "site_day_disappeared",
        "rows_imported_regression",
        "receipt_count_regression",
    }
    assert all(
        item["classification"] == SalesAnomalyClassification.INFORMATIONAL.value
        and item["blocking"] is False
        for item in missing_anomalies
    )
    by_code = {item["code"]: item for item in missing_anomalies}
    assert by_code["site_day_disappeared"]["classification"] == (
        SalesAnomalyClassification.INFORMATIONAL.value
    )
    assert by_code["site_day_disappeared"]["blocking"] is False
    assert by_code["rows_imported_regression"]["classification"] == (
        SalesAnomalyClassification.INFORMATIONAL.value
    )
    assert by_code["rows_imported_regression"]["blocking"] is False
    assert manifest_requires_override({"anomalies": missing_anomalies}) is False
    cutoff_anomalies = compare_sales_generation_manifests(regressed_cutoff, previous)
    cutoff = {item["code"]: item for item in cutoff_anomalies}
    assert cutoff["cutoff_regression"]["classification"] == (
        SalesAnomalyClassification.INFORMATIONAL.value
    )
    assert cutoff["cutoff_regression"]["blocking"] is False
    assert manifest_requires_override({"anomalies": cutoff_anomalies}) is False


def test_authoritative_replace_allows_informational_metric_regression() -> None:
    previous = manifest(sales_frame(), cutoff=date(2099, 11, 1))
    incoming_frame = sales_frame()
    incoming_frame.loc[0, "Valoare"] = 1
    incoming = manifest(incoming_frame, cutoff=date(2099, 11, 1))

    anomalies = compare_sales_generation_manifests(incoming, previous)

    assert {item["code"] for item in anomalies} == {"total_value_regression"}
    assert anomalies[0]["classification"] == SalesAnomalyClassification.INFORMATIONAL.value
    assert anomalies[0]["blocking"] is False
    assert manifest_requires_override({"anomalies": anomalies}) is False


def test_structural_manifest_contradiction_is_explicit() -> None:
    frame = sales_frame()

    with pytest.raises(SalesPolicyValidationError) as exc_info:
        manifest(frame, cutoff=date(2099, 12, 1))

    anomaly = exc_info.value.anomalies[0]
    assert anomaly["code"] == "cutoff_month_mismatch"
    assert anomaly["classification"] == SalesAnomalyClassification.STRUCTURAL_CONTRADICTION.value


async def cleanup_generation_data(conn: object) -> None:
    await conn.execute(  # type: ignore[attr-defined]
        "ALTER TABLE sales_generation_promotions DISABLE TRIGGER trg_sales_generation_promotions_immutable"
    )
    try:
        await conn.execute(  # type: ignore[attr-defined]
            "DELETE FROM sales_generation_promotions WHERE import_month = $1",
            TEST_MONTH,
        )
    finally:
        await conn.execute(  # type: ignore[attr-defined]
            "ALTER TABLE sales_generation_promotions ENABLE TRIGGER trg_sales_generation_promotions_immutable"
        )
    await conn.execute(  # type: ignore[attr-defined]
        "DELETE FROM sales_generation_heads WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(  # type: ignore[attr-defined]
        "DELETE FROM sales_transactions WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(  # type: ignore[attr-defined]
        "UPDATE import_snapshots SET previous_snapshot_id = NULL WHERE import_month = $1",
        TEST_MONTH,
    )
    await conn.execute(  # type: ignore[attr-defined]
        "ALTER TABLE sales_import_stage_rows DISABLE TRIGGER trg_sales_stage_mutation"
    )
    try:
        await conn.execute(  # type: ignore[attr-defined]
            "DELETE FROM import_snapshots WHERE import_month = $1",
            TEST_MONTH,
        )
    finally:
        await conn.execute(  # type: ignore[attr-defined]
            "ALTER TABLE sales_import_stage_rows ENABLE TRIGGER trg_sales_stage_mutation"
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_stage_promote_fencing_and_rollback_are_atomic() -> None:
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await cleanup_generation_data(conn)
            first = await import_sales_dataframe(
                conn,
                sales_frame(),
                "first.xlsx",
                source_sha256="a" * 64,
                cutoff_date=date(2099, 11, 1),
                requested_by_sub="test:first",
            )
            assert first.generation_state == "promoted"
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_transactions WHERE import_month = $1",
                TEST_MONTH,
            ) == 1

            second = await import_sales_dataframe(
                conn,
                sales_frame(include_second_row=True),
                "second.xlsx",
                source_sha256="b" * 64,
                cutoff_date=date(2099, 11, 2),
                stage_only=True,
                requested_by_sub="test:second",
            )
            assert second.generation_state == "validated"
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_transactions WHERE import_month = $1",
                TEST_MONTH,
            ) == 1

            assert second.generation_token is not None
            assert second.owner_id is not None
            assert second.manifest_sha256 is not None
            promoter_owner = str(uuid4())
            previous_owner = await claim_validated_sales_generation(
                conn,
                snapshot_id=second.snapshot_id,
                generation_token=second.generation_token,
                expected_manifest_sha256=second.manifest_sha256,
                new_owner_id=promoter_owner,
            )
            assert previous_owner == second.owner_id
            with pytest.raises(SalesGenerationConflictError):
                await claim_validated_sales_generation(
                    conn,
                    snapshot_id=second.snapshot_id,
                    generation_token=second.generation_token,
                    expected_manifest_sha256=second.manifest_sha256,
                    new_owner_id=str(uuid4()),
                )
            with pytest.raises(SalesGenerationConflictError):
                await promote_sales_generation(
                    conn,
                    snapshot_id=second.snapshot_id,
                    generation_token=second.generation_token,
                    owner_id=second.owner_id,
                    expected_manifest_sha256=second.manifest_sha256,
                    requested_by_sub="test:stale",
                )

            rows_imported, revision = await promote_sales_generation(
                conn,
                snapshot_id=second.snapshot_id,
                generation_token=second.generation_token,
                owner_id=promoter_owner,
                expected_manifest_sha256=second.manifest_sha256,
                requested_by_sub="test:promote",
            )
            assert (rows_imported, revision) == (2, 2)
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_transactions WHERE import_month = $1",
                TEST_MONTH,
            ) == 2

            rollback_snapshot_id, rollback_rows, rollback_revision = await rollback_sales_generation(
                conn,
                current_snapshot_id=second.snapshot_id,
                current_generation_token=second.generation_token,
                expected_manifest_sha256=second.manifest_sha256,
                requested_by_sub="test:rollback",
                reason="Rehearsal rollback verificat",
            )
            assert rollback_snapshot_id not in {first.snapshot_id, second.snapshot_id}
            assert (rollback_rows, rollback_revision) == (1, 3)
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_transactions WHERE import_month = $1",
                TEST_MONTH,
            ) == 1
            assert await conn.fetchval(
                "SELECT snapshot_id FROM sales_generation_heads WHERE import_month = $1",
                TEST_MONTH,
            ) == rollback_snapshot_id
            actions = await conn.fetch(
                "SELECT action FROM sales_generation_promotions WHERE import_month = $1 ORDER BY id",
                TEST_MONTH,
            )
            assert [row["action"] for row in actions] == ["promote", "promote", "rollback"]
    finally:
        async with pool.acquire() as conn:
            await cleanup_generation_data(conn)
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_authoritative_replace_promotes_snapshot_regressions_without_override_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    monkeypatch.setattr(importer, "rebuild_reporting_month", AsyncMock())
    monkeypatch.setattr(importer, "rebuild_agent_lifecycle_reporting", AsyncMock())
    monkeypatch.setattr(sales_generation_flow, "rebuild_reporting_month", AsyncMock())
    monkeypatch.setattr(sales_generation_flow, "rebuild_agent_lifecycle_reporting", AsyncMock())
    try:
        async with pool.acquire() as conn:
            await cleanup_generation_data(conn)
            await import_sales_dataframe(
                conn,
                sales_frame(include_second_row=True),
                "authoritative-first.xlsx",
                source_sha256="c" * 64,
                cutoff_date=date(2099, 11, 2),
                requested_by_sub="test:authoritative-first",
            )
            candidate = await import_sales_dataframe(
                conn,
                sales_frame(),
                "authoritative-candidate.xlsx",
                source_sha256="d" * 64,
                cutoff_date=date(2099, 11, 2),
                stage_only=True,
                requested_by_sub="test:authoritative-candidate",
            )

            assert candidate.manifest is not None
            assert manifest_requires_override(candidate.manifest) is False
            assert all(
                anomaly["classification"] == SalesAnomalyClassification.INFORMATIONAL.value
                for anomaly in candidate.manifest["anomalies"]
            )
            rows_imported, revision = await promote_sales_generation(
                conn,
                snapshot_id=candidate.snapshot_id,
                generation_token=str(candidate.generation_token),
                owner_id=str(candidate.owner_id),
                expected_manifest_sha256=str(candidate.manifest_sha256),
                requested_by_sub="test:authoritative-promote",
            )

            assert await conn.fetchval(
                "SELECT snapshot_id FROM sales_generation_heads WHERE import_month = $1",
                TEST_MONTH,
            ) == candidate.snapshot_id
            assert (rows_imported, revision) == (1, 2)
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM sales_transactions WHERE import_month = $1",
                TEST_MONTH,
            ) == 1
    finally:
        async with pool.acquire() as conn:
            await cleanup_generation_data(conn)
        await close_db_pool()
