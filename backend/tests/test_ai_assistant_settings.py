from __future__ import annotations

from pathlib import Path

import pytest

from ai_assistant.settings import load_ai_assistant_settings, resolve_storage_key
from request_body_limits import RequestBodyLimits


def _base_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UNIHUB_ENV", "development")
    monkeypatch.setenv("AI_ASSISTANT_STORAGE_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("AI_ASSISTANT_SNAPSHOT_ROOT", str(tmp_path / "snapshots"))


def test_ai_settings_keep_runtime_loopback_and_model_fixed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_ASSISTANT_RUNTIME_URL", "http://127.0.0.1:9911")
    settings = load_ai_assistant_settings()
    assert settings.model == "gpt-5.6-luna"
    assert settings.runtime_url == "http://127.0.0.1:9911"
    assert settings.storage_root.is_dir()
    assert settings.snapshot_root.is_dir()
    assert settings.setup_timeout_seconds == 90
    assert settings.max_concurrent_runs_per_owner == 2
    assert settings.readonly_dsn == ""


@pytest.mark.parametrize(
    "runtime_url",
    [
        "https://ai.example.invalid",
        "http://127.0.0.1:9911@evil.example",
        "http://localhost:9911/path",
        "http://localhost:9911?next=http://evil.example",
        "http://0.0.0.0:9911",
    ],
)
def test_ai_runtime_url_rejects_non_loopback_or_authority_injection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    runtime_url: str,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("AI_ASSISTANT_RUNTIME_URL", runtime_url)
    with pytest.raises(RuntimeError):
        load_ai_assistant_settings()


def test_ai_runtime_requires_sandbox_reachable_readonly_dsn(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _base_env(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setenv(
        "AI_ASSISTANT_READONLY_DSN",
        "postgresql://unihub_ai_readonly:test@127.0.0.1:5432/unihub",
    )
    with pytest.raises(RuntimeError, match="Docker sandbox"):
        load_ai_assistant_settings(runtime=True)

    monkeypatch.setenv(
        "AI_ASSISTANT_READONLY_DSN",
        "postgresql://unihub_ai_readonly:test@db.internal:5432/unihub",
    )
    settings = load_ai_assistant_settings(runtime=True)
    assert settings.model == "gpt-5.6-luna"
    # The sandbox credential is retained for the startup authority preflight but
    # must never surface through the settings representation.
    assert settings.readonly_dsn.endswith("@db.internal:5432/unihub")
    assert "unihub_ai_readonly" not in repr(settings)


def test_ai_storage_key_cannot_escape_root(tmp_path: Path) -> None:
    root = (tmp_path / "store").resolve()
    root.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        resolve_storage_key(root, "../secret.txt")
    assert resolve_storage_key(root, "input/conversation/file.csv") == root / "input/conversation/file.csv"


def test_ai_routes_receive_their_own_multipart_budget() -> None:
    limits = RequestBodyLimits(
        json_bytes=8,
        sales_multipart_bytes=16,
        promo_multipart_bytes=14,
        erp_multipart_bytes=12,
        ai_multipart_bytes=64,
    )
    multipart = "multipart/form-data; boundary=x"
    assert limits.for_request("/api/ai/conversations/abc/turn", multipart) == 64
    assert limits.for_request("/api/ai/conversations/abc/steer", multipart) == 64
    assert limits.for_request("/api/import/sales", multipart) == 16
