from __future__ import annotations

import os

import pytest

from db.connection import get_pool
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


@pytest.mark.parametrize("invalid", ["a" * 20, "a" * 20 + " " + "b" * 30, "a" * 20 + "\t" + "b" * 30, "a" * 20 + "\r" + "b" * 30, "a" * 20 + "\n" + "b" * 30, "a" * 20 + "\u00a0" + "b" * 30, "a" * 20 + "\u200b" + "b" * 30])
def test_key_rejects_all_whitespace_and_nonprintable_characters(invalid: str) -> None:
    with pytest.raises(ValueError, match="SALARY_PERSON_ID_HMAC_KEY"):
        validate_salary_person_id_key(invalid)


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
@pytest.mark.skipif(os.getenv("UNIHUB_TEST_DATABASE") != "1", reason="requires isolated PostgreSQL")
async def test_python_postgresql_equivalence_uses_actual_sql_helpers() -> None:
    canonical_expr = canonical_salary_identity_sql("sr")
    person_expr = salary_person_id_sql("sr", "$1")
    cases = [
        ("synthetic-private-id-a", "Ana Popescu"),
        (None, " Ștefan Ionescu "),
        (" synthetic-private-id-b ", "IGNORED"),
    ]
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH sample(cnp, full_name) AS (VALUES ($2::text, $3::text), ($4::text, $5::text), ($6::text, $7::text))
            SELECT {canonical_expr} AS canonical, {person_expr} AS person_id
            FROM sample sr
            ORDER BY canonical
            """,
            TEST_KEY,
            *[value for case in cases for value in case],
        )
    expected = sorted((canonical_salary_identity(cnp, name), make_salary_person_id(cnp, name, TEST_KEY)) for cnp, name in cases)
    assert [(row["canonical"], row["person_id"]) for row in rows] == expected
