"""Opaque, versioned identifiers for the public salary identity boundary."""
from __future__ import annotations

import hashlib
import hmac
import os
import re

SALARY_PERSON_ID_HMAC_KEY_ENV = "SALARY_PERSON_ID_HMAC_KEY"
PERSON_ID_PREFIX = "sp1_"
_MIN_KEY_LENGTH = 43
_MAX_KEY_LENGTH = 256
_ALIAS_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_IDENTITY_REF_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_PLACEHOLDER_RE = re.compile(r"^\$[1-9][0-9]*$")
_PERSON_ID_RE = re.compile(r"^sp1_[0-9a-f]{64}$")


def validate_salary_person_id_key(raw: str | None) -> str:
    if raw is None or not raw:
        raise ValueError(f"{SALARY_PERSON_ID_HMAC_KEY_ENV} is missing")
    if not isinstance(raw, str) or not (_MIN_KEY_LENGTH <= len(raw) <= _MAX_KEY_LENGTH):
        raise ValueError(f"{SALARY_PERSON_ID_HMAC_KEY_ENV} has invalid length")
    if any(char.isspace() or not char.isprintable() for char in raw):
        raise ValueError(f"{SALARY_PERSON_ID_HMAC_KEY_ENV} contains invalid characters")
    return raw


def get_salary_person_id_key() -> str:
    return validate_salary_person_id_key(os.getenv(SALARY_PERSON_ID_HMAC_KEY_ENV))


def canonical_salary_identity(cnp: str | None, full_name: str | None) -> str:
    private_id = (cnp or "").strip()
    if private_id:
        return f"cnp:{private_id}"
    return f"name:{(full_name or '').strip().lower()}"


def make_salary_person_id(cnp: str | None, full_name: str | None, key: str | None = None) -> str:
    secret = validate_salary_person_id_key(key) if key is not None else get_salary_person_id_key()
    digest = hmac.new(
        secret.encode("utf-8"),
        canonical_salary_identity(cnp, full_name).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return PERSON_ID_PREFIX + digest


def validate_salary_person_id(value: str) -> str:
    if not isinstance(value, str) or not _PERSON_ID_RE.fullmatch(value):
        raise ValueError("invalid salary person_id")
    if not hmac.compare_digest(value[: len(PERSON_ID_PREFIX)], PERSON_ID_PREFIX):
        raise ValueError("invalid salary person_id")
    return value


def canonical_salary_identity_sql(alias: str) -> str:
    if not _ALIAS_RE.fullmatch(alias):
        raise ValueError("invalid SQL alias")
    return (
        f"CASE WHEN NULLIF(BTRIM({alias}.cnp), '') IS NOT NULL "
        f"THEN 'cnp:' || BTRIM({alias}.cnp) "
        f"ELSE 'name:' || LOWER(BTRIM(COALESCE({alias}.full_name, ''))) END"
    )


def salary_person_id_sql(alias_or_identity_ref: str, key_placeholder: str) -> str:
    if not _IDENTITY_REF_RE.fullmatch(alias_or_identity_ref):
        raise ValueError("invalid SQL identity reference")
    if not _PLACEHOLDER_RE.fullmatch(key_placeholder):
        raise ValueError("invalid SQL key placeholder")
    identity = (
        canonical_salary_identity_sql(alias_or_identity_ref)
        if _ALIAS_RE.fullmatch(alias_or_identity_ref)
        else alias_or_identity_ref
    )
    return f"'sp1_' || encode(hmac(({identity})::text, {key_placeholder}::text, 'sha256'), 'hex')"
