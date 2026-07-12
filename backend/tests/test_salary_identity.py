from __future__ import annotations

import os

import asyncpg
import pytest

from salary_identity import (
    PERSON_ID_PREFIX,
    canonical_salary_identity,
    canonical_salary_identity_sql,
    make_salary_person_id,
    salary_person_id_sql,
    validate_salary_person_id,
    validate_salary_person_id_key,
)

TEST_KEY = "synthetic-hmac-key-for-tests-abcdefghijklmnopqrstuvwxyz"


def test_key_validation_and_person_id_format() -> None:
    assert validate_salary_person_id_key(TEST_KEY) == TEST_KEY
    person_id = make_salary_person_id("synthetic-private-id-a", "Ana Popescu", TEST_KEY)
    assert person_id.startswith(PERSON_ID_PREFIX)
    assert len(person_id) == len(PERSON_ID_PREFIX) + 64
    assert validate_salary_person_id(person_id) == person_id


def test_identity_is_deterministic_and_normalized() -> None:
    assert canonical_salary_identity("  synthetic-private-id-a ", "Ignored") == "cnp:synthetic-private-id-a"
    assert canonical_salary_identity(None, "  Ștefan Ionescu ") == "name:ștefan ionescu"
    assert make_salary_person_id(" synthetic-private-id-a ", "Ana", TEST_KEY) == make_salary_person_id(
        "synthetic-private-id-a", "Other", TEST_KEY
    )
    assert make_salary_person_id("synthetic-private-id-a", "Ana", TEST_KEY) != make_salary_person_id(
        "synthetic-private-id-b", "Ana", TEST_KEY
    )


def test_sql_helpers_validate_fragments() -> None:
    expression = canonical_salary_identity_sql("sr")
    assert "sr.cnp" in expression
    person_expression = salary_person_id_sql("sr", "$2")
    assert "hmac" in person_expression
    with pytest.raises(ValueError):
        canonical_salary_identity_sql("sr; DROP TABLE salary_records")
    with pytest.raises(ValueError):
        salary_person_id_sql("sr", "'secret'")


@pytest.mark.asyncio
async def test_python_postgresql_equivalence_when_explicit_test_db_is_configured() -> None:
    database_url = os.getenv("H01_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("H01_TEST_DATABASE_URL is not configured")
    conn = await asyncpg.connect(database_url)
    try:
        for cnp, full_name in (
            ("synthetic-private-id-a", "Ana Popescu"),
            (None, " Ștefan Ionescu "),
            (" synthetic-private-id-b ", "IGNORED"),
        ):
            expected = make_salary_person_id(cnp, full_name, TEST_KEY)
            actual = await conn.fetchval(
                "SELECT 'sp1_' || encode(hmac(($1)::text, $2::text, 'sha256'), 'hex')",
                canonical_salary_identity(cnp, full_name),
                TEST_KEY,
            )
            assert actual == expected
    finally:
        await conn.close()
