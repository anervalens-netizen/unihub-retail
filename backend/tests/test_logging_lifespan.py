from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_oidc_init_is_atomic_and_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    import oidc_verifier

    class Client:
        def __init__(self, **_kwargs): self.closed = 0
        async def aclose(self): self.closed += 1

    client = Client()
    monkeypatch.setattr(oidc_verifier, "_client", None)
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", lambda: object())
    monkeypatch.setattr(oidc_verifier.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(oidc_verifier, "OIDCVerifier", lambda *_args: (_ for _ in ()).throw(RuntimeError("construction")))
    with pytest.raises(RuntimeError):
        await oidc_verifier.init_oidc_runtime()
    assert client.closed == 1 and oidc_verifier._client is None and oidc_verifier._verifier is None
    await oidc_verifier.close_oidc_runtime()
    await oidc_verifier.close_oidc_runtime()


@pytest.mark.asyncio
async def test_oidc_runtime_prewarms_singleton_and_closes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import oidc_verifier

    class Client:
        def __init__(self, **_kwargs):
            self.closed = 0
            created.append(self)
        async def aclose(self):
            self.closed += 1

    created: list[Client] = []

    settings = object()
    prewarm = AsyncMock()
    verifier = type("Verifier", (), {"ensure_ready": prewarm})()
    monkeypatch.setattr(oidc_verifier, "_client", None)
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", lambda: settings)
    monkeypatch.setattr(oidc_verifier.httpx, "AsyncClient", Client)
    monkeypatch.setattr(oidc_verifier, "OIDCVerifier", lambda *_args: verifier)
    await oidc_verifier.init_oidc_runtime()
    await oidc_verifier.init_oidc_runtime()
    assert len(created) == 1 and oidc_verifier._client is created[0]
    assert oidc_verifier.get_oidc_verifier() is verifier
    prewarm.assert_awaited_once_with()
    await oidc_verifier.close_oidc_runtime()
    await oidc_verifier.close_oidc_runtime()
    assert created[0].closed == 1


@pytest.mark.asyncio
async def test_oidc_runtime_disabled_and_absent_verifier_are_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    import oidc_verifier
    monkeypatch.setattr(oidc_verifier, "_client", None)
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", lambda: None)
    await oidc_verifier.init_oidc_runtime()
    assert oidc_verifier._client is None
    with pytest.raises(Exception) as exc:
        oidc_verifier.get_oidc_verifier()
    assert getattr(exc.value, "status_code", None) == 503


@pytest.mark.asyncio
async def test_rate_limit_runtime_is_atomic_lazy_and_close_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    import rate_limits

    events: list[str] = []
    class Client:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            events.append("create")
            return cls()
        async def ping(self):
            events.append("ping")
        async def aclose(self):
            events.append("close")

    settings = type("Settings", (), {"valkey_url": "redis://test"})()
    monkeypatch.setattr(rate_limits, "_settings", None)
    monkeypatch.setattr(rate_limits, "_store", None)
    monkeypatch.setattr(rate_limits, "load_rate_limit_settings", lambda: settings)
    monkeypatch.setattr(rate_limits, "Redis", Client)
    await rate_limits.init_rate_limit_runtime()
    await rate_limits.init_rate_limit_runtime()
    assert events == ["create", "ping"] and rate_limits._store is not None
    await rate_limits.close_rate_limit_runtime(); await rate_limits.close_rate_limit_runtime()
    assert events == ["create", "ping", "close"] and rate_limits._store is None and rate_limits._settings is None


@pytest.mark.asyncio
async def test_rate_limit_runtime_failure_closes_local_client_without_publishing_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    import rate_limits

    class Client:
        closed = 0
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return cls()
        async def ping(self):
            raise ConnectionError("offline")
        async def aclose(self):
            type(self).closed += 1

    monkeypatch.setattr(rate_limits, "_settings", None); monkeypatch.setattr(rate_limits, "_store", None)
    monkeypatch.setattr(rate_limits, "load_rate_limit_settings", lambda: type("Settings", (), {"valkey_url": "redis://test"})())
    monkeypatch.setattr(rate_limits, "Redis", Client)
    with pytest.raises(RuntimeError, match="backend unavailable"):
        await rate_limits.init_rate_limit_runtime()
    assert Client.closed == 1 and rate_limits._store is None and rate_limits._settings is None


@pytest.mark.asyncio
async def test_rate_limit_runtime_disabled_does_not_create_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import rate_limits
    monkeypatch.setattr(rate_limits, "_settings", None); monkeypatch.setattr(rate_limits, "_store", None)
    monkeypatch.setattr(rate_limits, "load_rate_limit_settings", lambda: None)
    monkeypatch.setattr(rate_limits.Redis, "from_url", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("client created")))
    await rate_limits.init_rate_limit_runtime()
    assert rate_limits._store is None and rate_limits._settings is None


class _Acquire:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_args):
        return None


class _Pool:
    def acquire(self):
        return _Acquire()


@pytest.mark.asyncio
async def test_lifespan_startup_failure_still_runs_cleanup_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    import main

    events: list[str] = []
    monkeypatch.setattr(main, "validate_required_env_vars", lambda role: events.append(f"validate:{role}"))
    monkeypatch.setattr(main, "init_oidc_runtime", AsyncMock(side_effect=lambda: events.append("oidc-init")))
    monkeypatch.setattr(main, "init_session_runtime", AsyncMock(side_effect=lambda: events.append("session-init")))
    monkeypatch.setattr(main, "init_rate_limit_runtime", AsyncMock(side_effect=lambda: events.append("rate-init")))
    monkeypatch.setattr(main, "close_rate_limit_runtime", AsyncMock(side_effect=lambda: events.append("rate-close")))
    monkeypatch.setattr(main, "close_oidc_runtime", AsyncMock(side_effect=lambda: events.append("oidc-close")))
    monkeypatch.setattr(main, "close_session_runtime", AsyncMock(side_effect=lambda: events.append("session-close")))
    monkeypatch.setattr(main, "init_db_pool", AsyncMock(side_effect=lambda: events.append("init")))
    monkeypatch.setattr(main, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(main, "attach_db_error_handler", lambda _pool: events.append("attach"))
    monkeypatch.setattr(main, "verify_migrations_current", AsyncMock(side_effect=RuntimeError("schema failed")))
    monkeypatch.setattr(main, "close_arq_pool", AsyncMock(side_effect=lambda: events.append("arq")))
    monkeypatch.setattr(main, "detach_db_error_handler", AsyncMock(side_effect=lambda: events.append("detach")))
    monkeypatch.setattr(main, "close_db_pool", AsyncMock(side_effect=lambda: events.append("db")))

    with pytest.raises(RuntimeError, match="schema failed"):
        async with main.lifespan(main.app):
            pass
    assert events[-6:] == ["arq", "detach", "db", "rate-close", "session-close", "oidc-close"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["close_arq_pool", "detach_db_error_handler", "close_db_pool", "close_rate_limit_runtime"])
async def test_lifespan_cleanup_continues_after_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    import main

    events: list[str] = []
    monkeypatch.setattr(main, "validate_required_env_vars", lambda role: None)
    monkeypatch.setattr(main, "init_oidc_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_session_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_rate_limit_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_db_pool", AsyncMock())
    monkeypatch.setattr(main, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(main, "attach_db_error_handler", lambda _pool: None)
    monkeypatch.setattr(main, "verify_migrations_current", AsyncMock())
    monkeypatch.setattr(main, "prewarm_pool", AsyncMock())
    monkeypatch.setattr(main, "get_arq_pool", AsyncMock())

    async def close_arq() -> None:
        events.append("arq")
        if failing == "close_arq_pool":
            raise RuntimeError("arq close failed")

    async def detach() -> None:
        events.append("detach")
        if failing == "detach_db_error_handler":
            raise RuntimeError("detach failed")

    async def close_db() -> None:
        events.append("db")
        if failing == "close_db_pool":
            raise RuntimeError("db close failed")

    monkeypatch.setattr(main, "close_arq_pool", close_arq)
    monkeypatch.setattr(main, "detach_db_error_handler", detach)
    monkeypatch.setattr(main, "close_db_pool", close_db)
    async def close_rate() -> None:
        events.append("rate")
        if failing == "close_rate_limit_runtime":
            raise RuntimeError("rate close failed")
    monkeypatch.setattr(main, "close_rate_limit_runtime", close_rate)
    async def close_oidc() -> None:
        events.append("oidc")
    monkeypatch.setattr(main, "close_oidc_runtime", close_oidc)
    async def close_session() -> None:
        events.append("session")
    monkeypatch.setattr(main, "close_session_runtime", close_session)

    with pytest.raises(RuntimeError):
        async with main.lifespan(main.app):
            pass
    assert events == ["arq", "detach", "db", "rate", "session", "oidc"]
