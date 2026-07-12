from __future__ import annotations

import os
from decimal import Decimal

import pandas as pd
import pytest

from db.connection import close_db_pool, get_pool
from scripts.import_salary_records import (
    SalaryRecord,
    insert_records,
    parse_file,
    validate_records,
)


def test_parse_salary_file_skips_invalid_rows_and_includes_meal_vouchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "Denumire locatie": "PROMENDADA",
                "CNP": 900000001.0,
                "Nume Prenume": "Agent Valid",
                "TOTAL SALARIU": 3000.125,
                "Bonuri masa Mai": 400.126,
            },
            {
                "Denumire locatie": "PROMENDADA",
                "CNP": 123,
                "Nume Prenume": "TOTAL GENERAL",
                "TOTAL SALARIU": 9999,
                "Bonuri masa Mai": 999,
            },
            {
                "Denumire locatie": "Alta locatie",
                "CNP": None,
                "Nume Prenume": "Fara CNP",
                "TOTAL SALARIU": 2500,
                "Bonuri masa Mai": 300,
            },
        ]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *args, **kwargs: frame)

    records = parse_file(
        "salary.xlsx",  # type: ignore[arg-type]
        year=2099,
        month=7,
        company_name="Mobiup",
        store_map={},
    )

    assert records == [
        SalaryRecord(
            year=2099,
            month=7,
            full_name="Agent Valid",
            cnp="900000001",
            total_salary=Decimal("3400.25"),
            company_name="Mobiup",
            site_code="PROM",
            locatie="PROMENDADA",
        )
    ]


def test_validate_salary_records_rejects_duplicate_business_key() -> None:
    record = SalaryRecord(
        year=2099,
        month=7,
        full_name="Agent Duplicat",
        cnp="123",
        total_salary=Decimal("3000"),
        company_name="Mobiup",
        site_code=None,
        locatie="Test",
    )

    with pytest.raises(ValueError, match="duplicate_count=1") as exc_info:
        validate_records([record, record])
    assert record.cnp not in str(exc_info.value)
    assert record.full_name not in str(exc_info.value)


@pytest.mark.asyncio
async def test_insert_salary_records_rejects_empty_batch() -> None:
    with pytest.raises(ValueError, match="Nu exista randuri valide"):
        await insert_records(None, [])  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_salary_import_replaces_only_selected_month_and_companies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "SALARY_PERSON_ID_HMAC_KEY",
        "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz",
    )
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM salary_records WHERE year = 2099 AND month = 7"
            )
            await conn.executemany(
                """
                INSERT INTO salary_records (
                    year, month, full_name, cnp, total_salary,
                    company_name, site_code, locatie
                )
                VALUES ($1, $2, $3, $4, $5, $6, NULL, $7)
                """,
                [
                    (2099, 7, "Mobiup vechi", "101", 1000, "Mobiup", "Test"),
                    (2099, 7, "Mobicell pastrat", "102", 2000, "Mobicell", "Test"),
                ],
            )
            replacement = SalaryRecord(
                year=2099,
                month=7,
                full_name="Mobiup nou",
                cnp="103",
                total_salary=Decimal("3500"),
                company_name="Mobiup",
                site_code=None,
                locatie="Test",
            )
            async with conn.transaction():
                await insert_records(conn, [replacement])
            rows = await conn.fetch(
                """
                SELECT full_name, company_name, total_salary, person_id
                FROM salary_records
                WHERE year = 2099 AND month = 7
                ORDER BY company_name, full_name
                """
            )

        assert [(row["full_name"], row["company_name"], row["total_salary"]) for row in rows] == [
            ("Mobicell pastrat", "Mobicell", Decimal("2000.00")),
            ("Mobiup nou", "Mobiup", Decimal("3500.00")),
        ]
        assert rows[1]["person_id"].startswith("sp1_")
        assert len(rows[1]["person_id"]) == 68
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM salary_records WHERE year = 2099 AND month = 7"
            )
        await close_db_pool()
