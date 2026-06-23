from __future__ import annotations

import pytest

from db.connection import validate_test_database_url


def test_database_safety_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UNIHUB_TEST_DATABASE", raising=False)

    with pytest.raises(RuntimeError, match="UNIHUB_TEST_DATABASE=1"):
        validate_test_database_url(
            "postgresql://user:password@127.0.0.1:55432/unihub_test"
        )


@pytest.mark.parametrize(
    "database_url,error",
    [
        (
            "postgresql://user:password@127.0.0.1:5432/unihub_test",
            "production Retail port",
        ),
        (
            "postgresql://user:password@127.0.0.1:55432/unihub",
            "database name",
        ),
        (
            "postgresql://user:password@db.internal:55432/unihub_test",
            "loopback host",
        ),
        (
            "mysql://user:password@127.0.0.1:55432/unihub_test",
            "PostgreSQL",
        ),
    ],
)
def test_database_safety_rejects_unsafe_targets(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
    error: str,
) -> None:
    monkeypatch.setenv("UNIHUB_TEST_DATABASE", "1")

    with pytest.raises(RuntimeError, match=error):
        validate_test_database_url(database_url)


def test_database_safety_accepts_isolated_local_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UNIHUB_TEST_DATABASE", "1")

    validate_test_database_url(
        "postgresql://user:password@127.0.0.1:55432/unihub_test"
    )
