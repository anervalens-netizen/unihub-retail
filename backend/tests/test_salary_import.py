from __future__ import annotations

import base64
import json
import os
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
import asyncpg
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from db.connection import close_db_pool, get_pool
from scripts.import_salary_records import (
    SalaryRecord,
    build_dry_run_manifest,
    insert_records,
    parse_file,
    validate_cnp,
    validate_records,
)
import scripts.import_salary_records as salary_import_module
from salary_identity import make_salary_person_id
from salary_import_approval import (
    APPROVAL_ARTIFACT_TYPE,
    APPROVAL_SCHEMA_VERSION,
    KNOWN_GROUPS_TOTAL,
    REQUIRED_COMPANIES,
    SalaryImportApprovalError,
    ValidatedApproval,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_approval_artifact,
)


TEST_PERSON_ID_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"
REVIEWER_KEY_ID = "synthetic-reviewer-key"
REVIEWER_PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(b"\x01" * 32)
TRUSTED_REVIEWER_KEYS = {
    REVIEWER_KEY_ID: base64.b64encode(
        REVIEWER_PRIVATE_KEY.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode("ascii")
}


@pytest.fixture(autouse=True)
def _trusted_salary_reviewer_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SALARY_APPROVAL_REVIEWER_PUBLIC_KEYS_JSON",
        json.dumps(TRUSTED_REVIEWER_KEYS),
    )
CNP_A = "9000000000007"
CNP_B = "9000000000015"
CNP_C = "9000000000023"


def make_record(
    *,
    full_name: str = "Agent Test",
    cnp: str = CNP_A,
    company_name: str = "Mobiup",
    total_salary: str = "3000.00",
    source_file: str = "salary.xlsx",
    source_row: int | None = 2,
    source_sha256: str = "a" * 64,
) -> SalaryRecord:
    return SalaryRecord(
        year=2099,
        month=7,
        full_name=full_name,
        cnp=cnp,
        total_salary=Decimal(total_salary),
        company_name=company_name,
        site_code=None,
        locatie="Test",
        source_file=source_file,
        source_row=source_row,
        source_sha256=source_sha256,
    )


def approved_batch(
    records: list[SalaryRecord], *, applied_by: str
) -> tuple[dict[str, object], ValidatedApproval]:
    companies: list[dict[str, object]] = []
    for company_name in REQUIRED_COMPANIES:
        company_records = [record for record in records if record.company_name == company_name]
        assert company_records
        companies.append(
            {
                "company_name": company_name,
                "source_file": company_records[0].source_file,
                "source_sha256": company_records[0].source_sha256,
                "row_count": len(company_records),
                "control_total": f"{sum((item.total_salary for item in company_records), Decimal('0')):.2f}",
                "mapped_site_rows": sum(1 for item in company_records if item.site_code),
                "unmapped_locations": sorted(
                    {item.locatie for item in company_records if not item.site_code}
                ),
            }
        )
    manifest: dict[str, object] = {
        "manifest_version": 1,
        "year": records[0].year,
        "month": records[0].month,
        "companies": companies,
        "row_count": len(records),
        "control_total": f"{sum((item.total_salary for item in records), Decimal('0')):.2f}",
    }
    manifest_sha256 = canonical_json_sha256(manifest)
    artifact = {
        "artifact_type": APPROVAL_ARTIFACT_TYPE,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "decision": "approved",
        "manifest_sha256": manifest_sha256,
        "year": records[0].year,
        "month": records[0].month,
        "companies": list(REQUIRED_COMPANIES),
        "known_groups_total": KNOWN_GROUPS_TOTAL,
        "resolved_groups_count": KNOWN_GROUPS_TOTAL,
        "unresolved_groups_count": 0,
        "reviewer": "test:independent-reviewer",
        "reviewer_key_id": REVIEWER_KEY_ID,
        "approval_timestamp": "2099-01-01T00:00:00+00:00",
        "approval_reference": "test:approved-batch",
    }
    artifact["signature"] = base64.b64encode(
        REVIEWER_PRIVATE_KEY.sign(canonical_json_bytes(artifact))
    ).decode("ascii")
    approval = validate_approval_artifact(
        artifact,
        manifest=manifest,
        expected_manifest_sha256=manifest_sha256,
        applied_by=applied_by,
        trusted_reviewer_keys=TRUSTED_REVIEWER_KEYS,
    )
    return manifest, approval


def test_validate_cnp_requires_thirteen_digits_and_checksum() -> None:
    assert validate_cnp(CNP_A) == CNP_A
    with pytest.raises(ValueError, match="exact 13 cifre"):
        validate_cnp("123")
    with pytest.raises(ValueError, match="checksum invalid"):
        validate_cnp("9000000000008")


def test_parse_salary_file_rejects_invalid_cnp_and_includes_meal_vouchers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "Denumire locatie": "PROMENDADA",
                "CNP": CNP_A,
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
        ]
    )
    monkeypatch.setattr(salary_import_module, "read_spreadsheet_frame", lambda *args, **kwargs: frame)

    records = parse_file(
        Path("salary.xlsx"),
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
            cnp=CNP_A,
            total_salary=Decimal("3400.25"),
            company_name="Mobiup",
            site_code="PROM",
            locatie="PROMENDADA",
            source_file="salary.xlsx",
            source_row=2,
            source_sha256="",
        )
    ]


def test_parse_salary_file_rejects_blank_cnp_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        [
            {
                "Denumire locatie": "PROMENDADA",
                "CNP": None,
                "Nume Prenume": "Fara CNP",
                "TOTAL SALARIU": 2500,
                "Bonuri masa Mai": 300,
            }
        ]
    )
    monkeypatch.setattr(salary_import_module, "read_spreadsheet_frame", lambda *args, **kwargs: frame)

    with pytest.raises(ValueError, match="exact 13 cifre"):
        parse_file(
            Path("salary.xlsx"),
            year=2099,
            month=7,
            company_name="Mobiup",
            store_map={},
        )


def test_validate_salary_records_allows_distinct_source_components() -> None:
    first = make_record(source_file="salary.xlsx", source_row=2, source_sha256="a" * 64)
    second = replace(first, source_row=3)
    validate_records([first, second])


def test_validate_salary_records_rejects_duplicate_source_row() -> None:
    first = make_record(source_file="salary.xlsx", source_row=2, source_sha256="a" * 64)
    second = replace(first, total_salary=Decimal("3100.00"))
    with pytest.raises(ValueError, match="Duplicate source row"):
        validate_records([first, second])


def test_validate_salary_records_rejects_conflicting_names_without_sensitive_data() -> None:
    first = make_record(
        full_name="Agent Alpha",
        source_file="mobiup.xls",
        source_row=2,
        source_sha256="a" * 64,
    )
    second = make_record(
        full_name="Agent Beta",
        source_file="mobicell.xls",
        source_row=2,
        source_sha256="b" * 64,
    )
    with pytest.raises(ValueError, match="Conflict identitate") as exc_info:
        validate_records([first, second])
    assert CNP_A not in str(exc_info.value)
    assert "Agent Alpha" not in str(exc_info.value)
    assert "Agent Beta" not in str(exc_info.value)


def test_dry_run_manifest_contains_both_sources_control_totals_and_hashes() -> None:
    records = [
        make_record(total_salary="3400.25", source_file="mobiup.xls", source_row=2),
        make_record(
            cnp=CNP_B,
            company_name="Mobicell",
            total_salary="2200.00",
            source_file="mobicell.xls",
            source_row=2,
        ),
    ]
    manifest = build_dry_run_manifest(
        records,
        year=2099,
        month=7,
        source_files=[("Mobiup", Path("mobiup.xls")), ("Mobicell", Path("mobicell.xls"))],
        source_hashes={"Mobiup": "a" * 64, "Mobicell": "b" * 64},
    )

    assert [company["company_name"] for company in manifest["companies"]] == ["Mobiup", "Mobicell"]
    assert [company["control_total"] for company in manifest["companies"]] == ["3400.25", "2200.00"]
    assert [company["source_sha256"] for company in manifest["companies"]] == ["a" * 64, "b" * 64]
    assert manifest["row_count"] == 2
    assert manifest["control_total"] == "5600.25"
    assert "CNP" not in json.dumps(manifest)


@pytest.mark.asyncio
async def test_insert_salary_records_rejects_empty_batch() -> None:
    with pytest.raises(ValueError, match="Nu exista randuri valide"):
        await insert_records(None, [])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_salary_import_rejects_directly_constructed_approval() -> None:
    record = make_record()
    counterpart = make_record(
        company_name="Mobicell",
        source_file="mobicell.xlsx",
        source_sha256="b" * 64,
    )
    records = [record, counterpart]
    manifest, approval = approved_batch(records, applied_by="test:forged")
    forged = replace(approval, _proof=None)

    with pytest.raises(SalaryImportApprovalError, match="cryptographic signature validation"):
        await insert_records(
            MagicMock(),
            records,
            manifest=manifest,
            applied_by="test:forged",
            approval=forged,
        )

    tampered = replace(
        approval,
        signed_artifact={**approval.signed_artifact, "decision": "rejected"},
    )
    with pytest.raises(SalaryImportApprovalError, match="signature is invalid"):
        await insert_records(
            MagicMock(),
            records,
            manifest=manifest,
            applied_by="test:forged",
            approval=tampered,
        )


@pytest.mark.asyncio
async def test_insert_salary_records_validates_before_db_writes() -> None:
    conn = AsyncMock()
    with pytest.raises(ValueError, match="exact 13 cifre"):
        await insert_records(conn, [make_record(cnp="123")])
    conn.transaction.assert_not_called()
    conn.executemany.assert_not_called()


class FaultAfterIdentityInsert:
    def __init__(self, conn: object) -> None:
        self.conn = conn
        self.calls = 0

    def transaction(self) -> object:
        return self.conn.transaction()  # type: ignore[attr-defined]

    async def fetch(self, query: str, *args: object) -> object:
        return await self.conn.fetch(query, *args)  # type: ignore[attr-defined]

    async def executemany(self, query: str, args: object) -> None:
        self.calls += 1
        await self.conn.executemany(query, args)  # type: ignore[attr-defined]
        if self.calls == 1:
            raise RuntimeError("injected after identity insert")

    async def execute(self, query: str, *args: object) -> object:
        return await self.conn.execute(query, *args)  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_salary_import_rolls_back_identity_after_post_insert_fault(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", TEST_PERSON_ID_KEY)
    pool = await get_pool()
    try:
        record = make_record(cnp=CNP_C)
        counterpart = make_record(
            cnp=CNP_A,
            full_name="Agent Counterpart",
            company_name="Mobicell",
            source_file="mobicell.xlsx",
            source_sha256="b" * 64,
        )
        records = [record, counterpart]
        manifest, approval = approved_batch(records, applied_by="test:salary-import")
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 7")
            await conn.execute(
                "DELETE FROM salary_private.people WHERE cnp = $1",
                CNP_C,
            )
            with pytest.raises(RuntimeError, match="injected after identity insert"):
                await insert_records(
                    FaultAfterIdentityInsert(conn),
                    records,
                    manifest=manifest,
                    approval=approval,
                )
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_private.people WHERE cnp = $1",
                CNP_C,
            ) == 0
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_records WHERE year = 2099 AND month = 7 AND cnp = $1",
                CNP_C,
            ) == 0
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 7")
            await conn.execute("DELETE FROM salary_private.people WHERE cnp = $1", CNP_C)
        await close_db_pool()


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
        TEST_PERSON_ID_KEY,
    )
    old_mobiup_id = make_salary_person_id(CNP_A, "Mobiup vechi", TEST_PERSON_ID_KEY)
    kept_mobicell_id = make_salary_person_id(CNP_B, "Mobicell pastrat", TEST_PERSON_ID_KEY)
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM salary_records WHERE year = 2099 AND month = 7"
            )
            await conn.executemany(
                """
                INSERT INTO salary_private.people (
                    person_id, cnp, normalized_name, identity_source
                ) VALUES ($1, $2, $3, 'cnp')
                ON CONFLICT (person_id) DO NOTHING
                """,
                [
                    (old_mobiup_id, CNP_A, "mobiup vechi"),
                    (kept_mobicell_id, CNP_B, "mobicell pastrat"),
                ],
            )
            await conn.executemany(
                """
                INSERT INTO salary_records (
                    year, month, full_name, cnp, total_salary,
                    company_name, site_code, locatie, person_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, NULL, $7, $8)
                """,
                [
                    (2099, 7, "Mobiup vechi", CNP_A, 1000, "Mobiup", "Test", old_mobiup_id),
                    (2099, 7, "Mobicell pastrat", CNP_B, 2000, "Mobicell", "Test", kept_mobicell_id),
                ],
            )
            replacement = SalaryRecord(
                year=2099,
                month=7,
                full_name="Mobiup nou",
                cnp=CNP_C,
                total_salary=Decimal("3500"),
                company_name="Mobiup",
                site_code=None,
                locatie="Test",
                source_file="mobiup.xlsx",
                source_row=2,
                source_sha256="c" * 64,
            )
            replacement_mobicell = SalaryRecord(
                year=2099,
                month=7,
                full_name="Mobicell pastrat",
                cnp=CNP_B,
                total_salary=Decimal("2000"),
                company_name="Mobicell",
                site_code=None,
                locatie="Test",
                source_file="mobicell.xlsx",
                source_row=2,
                source_sha256="b" * 64,
            )
            replacements = [replacement, replacement_mobicell]
            manifest, approval = approved_batch(
                replacements, applied_by="test:salary-import"
            )
            async with conn.transaction():
                await insert_records(
                    conn,
                    replacements,
                    manifest=manifest,
                    approval=approval,
                )
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
            await conn.execute(
                "DELETE FROM salary_private.people WHERE person_id = ANY($1::text[])",
                [old_mobiup_id, kept_mobicell_id],
            )
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_salary_components_persist_by_source_row_and_aggregate_by_person(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", TEST_PERSON_ID_KEY)
    person_id = make_salary_person_id(CNP_A, "Agent Test", TEST_PERSON_ID_KEY)
    first = replace(make_record(cnp=CNP_A), month=8, source_row=2)
    second = replace(first, source_row=3, total_salary=Decimal("1250.00"))
    counterpart = replace(
        make_record(
            cnp=CNP_B,
            full_name="Agent Counterpart",
            company_name="Mobicell",
            source_file="mobicell.xlsx",
            source_sha256="b" * 64,
        ),
        month=8,
    )
    records = [first, second, counterpart]
    manifest, approval = approved_batch(records, applied_by="test:components")
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 8")
            await conn.execute("DELETE FROM salary_private.people WHERE person_id = $1", person_id)
            await insert_records(
                conn,
                records,
                manifest=manifest,
                approval=approval,
                applied_by="test:components",
            )
            result = await conn.fetchrow(
                """
                SELECT COUNT(*)::integer AS component_count,
                       SUM(total_salary)::numeric AS total_salary,
                       COUNT(DISTINCT person_id)::integer AS person_count
                FROM salary_records
                WHERE year = 2099 AND month = 8 AND company_name = 'Mobiup'
                  AND person_id = $1
                """,
                person_id,
            )
            assert result is not None
            assert (result["component_count"], result["total_salary"], result["person_count"]) == (
                2,
                Decimal("4250.00"),
                1,
            )
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 8")
            await conn.execute("DELETE FROM salary_import_batches WHERE year = 2099 AND month = 8")
            await conn.execute("DELETE FROM salary_private.people WHERE person_id = $1", person_id)
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_signed_salary_approval_is_consumed_once_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", TEST_PERSON_ID_KEY)
    records = [
        replace(make_record(), month=10),
        replace(
            make_record(
                cnp=CNP_B,
                full_name="Agent Counterpart",
                company_name="Mobicell",
                source_file="mobicell.xlsx",
                source_sha256="b" * 64,
            ),
            month=10,
        ),
    ]
    manifest, approval = approved_batch(records, applied_by="test:one-time-approval")
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 10")
            await conn.execute("DELETE FROM salary_import_batches WHERE year = 2099 AND month = 10")
            await insert_records(
                conn,
                records,
                manifest=manifest,
                approval=approval,
                applied_by="test:one-time-approval",
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await insert_records(
                    conn,
                    records,
                    manifest=manifest,
                    approval=approval,
                    applied_by="test:one-time-approval",
                )
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_import_batches WHERE year = 2099 AND month = 10"
            ) == 1
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_records WHERE year = 2099 AND month = 10"
            ) == 2
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 10")
            await conn.execute("DELETE FROM salary_import_batches WHERE year = 2099 AND month = 10")
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_salary_existing_identity_name_conflict_has_zero_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALARY_PERSON_ID_HMAC_KEY", TEST_PERSON_ID_KEY)
    person_id = make_salary_person_id(CNP_B, "Alt Nume", TEST_PERSON_ID_KEY)
    record = replace(make_record(cnp=CNP_B), month=9, source_sha256="b" * 64)
    counterpart = replace(
        make_record(
            cnp=CNP_A,
            full_name="Agent Counterpart",
            company_name="Mobicell",
            source_file="mobicell.xlsx",
            source_sha256="a" * 64,
        ),
        month=9,
    )
    records = [record, counterpart]
    manifest, approval = approved_batch(records, applied_by="test:conflict")
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 9")
            await conn.execute("DELETE FROM salary_private.people WHERE person_id = $1", person_id)
            await conn.execute(
                """
                INSERT INTO salary_private.people (person_id, cnp, normalized_name, identity_source)
                VALUES ($1, $2, 'alt nume', 'cnp')
                """,
                person_id,
                CNP_B,
            )
            with pytest.raises(ValueError, match="zero scrieri"):
                await insert_records(
                    conn,
                    records,
                    manifest=manifest,
                    approval=approval,
                    applied_by="test:conflict",
                )
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_records WHERE year = 2099 AND month = 9"
            ) == 0
            assert await conn.fetchval(
                "SELECT COUNT(*) FROM salary_import_batches WHERE year = 2099 AND month = 9"
            ) == 0
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM salary_records WHERE year = 2099 AND month = 9")
            await conn.execute("DELETE FROM salary_import_batches WHERE year = 2099 AND month = 9")
            await conn.execute("DELETE FROM salary_private.people WHERE person_id = $1", person_id)
        await close_db_pool()
