from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from typing import Any
from uuid import uuid4

import asyncpg
import pandas as pd

from services.sales_import_parsing import is_month_final


class ImportAlreadyRunningError(RuntimeError):
    pass


async def record_coverage_report(
    conn: asyncpg.Connection,
    snapshot_id: int,
    coverage_report: dict[str, Any],
) -> None:
    await conn.execute(
        """
        UPDATE import_snapshots
        SET coverage_report = $2::jsonb,
            heartbeat_at = now()
        WHERE id = $1 AND status = 'processing'
        """,
        snapshot_id,
        json.dumps(coverage_report, ensure_ascii=False),
    )


async def reserve_snapshot(
    conn: asyncpg.Connection,
    import_month: str,
    filename: str,
    rows_in_file: int,
    *,
    source_sha256: str | None = None,
    cutoff_date: date | None = None,
    generation_token: str | None = None,
    owner_id: str | None = None,
    source_artifact_required: bool = False,
    source_artifact_path: str | None = None,
    source_artifact_bytes: int | None = None,
    lease_seconds: int = 2 * 60 * 60,
) -> int:
    generation_token = generation_token or str(uuid4())
    owner_id = owner_id or str(uuid4())
    if lease_seconds < 60:
        raise ValueError("Sales generation lease must be at least 60 seconds")
    if source_artifact_required and (
        not source_artifact_path
        or source_sha256 is None
        or source_artifact_bytes is None
        or source_artifact_bytes < 0
    ):
        raise ValueError("Required sales artifact metadata is incomplete")
    async with conn.transaction():
        await conn.execute(
            """
            UPDATE import_snapshots
            SET status = 'failed',
                rows_imported = 0,
                error_message = 'Import processing abandonat si inchis automat',
                heartbeat_at = now(),
                finished_at = now()
            WHERE import_month = $1
              AND status = 'processing'
              AND COALESCE(manifest->>'generation_state', '') NOT IN ('validated', 'promoting')
              AND (
                    (lease_until IS NOT NULL AND lease_until <= now())
                    OR (lease_until IS NULL AND COALESCE(heartbeat_at, created_at) < now() - interval '1 hour')
              )
            """,
            import_month,
        )
        head = await conn.fetchrow(
            "SELECT snapshot_id, revision FROM sales_generation_heads WHERE import_month = $1",
            import_month,
        )
        previous_snapshot_id = int(head["snapshot_id"]) if head is not None else None
        expected_head_revision = int(head["revision"]) if head is not None else 0
        row = await conn.fetchrow(
            """
            INSERT INTO import_snapshots (
                import_month, filename, rows_in_file, status,
                is_month_final, heartbeat_at, source_sha256, cutoff_date,
                generation_token, owner_id, lease_until,
                expected_head_revision, previous_snapshot_id
                , source_artifact_required, source_spool_path,
                source_artifact_state, source_artifact_sha256, source_artifact_bytes
            )
            VALUES (
                $1, $2, $3, 'processing', $4, now(), $5, $6,
                $7::uuid, $8::uuid, now() + make_interval(secs => $9),
                $10, $11, $12, $13,
                CASE WHEN $12 THEN 'artifact_retaining' ELSE NULL END,
                CASE WHEN $12 THEN $5 ELSE NULL END, $14
            )
            ON CONFLICT (import_month)
                WHERE status = 'processing'
            DO NOTHING
            RETURNING id
            """,
            import_month,
            filename,
            rows_in_file,
            is_month_final(import_month),
            source_sha256,
            cutoff_date,
            generation_token,
            owner_id,
            lease_seconds,
            expected_head_revision,
            previous_snapshot_id,
            source_artifact_required,
            source_artifact_path,
            source_artifact_bytes,
        )
    if row is None:
        raise ImportAlreadyRunningError(
            f"Exista deja un import in curs pentru luna {import_month}"
        )
    return int(row["id"])


def _to_decimal(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


async def insert_transactions(conn: asyncpg.Connection, df: pd.DataFrame, snapshot_id: int, import_month: str) -> int:
    row_count = len(df)

    def records():
        # asyncpg consumes the iterable synchronously while encoding COPY data.
        # Keeping this lazy avoids duplicating the entire DataFrame in memory.
        for row in df.itertuples(index=False):
            yield (
                import_month,
                row.Data,
                row.SiteCode,
                row.Nr,
                row.ItemCode,
                row.ItemName,
                row.Brand,
                row.Categorie,
                row.SubCategorie,
                int(row.Cantitate),
                _to_decimal(row.Pret),
                _to_decimal(row.Valoare),
                row.Agent,
                bool(row.is_cartela),
                bool(row.is_return),
                snapshot_id,
            )

    await conn.execute(
        """
        CREATE TEMP TABLE tmp_sales_transactions (
            import_month TEXT NOT NULL,
            sale_date DATE NOT NULL,
            site_code TEXT NOT NULL,
            bon_nr TEXT NOT NULL,
            item_code TEXT NOT NULL,
            item_name TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            subcategory TEXT,
            quantity INTEGER NOT NULL,
            unit_price NUMERIC(10, 2) NOT NULL,
            total_value NUMERIC(10, 2) NOT NULL,
            agent TEXT NOT NULL,
            is_cartela BOOLEAN NOT NULL,
            is_return BOOLEAN NOT NULL,
            snapshot_id INTEGER NOT NULL
        ) ON COMMIT DROP
        """
    )
    await conn.copy_records_to_table(
        "tmp_sales_transactions",
        records=records(),
        columns=[
            "import_month",
            "sale_date",
            "site_code",
            "bon_nr",
            "item_code",
            "item_name",
            "brand",
            "category",
            "subcategory",
            "quantity",
            "unit_price",
            "total_value",
            "agent",
            "is_cartela",
            "is_return",
            "snapshot_id",
        ],
    )
    await conn.execute(
        """
        INSERT INTO sales_transactions (
            import_month,
            sale_date,
            site_code,
            bon_nr,
            item_code,
            item_name,
            brand,
            category,
            subcategory,
            quantity,
            unit_price,
            total_value,
            agent,
            is_cartela,
            is_return,
            snapshot_id
        )
        SELECT
            import_month,
            sale_date,
            site_code,
            bon_nr,
            item_code,
            item_name,
            brand,
            category,
            subcategory,
            quantity,
            unit_price,
            total_value,
            agent,
            is_cartela,
            is_return,
            snapshot_id
        FROM tmp_sales_transactions
        """,
    )
    return row_count
