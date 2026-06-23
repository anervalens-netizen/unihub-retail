from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import db.connection
import services.jobs
import worker


def test_worker_uses_bounded_serial_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    worker_instance = MagicMock()
    create_worker = MagicMock(return_value=worker_instance)
    monkeypatch.setattr(worker, "create_worker", create_worker)

    worker.main()

    settings = create_worker.call_args.args[0]
    assert settings["max_jobs"] == 1
    assert settings["job_timeout"] == 1800
    assert settings["job_completion_wait"] == 60
    assert settings["health_check_interval"] == 30
    worker_instance.run.assert_called_once_with()


@pytest.mark.asyncio
async def test_worker_shutdown_closes_all_pools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    close_db_pool = AsyncMock()
    close_arq_pool = AsyncMock()
    monkeypatch.setattr(db.connection, "close_db_pool", close_db_pool)
    monkeypatch.setattr(services.jobs, "close_arq_pool", close_arq_pool)

    await worker.shutdown({})

    close_arq_pool.assert_awaited_once_with()
    close_db_pool.assert_awaited_once_with()
