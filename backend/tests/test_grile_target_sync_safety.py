from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import asyncpg
import pytest

import db.connection as db_connection
import services.grile as grile_service
import services.grile_agent_targets as target_service
import services.jobs as jobs
import repositories.grile_agent_target_sync as sync_repository
import worker
from db.connection import close_db_pool, get_pool
from repositories.grile_agent_target_sync import GrileAgentTargetSyncRepository
from services.grile_agent_targets import (
    AgentTargetCandidate,
    AgentTargetRow,
    AgentTargetSyncResult,
    AgentTargetSyncBlockedError,
    AgentTargetsState,
    candidate_agent_codes,
    read_agent_targets_state,
    require_applicable_agent_target_sync,
    sync_agent_targets_from_grile,
)


class AsyncContext:
    def __init__(self, value: object | None = None):
        self.value = value

    async def __aenter__(self) -> object | None:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


def test_legacy_cli_is_dry_run_only_and_does_not_print_identity_details() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "import_grile_agent_targets.py"
    ).read_text(encoding="utf-8")
    assert "--apply" not in script
    assert "source_agent_name" not in script
    assert "resolved.site_code" not in script


@pytest.mark.asyncio
async def test_grile_check_worker_is_read_only_and_uses_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = AgentTargetsState(sha256="a" * 64, row_count=2)
    events: list[str] = []

    async def run_check_impl(*_args: object, **_kwargs: object) -> int:
        events.append("check")
        return 17

    async def sync_impl(*_args: object, **_kwargs: object) -> SimpleNamespace:
        events.append("diff")
        return SimpleNamespace(as_dict=lambda: {"apply": False, "diff": {}})

    async def read_state_impl(*_args: object, **_kwargs: object) -> AgentTargetsState:
        events.append("hash")
        return state

    run_check = AsyncMock(side_effect=run_check_impl)
    sync = AsyncMock(side_effect=sync_impl)
    state_reader = AsyncMock(side_effect=read_state_impl)
    pool = cast(asyncpg.Pool, object())
    monkeypatch.setattr(grile_service, "run_grile_check", run_check)
    monkeypatch.setattr(target_service, "sync_agent_targets_from_grile", sync)
    monkeypatch.setattr(target_service, "read_agent_targets_state", state_reader)

    result = await worker.grile_check_background(
        {"db_pool": pool},
        "2098-04",
        triggered_by_sub="stable-synthetic-subject",
    )

    run_check.assert_awaited_once()
    assert run_check.await_args is not None
    assert run_check.await_args.kwargs["triggered_by_sub"] == "stable-synthetic-subject"
    sync.assert_awaited_once_with(pool, month="2098-04")
    assert events == ["hash", "check", "diff", "hash"]
    assert result["agent_targets_before_sha256"] == result["agent_targets_after_sha256"]


@pytest.mark.asyncio
async def test_grile_check_worker_detects_any_agent_target_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_check = AsyncMock(return_value=18)
    monkeypatch.setattr(grile_service, "run_grile_check", run_check)
    monkeypatch.setattr(
        target_service,
        "sync_agent_targets_from_grile",
        AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {})),
    )
    monkeypatch.setattr(
        target_service,
        "read_agent_targets_state",
        AsyncMock(
            side_effect=[
                AgentTargetsState(sha256="a" * 64, row_count=1),
                AgentTargetsState(sha256="b" * 64, row_count=1),
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="modified agent_targets"):
        await worker.grile_check_background({"db_pool": object()}, "2098-05")


@pytest.mark.asyncio
async def test_grile_check_verifies_hash_even_when_the_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grile_service,
        "run_grile_check",
        AsyncMock(side_effect=RuntimeError("synthetic check failure")),
    )
    state_reader = AsyncMock(
        side_effect=[
            AgentTargetsState(sha256="a" * 64, row_count=1),
            AgentTargetsState(sha256="b" * 64, row_count=1),
        ]
    )
    monkeypatch.setattr(target_service, "read_agent_targets_state", state_reader)

    with pytest.raises(RuntimeError, match="modified agent_targets"):
        await worker.grile_check_background({"db_pool": object()}, "2098-05")

    assert state_reader.await_count == 2


@pytest.mark.asyncio
async def test_privileged_sync_worker_is_the_only_apply_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = SimpleNamespace(
        execute=AsyncMock(),
        transaction=lambda: AsyncContext(),
    )
    pool = SimpleNamespace(acquire=lambda: AsyncContext(conn))
    before = AgentTargetsState(sha256="a" * 64, row_count=1)
    after = AgentTargetsState(sha256="b" * 64, row_count=1)
    repo = SimpleNamespace(
        start=AsyncMock(
            return_value={
                "status": "running",
                "run_month": "2098-08",
                "mode": "sync",
            }
        ),
        get=AsyncMock(),
        finish=AsyncMock(return_value=True),
        finish_on_connection=AsyncMock(return_value=True),
        fail=AsyncMock(return_value=True),
    )
    prepared = AgentTargetSyncResult(
        month="2098-08",
        apply=False,
        enabled_managers=("*",),
        disabled_managers=(),
        sites_considered=1,
        sites_read=1,
        resolved=[],
        unresolved=[],
        skipped_managers={},
        diff={"empty_site_count": 0, "duplicate_target_count": 0},
        read_site_codes=("SYNTHETIC-SITE",),
    )
    sync = AsyncMock(return_value=prepared)
    apply = AsyncMock()
    monkeypatch.setattr(
        sync_repository,
        "GrileAgentTargetSyncRepository",
        lambda received_pool: repo if received_pool is pool else None,
    )
    monkeypatch.setattr(target_service, "sync_agent_targets_from_grile", sync)
    monkeypatch.setattr(target_service, "apply_agent_target_sync_on_connection", apply)
    monkeypatch.setattr(
        target_service,
        "read_agent_targets_state",
        AsyncMock(return_value=before),
    )
    monkeypatch.setattr(
        target_service,
        "read_agent_targets_state_on_connection",
        AsyncMock(side_effect=[before, after]),
    )

    result = await worker.grile_agent_targets_background(
        {"db_pool": pool},
        operation_id=11,
    )

    sync.assert_awaited_once_with(pool, month="2098-08")
    apply.assert_awaited_once_with(conn, prepared)
    repo.finish_on_connection.assert_awaited_once()
    repo.finish.assert_not_awaited()
    repo.fail.assert_not_awaited()
    assert result["before_sha256"] != result["after_sha256"]


@pytest.mark.asyncio
async def test_apply_is_blocked_when_an_enabled_sheet_has_no_agent_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = cast(asyncpg.Pool, object())
    monkeypatch.setattr(
        target_service,
        "_load_enabled_sheets",
        AsyncMock(return_value=([{"site_code": "SYNTHETIC-SITE"}], {})),
    )
    monkeypatch.setattr(
        target_service,
        "_read_candidates",
        AsyncMock(return_value=([], {"SYNTHETIC-SITE"}, [])),
    )
    monkeypatch.setattr(
        target_service,
        "_load_retail_agents",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        target_service,
        "_load_managed_targets",
        AsyncMock(return_value={}),
    )
    result = await sync_agent_targets_from_grile(pool, month="2098-12")
    with pytest.raises(AgentTargetSyncBlockedError, match="coverage incomplet"):
        require_applicable_agent_target_sync(result)


pytestmark_db = pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)


@pytest.mark.asyncio
@pytestmark_db
async def test_enqueue_error_does_not_fail_operation_claimed_by_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    month = "2098-05"
    repo = GrileAgentTargetSyncRepository(pool)

    class AcceptedThenDisconnectedQueue:
        async def enqueue_job(self, *_args: object, **_kwargs: object) -> None:
            assert isinstance(_args[1], int)
            operation_id = _args[1]
            claimed = await repo.start(operation_id)
            assert claimed is not None
            raise ConnectionError("synthetic response loss after publish")

    try:
        monkeypatch.setattr(
            db_connection,
            "get_pool",
            AsyncMock(return_value=pool),
        )
        monkeypatch.setattr(
            jobs,
            "get_arq_pool",
            AsyncMock(return_value=AcceptedThenDisconnectedQueue()),
        )

        with pytest.raises(ConnectionError, match="response loss"):
            await jobs.enqueue_grile_target_sync(
                month=month,
                mode="dry_run",
                requested_by_sub="stable-synthetic-subject",
            )

        async with pool.acquire() as conn:
            operation = await conn.fetchrow(
                """
                SELECT id, status
                FROM grile_agent_target_sync_runs
                WHERE run_month = $1
                """,
                month,
            )
        assert operation is not None
        assert operation["status"] == "running"
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_agent_target_sync_runs WHERE run_month = $1",
                month,
            )
        await close_db_pool()


@pytest.mark.asyncio
@pytestmark_db
async def test_dry_run_preserves_hash_and_privileged_sync_applies_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    month = "2098-06"
    site_code = "SYNTHETIC-GRILE-SITE"
    agent_code = sorted(candidate_agent_codes("Synthetic Alpha"))[0]
    candidate = AgentTargetCandidate(
        import_month=month,
        site_code=site_code,
        source_store_key="synthetic/store",
        manager="Synthetic manager",
        slot=1,
        source_agent_name="Synthetic Alpha",
        target_value=Decimal("200.00"),
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    is_active, first_seen_month, last_seen_month
                )
                VALUES ($1, 'Synthetic store', 'Synthetic company',
                        'Synthetic region', 'Synthetic manager', true, $2, $2)
                """,
                site_code,
                month,
            )
            await conn.execute(
                """
                INSERT INTO agent_targets (
                    import_month, site_code, agent, target_value, source_file
                )
                VALUES ($1, $2, $3, 100, 'retail-grile/synthetic')
                """,
                month,
                site_code,
                agent_code,
            )

        monkeypatch.setattr(
            target_service,
            "_load_enabled_sheets",
            AsyncMock(
                return_value=(
                    [
                        {
                            "site_code": site_code,
                            "sheet_id": "synthetic-sheet",
                            "registry_key": "synthetic/store",
                            "manager": "Synthetic manager",
                        }
                    ],
                    {},
                )
            ),
        )
        monkeypatch.setattr(
            target_service,
            "_read_candidates",
            AsyncMock(return_value=([candidate], {site_code}, [])),
        )
        monkeypatch.setattr(
            target_service,
            "_load_retail_agents",
            AsyncMock(return_value={site_code: {agent_code}}),
        )

        before = await read_agent_targets_state(pool, month)
        dry_run = await sync_agent_targets_from_grile(
            pool,
            month=month,
            enabled_managers=("*",),
            disabled_managers=(),
        )
        after_dry_run = await read_agent_targets_state(pool, month)

        assert before == after_dry_run
        assert dry_run.diff["update_count"] == 1
        repo = GrileAgentTargetSyncRepository(pool)
        reservation_status, operation = await repo.reserve(
            month=month,
            mode="sync",
            requested_by_sub="stable-synthetic-subject",
        )
        assert reservation_status == "enqueued"
        worker_result = await worker.grile_agent_targets_background(
            {"db_pool": pool},
            operation_id=int(operation["id"]),
        )
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT at.target_value, op.status, op.requested_by_sub,
                       op.before_sha256, op.after_sha256
                FROM agent_targets at
                JOIN grile_agent_target_sync_runs op ON op.id = $4
                WHERE at.import_month = $1
                  AND at.site_code = $2
                  AND at.agent = $3
                """,
                month,
                site_code,
                agent_code,
                int(operation["id"]),
            )
        assert row is not None
        assert Decimal(row["target_value"]) == Decimal("200.00")
        assert row["status"] == "completed"
        assert row["requested_by_sub"] == "stable-synthetic-subject"
        assert row["before_sha256"] != row["after_sha256"]
        assert worker_result["mode"] == "sync"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_targets WHERE import_month = $1", month)
            await conn.execute(
                "DELETE FROM grile_agent_target_sync_runs WHERE run_month = $1",
                month,
            )
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
        await close_db_pool()


@pytest.mark.asyncio
@pytestmark_db
async def test_sync_rolls_back_targets_when_audit_cannot_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = await get_pool()
    month = "2098-09"
    site_code = "SYNTHETIC-AUDIT-ROLLBACK"
    agent_code = "SYNTHETIC-AGENT"
    operation_id: int | None = None
    prepared = AgentTargetSyncResult(
        month=month,
        apply=False,
        enabled_managers=("*",),
        disabled_managers=(),
        sites_considered=1,
        sites_read=1,
        resolved=[
            AgentTargetRow(
                import_month=month,
                site_code=site_code,
                agent=agent_code,
                target_value=Decimal("200.00"),
                source_agent_name="Synthetic Alpha",
                source_store_key="synthetic/store",
                manager="Synthetic manager",
                match_method="synthetic",
            )
        ],
        unresolved=[],
        skipped_managers={},
        diff={
            "current_count": 1,
            "proposed_count": 1,
            "insert_count": 0,
            "update_count": 1,
            "delete_count": 0,
            "unchanged_count": 0,
            "proposed_sha256": "a" * 64,
            "empty_site_count": 0,
            "duplicate_target_count": 0,
        },
        read_site_codes=(site_code,),
    )
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO stores (
                    site_code, locatie, firma, regional, asm,
                    is_active, first_seen_month, last_seen_month
                )
                VALUES ($1, 'Synthetic store', 'Synthetic company',
                        'Synthetic region', 'Synthetic manager', true, $2, $2)
                """,
                site_code,
                month,
            )
            await conn.execute(
                """
                INSERT INTO agent_targets (
                    import_month, site_code, agent, target_value, source_file
                )
                VALUES ($1, $2, $3, 100, 'retail-grile/synthetic')
                """,
                month,
                site_code,
                agent_code,
            )
        repo = GrileAgentTargetSyncRepository(pool)
        status, operation = await repo.reserve(
            month=month,
            mode="sync",
            requested_by_sub="stable-synthetic-subject",
        )
        assert status == "enqueued"
        operation_id = int(operation["id"])
        monkeypatch.setattr(
            target_service,
            "sync_agent_targets_from_grile",
            AsyncMock(return_value=prepared),
        )
        monkeypatch.setattr(
            GrileAgentTargetSyncRepository,
            "finish_on_connection",
            AsyncMock(return_value=False),
        )

        with pytest.raises(RuntimeError, match="operation failed"):
            await worker.grile_agent_targets_background(
                {"db_pool": pool},
                operation_id=operation_id,
            )

        async with pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT target_value
                FROM agent_targets
                WHERE import_month = $1 AND site_code = $2 AND agent = $3
                """,
                month,
                site_code,
                agent_code,
            )
            operation_status = await conn.fetchval(
                "SELECT status FROM grile_agent_target_sync_runs WHERE id = $1",
                operation_id,
            )
        assert Decimal(value) == Decimal("100.00")
        assert operation_status == "failed"
    finally:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM agent_targets WHERE import_month = $1", month)
            await conn.execute(
                "DELETE FROM grile_agent_target_sync_runs WHERE run_month = $1",
                month,
            )
            await conn.execute("DELETE FROM stores WHERE site_code = $1", site_code)
        await close_db_pool()


@pytest.mark.asyncio
@pytestmark_db
async def test_sync_reservation_is_concurrent_and_persists_subject() -> None:
    pool = await get_pool()
    month = "2098-07"
    repo = GrileAgentTargetSyncRepository(pool)
    try:
        results = await asyncio.gather(
            repo.reserve(
                month=month,
                mode="dry_run",
                requested_by_sub="synthetic-subject-one",
            ),
            repo.reserve(
                month=month,
                mode="sync",
                requested_by_sub="synthetic-subject-two",
            ),
        )

        assert sorted(result[0] for result in results) == ["already_running", "enqueued"]
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT requested_by_sub, status
                FROM grile_agent_target_sync_runs
                WHERE run_month = $1
                """,
                month,
            )
        assert len(rows) == 1
        assert rows[0]["requested_by_sub"] in {
            "synthetic-subject-one",
            "synthetic-subject-two",
        }
        assert rows[0]["status"] == "queued"
    finally:
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM grile_agent_target_sync_runs WHERE run_month = $1",
                month,
            )
        await close_db_pool()
