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
async def test_oidc_runtime_success_is_network_lazy_singleton_and_closes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import oidc_verifier

    class Client:
        def __init__(self, **_kwargs):
            self.closed = 0
            created.append(self)
        async def aclose(self):
            self.closed += 1

    created: list[Client] = []

    settings = object()
    monkeypatch.setattr(oidc_verifier, "_client", None)
    monkeypatch.setattr(oidc_verifier, "_verifier", None)
    monkeypatch.setattr(oidc_verifier, "load_oidc_verifier_settings", lambda: settings)
    monkeypatch.setattr(oidc_verifier.httpx, "AsyncClient", Client)
    await oidc_verifier.init_oidc_runtime()
    await oidc_verifier.init_oidc_runtime()
    assert len(created) == 1 and oidc_verifier._client is created[0] and oidc_verifier.get_oidc_verifier()
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
    monkeypatch.setattr(main, "validate_required_env_vars", lambda: events.append("validate"))
    monkeypatch.setattr(main, "init_oidc_runtime", AsyncMock(side_effect=lambda: events.append("oidc-init")))
    monkeypatch.setattr(main, "close_oidc_runtime", AsyncMock(side_effect=lambda: events.append("oidc-close")))
    monkeypatch.setattr(main, "init_db_pool", AsyncMock(side_effect=lambda: events.append("init")))
    monkeypatch.setattr(main, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(main, "attach_db_error_handler", lambda _pool: events.append("attach"))
    monkeypatch.setattr(main, "ensure_schema_current", AsyncMock(side_effect=RuntimeError("schema failed")))
    monkeypatch.setattr(main, "close_arq_pool", AsyncMock(side_effect=lambda: events.append("arq")))
    monkeypatch.setattr(main, "detach_db_error_handler", AsyncMock(side_effect=lambda: events.append("detach")))
    monkeypatch.setattr(main, "close_db_pool", AsyncMock(side_effect=lambda: events.append("db")))

    with pytest.raises(RuntimeError, match="schema failed"):
        async with main.lifespan(main.app):
            pass
    assert events[-4:] == ["arq", "detach", "db", "oidc-close"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["close_arq_pool", "detach_db_error_handler"])
async def test_lifespan_cleanup_continues_after_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    import main

    events: list[str] = []
    monkeypatch.setattr(main, "validate_required_env_vars", lambda: None)
    monkeypatch.setattr(main, "init_oidc_runtime", AsyncMock())
    monkeypatch.setattr(main, "init_db_pool", AsyncMock())
    monkeypatch.setattr(main, "get_pool", AsyncMock(return_value=_Pool()))
    monkeypatch.setattr(main, "attach_db_error_handler", lambda _pool: None)
    monkeypatch.setattr(main, "ensure_schema_current", AsyncMock(return_value=False))
    monkeypatch.setattr(main, "apply_pending_migrations", AsyncMock(return_value=[]))
    monkeypatch.setattr(main, "prewarm_pool", AsyncMock())
    monkeypatch.setattr(main, "sync_visits_snapshot", AsyncMock(return_value=0))
    monkeypatch.setattr(main, "prewarm_special_cards_cache", lambda: None)
    monkeypatch.setattr(main, "get_arq_pool", AsyncMock())
    monkeypatch.setattr(main, "update_business_metrics", AsyncMock())

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

    monkeypatch.setattr(main, "close_arq_pool", close_arq)
    monkeypatch.setattr(main, "detach_db_error_handler", detach)
    monkeypatch.setattr(main, "close_db_pool", close_db)
    async def close_oidc() -> None:
        events.append("oidc")
    monkeypatch.setattr(main, "close_oidc_runtime", close_oidc)

    with pytest.raises(RuntimeError):
        async with main.lifespan(main.app):
            pass
    assert events == ["arq", "detach", "db", "oidc"]
