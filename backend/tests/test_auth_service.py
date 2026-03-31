from __future__ import annotations

from bootstrap import get_default_core_credentials
from services.auth_service import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password_roundtrip() -> None:
    password = "9999"
    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_create_and_decode_access_token() -> None:
    token = create_access_token(user_id=42, username="admin", role="admin")
    payload = decode_access_token(token)

    assert payload["user_id"] == 42
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_default_core_credentials_read_from_env_defaults() -> None:
    credentials = get_default_core_credentials()

    assert credentials["admin"][0] == "admin"
    assert credentials["admin"][1] == "9999"
    assert credentials["management"][0] == "management"
    assert credentials["management"][1] == "9999"
