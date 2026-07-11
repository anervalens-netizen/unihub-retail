from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


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
    assert events[-3:] == ["arq", "detach", "db"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["close_arq_pool", "detach_db_error_handler"])
async def test_lifespan_cleanup_continues_after_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    import main

    events: list[str] = []
    monkeypatch.setattr(main, "validate_required_env_vars", lambda: None)
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

    with pytest.raises(RuntimeError):
        async with main.lifespan(main.app):
            pass
    assert events == ["arq", "detach", "db"]
