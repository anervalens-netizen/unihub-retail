from __future__ import annotations

from collections.abc import Callable
from typing import Any

import asyncpg


async def persist_salary_records(
    conn: asyncpg.Connection,
    *,
    records: list[Any],
    identified_records: list[tuple[Any, str]],
    batch_id: str,
    manifest_json: str,
    envelope_sha256: str,
    applied_by: str,
    safe_envelope: dict[str, Any],
    normalize_name: Callable[[str], str],
) -> None:
    async with conn.transaction():
        existing_people = await conn.fetch(
            """
            SELECT person_id, normalized_name
            FROM salary_private.people
            WHERE person_id = ANY($1::text[])
            """,
            [person_id for _, person_id in identified_records],
        )
        existing_names = {
            str(row["person_id"]): normalize_name(row["normalized_name"])
            for row in existing_people
        }
        if any(
            person_id in existing_names
            and existing_names[person_id] != normalize_name(record.full_name)
            for record, person_id in identified_records
        ):
            raise ValueError(
                "Conflict identitate cu registrul existent; zero scrieri"
            )
        await conn.execute(
            """
            INSERT INTO salary_import_batches (
                batch_id, year, month, status, manifest, manifest_sha256,
                applied_by, approval_artifact_sha256, reviewer_key_id
            ) VALUES (
                $1::uuid, $2, $3, 'applied', $4::jsonb, $5, $6, $7, $8
            )
            """,
            batch_id,
            records[0].year,
            records[0].month,
            manifest_json,
            envelope_sha256,
            applied_by.strip(),
            safe_envelope["approval_artifact_sha256"],
            safe_envelope["approval_metadata"]["reviewer_key_id"],
        )
        await conn.executemany(
            """
            INSERT INTO salary_private.people (
                person_id, cnp, normalized_name, identity_source
            ) VALUES ($1, $2, LOWER(BTRIM($3)), 'cnp')
            ON CONFLICT (person_id) DO NOTHING
            """,
            [
                (person_id, record.cnp, record.full_name)
                for record, person_id in identified_records
            ],
        )
        await conn.execute(
            """
            DELETE FROM salary_records
            WHERE year = $1
              AND month = $2
              AND company_name = ANY($3::text[])
            """,
            records[0].year,
            records[0].month,
            sorted({record.company_name for record in records}),
        )
        await conn.executemany(
            """
            INSERT INTO salary_records (
                year, month, full_name, cnp, total_salary, company_name,
                site_code, locatie, person_id, import_batch_id,
                source_file, source_sheet, source_row, source_sha256
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9, $10::uuid, $11, $12, $13, $14
            )
            """,
            [
                (
                    record.year,
                    record.month,
                    record.full_name,
                    record.cnp,
                    record.total_salary,
                    record.company_name,
                    record.site_code,
                    record.locatie,
                    person_id,
                    batch_id,
                    record.source_file,
                    record.source_sheet,
                    record.source_row,
                    record.source_sha256,
                )
                for record, person_id in identified_records
            ],
        )

