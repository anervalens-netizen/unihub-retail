from __future__ import annotations

import errno
import hashlib
import os
import pickle
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import asyncpg

import services.jobs as jobs
import services.importer as importer
import services.sales_import_recovery as sales_import_recovery
import services.sales_artifacts as sales_artifacts
import services.sales_generation_flow as sales_generation_flow
import services.sales_import_worker as sales_import_worker
import worker
from db.connection import close_db_pool, get_pool
from services.sales_generation import (
    SalesGenerationValidationError,
    SalesPolicyValidationError,
)
from services.sales_generation_flow import promote_sales_generation
from services.importer import _reconcile_sales_artifacts, reserve_snapshot


def _artifact(tmp_path: Path, content: bytes = b"sales source") -> tuple[Path, str]:
    digest = hashlib.sha256(content).hexdigest()
    source = tmp_path / f"{digest}.upload"
    source.write_bytes(content)
    return source, digest


def test_retain_is_content_addressed_durable_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)

    previous_umask = os.umask(0o007)
    try:
        retained = jobs.retain_sales_import_spool_file(
            source,
            import_month="2099-08",
            snapshot_id=7,
            expected_digest=digest,
            expected_bytes=12,
        )
    finally:
        os.umask(previous_umask)

    assert retained == tmp_path / "retained" / f"{digest}.source"
    assert not source.exists()
    assert retained.stat().st_mode & 0o777 == 0o660
    assert retained.parent.stat().st_mode & 0o7777 == 0o770
    assert jobs.verify_sales_import_artifact(retained, digest, 12) == 12
    assert jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=7,
        expected_digest=digest,
        expected_bytes=12,
    ) == retained


def test_retain_never_chmods_an_artifact_published_by_the_web_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rename keeps the web owner's mode; the import worker is not owner.

    Production uses a shared group with mode 0660.  The import worker may move
    and read the file, but Linux rejects chmod after the cross-identity rename.
    """
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    source.chmod(0o660)
    original_chmod = Path.chmod
    retained_chmod_attempts: list[Path] = []

    def reject_cross_identity_chmod(
        path: Path, mode: int, *, follow_symlinks: bool = True
    ) -> None:
        if path.parent.name == "retained":
            retained_chmod_attempts.append(path)
            raise PermissionError(errno.EPERM, "Operation not permitted", str(path))
        original_chmod(path, mode, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "chmod", reject_cross_identity_chmod)
    retained = jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=8,
        expected_digest=digest,
        expected_bytes=12,
    )
    assert retained.stat().st_mode & 0o777 == 0o660
    assert jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=8,
        expected_digest=digest,
        expected_bytes=12,
    ) == retained
    assert retained_chmod_attempts == []


def test_resolver_follows_an_atomic_move_to_the_canonical_retained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    retained = jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=7,
        expected_digest=digest,
        expected_bytes=12,
    )

    assert jobs.resolve_sales_import_artifact(source, digest, 12) == retained


def test_resolver_prefers_valid_retained_bytes_over_a_corrupt_queued_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    retained_dir = tmp_path / "retained"
    retained_dir.mkdir()
    (retained_dir / f"{digest}.source").write_bytes(b"sales source")
    source.write_bytes(b"corrupt")

    assert jobs.resolve_sales_import_artifact(source, digest, 12) == (
        retained_dir / f"{digest}.source"
    )


def test_resolver_fails_when_neither_artifact_matches_the_expected_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    retained_dir = tmp_path / "retained"
    retained_dir.mkdir()
    source.write_bytes(b"corrupt queued")
    (retained_dir / f"{digest}.source").write_bytes(b"corrupt retained")

    with pytest.raises(jobs.SalesImportArtifactError, match="integrity"):
        jobs.resolve_sales_import_artifact(source, digest, 12)


@pytest.mark.asyncio
async def test_worker_retry_repairs_post_move_db_failure_without_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    retained = jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=17,
        expected_digest=digest,
        expected_bytes=12,
    )
    recovered = {
        "id": 17,
        "import_month": "2099-08",
        "filename": "sales.xlsx",
        "is_month_final": False,
        "rows_in_file": 3,
        "rows_imported": 3,
        "coverage_report": {},
        "generation_token": "58daa48f-ceb4-4963-88ab-441a46fedd64",
        "owner_id": "a8bc1c44-752f-43c7-b0b0-f99b95134a74",
        "manifest_sha256": "a" * 64,
        "manifest": {
            "generation_state": "validated",
            "rows_filtered": 0,
            "store_count": 1,
            "agent_count": 1,
        },
        "source_artifact_state": "artifact_retaining",
    }
    find_recovery = AsyncMock(return_value=recovered)
    mark_retained = AsyncMock()
    parse_and_stage = AsyncMock(side_effect=AssertionError("validated rows must not be rebuilt"))
    monkeypatch.setattr(
        sales_generation_flow,
        "find_recoverable_sales_generation_for_artifact_retain",
        find_recovery,
    )
    monkeypatch.setattr(
        sales_generation_flow,
        "mark_sales_generation_artifact_retained",
        mark_retained,
    )
    monkeypatch.setattr(importer, "import_sales_file", parse_and_stage)

    result = await worker.import_sales_background(
        {"db_conn": MagicMock()},
        str(source),
        digest,
        12,
        "sales.xlsx",
        cutoff_date_iso="2099-08-12",
    )

    assert result["snapshot_id"] == 17
    assert result["generation_state"] == "validated"
    find_recovery.assert_awaited_once()
    assert find_recovery.await_args is not None
    assert find_recovery.await_args.kwargs["retained_path"] == str(retained)
    mark_retained.assert_awaited_once()
    parse_and_stage.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_returns_pickle_safe_sales_policy_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, digest = _artifact(tmp_path)
    failure = SalesPolicyValidationError(
        {
            "code": "invalid_workbook",
            "classification": "structural_contradiction",
            "blocking": True,
            "message": "Fișierul de vânzări este invalid",
        }
    )
    monkeypatch.setattr(
        sales_import_worker,
        "_execute_import",
        AsyncMock(side_effect=failure),
    )

    with pytest.raises(
        RuntimeError,
        match="Fișierul de vânzări este invalid",
    ) as caught:
        await sales_import_worker.run_sales_import_job(
            {"db_conn": MagicMock()},
            str(source),
            digest,
            12,
            "sales.xlsx",
        )

    restored = pickle.loads(pickle.dumps(caught.value))
    assert str(restored) == str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.asyncio
async def test_worker_retry_preserves_exact_queued_bytes_after_stage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    staged = importer.ImportResult(
        import_month="2099-08",
        rows_in_file=3,
        rows_imported=3,
        rows_filtered=0,
        store_count=1,
        agent_count=1,
        snapshot_id=18,
        filename="sales.xlsx",
        is_month_final=False,
        coverage_report={},
        generation_state="validated",
        generation_token="58daa48f-ceb4-4963-88ab-441a46fedd64",
        owner_id="a8bc1c44-752f-43c7-b0b0-f99b95134a74",
        manifest_sha256="a" * 64,
        manifest={"generation_state": "validated"},
    )
    parse_and_stage = AsyncMock(
        side_effect=[RuntimeError("transient PostgreSQL failure"), staged]
    )
    mark_retained = AsyncMock()
    monkeypatch.setattr(
        sales_generation_flow,
        "find_recoverable_sales_generation_for_artifact_retain",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(importer, "import_sales_file", parse_and_stage)
    monkeypatch.setattr(
        sales_generation_flow,
        "mark_sales_generation_artifact_retained",
        mark_retained,
    )

    with pytest.raises(RuntimeError, match="PostgreSQL"):
        await worker.import_sales_background(
            {"db_conn": MagicMock()},
            str(source),
            digest,
            12,
            "sales.xlsx",
        )

    assert source.read_bytes() == b"sales source"
    retried = await worker.import_sales_background(
        {"db_conn": MagicMock()},
        str(source),
        digest,
        12,
        "sales.xlsx",
    )

    retained = tmp_path / "retained" / f"{digest}.source"
    assert retried["snapshot_id"] == 18
    assert not source.exists()
    assert retained.read_bytes() == b"sales source"
    assert [call.args[1] for call in parse_and_stage.await_args_list] == [
        b"sales source",
        b"sales source",
    ]
    mark_retained.assert_awaited_once()


@pytest.mark.asyncio
async def test_worker_retry_recovers_validated_generation_before_artifact_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    recovered = {
        "id": 19,
        "import_month": "2099-08",
        "filename": "sales.xlsx",
        "is_month_final": False,
        "rows_in_file": 3,
        "rows_imported": 3,
        "coverage_report": {},
        "generation_token": "58daa48f-ceb4-4963-88ab-441a46fedd64",
        "owner_id": "a8bc1c44-752f-43c7-b0b0-f99b95134a74",
        "manifest_sha256": "a" * 64,
        "manifest": {
            "generation_state": "validated",
            "rows_filtered": 0,
            "store_count": 1,
            "agent_count": 1,
        },
        "source_artifact_state": "artifact_retaining",
    }
    staged = importer.ImportResult(
        import_month="2099-08",
        rows_in_file=3,
        rows_imported=3,
        rows_filtered=0,
        store_count=1,
        agent_count=1,
        snapshot_id=19,
        filename="sales.xlsx",
        is_month_final=False,
        coverage_report={},
        generation_state="validated",
        generation_token=str(recovered["generation_token"]),
        owner_id=str(recovered["owner_id"]),
        manifest_sha256=str(recovered["manifest_sha256"]),
        manifest={
            "generation_state": "validated",
            "rows_filtered": 0,
            "store_count": 1,
            "agent_count": 1,
        },
    )
    find_recovery = AsyncMock(side_effect=[None, recovered])
    parse_and_stage = AsyncMock(return_value=staged)
    mark_retained = AsyncMock()
    real_retain = sales_artifacts.retain_sales_import_spool_file
    retain_attempts = 0

    def fail_before_move_once(*args: object, **kwargs: object) -> Path:
        nonlocal retain_attempts
        retain_attempts += 1
        if retain_attempts == 1:
            raise OSError("simulated fsync failure before move")
        return real_retain(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        sales_generation_flow,
        "find_recoverable_sales_generation_for_artifact_retain",
        find_recovery,
    )
    monkeypatch.setattr(importer, "import_sales_file", parse_and_stage)
    monkeypatch.setattr(
        sales_generation_flow,
        "mark_sales_generation_artifact_retained",
        mark_retained,
    )
    monkeypatch.setattr(
        sales_import_worker,
        "retain_sales_import_spool_file",
        fail_before_move_once,
    )

    with pytest.raises(OSError, match="before move"):
        await worker.import_sales_background(
            {"db_conn": MagicMock()}, str(source), digest, 12, "sales.xlsx"
        )
    assert source.read_bytes() == b"sales source"

    retried = await worker.import_sales_background(
        {"db_conn": MagicMock()}, str(source), digest, 12, "sales.xlsx"
    )

    retained = tmp_path / "retained" / f"{digest}.source"
    assert retried["snapshot_id"] == 19
    assert retained.read_bytes() == b"sales source"
    parse_and_stage.assert_awaited_once()
    mark_retained.assert_awaited_once()
    assert retain_attempts == 2


@pytest.mark.asyncio
async def test_post_move_recovery_matches_the_exact_cutoff_including_null() -> None:
    conn = AsyncMock()
    conn.fetch.return_value = []

    recovered = (
        await sales_generation_flow.find_recoverable_sales_generation_for_artifact_retain(
            conn,
            queued_path="/spool/source.upload",
            retained_path="/spool/retained/source.source",
            source_sha256="a" * 64,
            source_byte_size=12,
            cutoff_date=None,
        )
    )

    assert recovered is None
    query = conn.fetch.await_args.args[0]
    assert "cutoff_date IS NOT DISTINCT FROM $5::date" in query
    assert conn.fetch.await_args.args[-1] is None


def test_retained_cleanup_is_explicit_rooted_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    retained_dir = tmp_path / "retained"
    retained_dir.mkdir()
    keep = retained_dir / f"{'a' * 64}.source"
    remove = retained_dir / f"{'b' * 64}.source"
    keep.write_bytes(b"keep")
    remove.write_bytes(b"remove")

    assert jobs.cleanup_sales_import_retained_artifacts({str(keep)}) == 1
    assert keep.exists()
    assert not remove.exists()
    assert jobs.cleanup_sales_import_retained_artifacts({str(keep)}) == 0


def test_retain_conflict_and_crash_after_move_fail_closed_then_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path, b"original")
    destination = tmp_path / "retained" / f"{digest}.source"
    destination.parent.mkdir()
    destination.write_bytes(b"conflict")
    with pytest.raises(jobs.SalesImportArtifactConflictError):
        jobs.retain_sales_import_spool_file(
            source,
            import_month="2099-08",
            snapshot_id=8,
            expected_digest=digest,
            expected_bytes=8,
        )

    destination.unlink()
    original_replace = Path.replace
    crashed = False

    def replace_then_crash(path: Path, target: Path) -> Path:
        nonlocal crashed
        result = original_replace(path, target)
        if target == destination and not crashed:
            crashed = True
            raise OSError("simulated worker crash after move")
        return result

    monkeypatch.setattr(Path, "replace", replace_then_crash)
    with pytest.raises(OSError, match="crash"):
        jobs.retain_sales_import_spool_file(
            source,
            import_month="2099-08",
            snapshot_id=8,
            expected_digest=digest,
            expected_bytes=8,
        )
    assert jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=8,
        expected_digest=digest,
        expected_bytes=8,
    ) == destination


@pytest.mark.parametrize("fault", ["chmod", "disk_full", "fsync", "readback"])
def test_retain_faults_never_report_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    if fault == "chmod":
        monkeypatch.setattr(Path, "chmod", lambda self, mode: (_ for _ in ()).throw(OSError("chmod fault")))
    elif fault == "disk_full":
        monkeypatch.setattr(
            Path,
            "replace",
            lambda _self, _target: (_ for _ in ()).throw(OSError(errno.ENOSPC, "disk full")),
        )
    elif fault == "fsync":
        monkeypatch.setattr(
            sales_artifacts,
            "_fsync_file",
            lambda _path: (_ for _ in ()).throw(OSError("fsync fault")),
        )
    else:
        monkeypatch.setattr(
            sales_artifacts,
            "_file_digest_and_size",
            lambda _path: ("0" * 64, 1),
        )
    with pytest.raises(OSError if fault != "readback" else jobs.SalesImportArtifactError):
        jobs.retain_sales_import_spool_file(
            source,
            import_month="2099-08",
            snapshot_id=9,
            expected_digest=digest,
            expected_bytes=12,
        )


@pytest.mark.asyncio
async def test_required_generation_cannot_promote_without_retained_metadata() -> None:
    conn = MagicMock()
    conn.transaction.return_value = _AsyncContext()
    conn.fetchrow = _async_value(
        {
            "id": 1,
            "import_month": "2099-08",
            "manifest": {"generation_state": "promoting", "anomalies": []},
            "manifest_sha256": "a" * 64,
            "source_sha256": "b" * 64,
            "expected_head_revision": 0,
            "is_month_final": False,
            "source_artifact_required": True,
            "source_artifact_state": "artifact_retaining",
            "source_artifact_sha256": "b" * 64,
            "source_artifact_bytes": 12,
            "source_artifact_retained_path": None,
        }
    )
    with pytest.raises(SalesGenerationValidationError, match="artefact"):
        await promote_sales_generation(
            conn,
            snapshot_id=1,
            generation_token="a" * 36,
            owner_id="b" * 36,
            expected_manifest_sha256="a" * 64,
            requested_by_sub="test:artifact",
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_database_rejects_terminal_required_generation_without_artifact() -> None:
    pool = await get_pool()
    month = "2099-06"
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", month)
            snapshot_id = await conn.fetchval(
                """
                INSERT INTO import_snapshots (
                    import_month, filename, status, rows_in_file, rows_imported,
                    source_sha256, source_artifact_required
                ) VALUES ($1, 'artifact-fence.xlsx', 'processing', 1, 0, $2, true)
                RETURNING id
                """,
                month,
                "a" * 64,
            )
            with pytest.raises(asyncpg.PostgresError, match="retained source artifact"):
                await conn.execute(
                    "UPDATE import_snapshots SET status = 'completed' WHERE id = $1",
                    snapshot_id,
                )
            assert await conn.fetchval(
                "SELECT status FROM import_snapshots WHERE id = $1", snapshot_id
            ) == "processing"
            await conn.execute("DELETE FROM import_snapshots WHERE id = $1", snapshot_id)
    finally:
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_artifact_intent_is_persisted_before_validation_and_reconciled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    source, digest = _artifact(tmp_path)
    pool = await get_pool()
    month = "2099-07"
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", month)
            snapshot_id = await reserve_snapshot(
                conn,
                month,
                "artifact-window.xlsx",
                1,
                source_sha256=digest,
                source_artifact_required=True,
                source_artifact_path=str(source),
                source_artifact_bytes=12,
            )
            row = await conn.fetchrow(
                """
                SELECT source_spool_path, source_artifact_state, manifest
                FROM import_snapshots WHERE id = $1
                """,
                snapshot_id,
            )
            assert dict(row) == {
                "source_spool_path": str(source),
                "source_artifact_state": "artifact_retaining",
                "manifest": None,
            }

        assert snapshot_id in await _reconcile_sales_artifacts(pool)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, source_artifact_state FROM import_snapshots WHERE id = $1",
                snapshot_id,
            )
            assert dict(row) == {
                "status": "failed",
                "source_artifact_state": "artifact_retained",
            }
            await conn.execute("DELETE FROM import_snapshots WHERE id = $1", snapshot_id)
    finally:
        await close_db_pool()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="Requires the explicitly isolated PostgreSQL test database",
)
async def test_retained_artifact_oserror_preserves_immutable_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pool = await get_pool()
    month = "2099-05"
    digest = "c" * 64
    retained_path = tmp_path / "retained" / f"{digest}.source"
    monkeypatch.setenv("SALES_IMPORT_SPOOL_DIR", str(tmp_path))
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM import_snapshots WHERE import_month = $1", month)
            snapshot_id = await conn.fetchval(
                """
                INSERT INTO import_snapshots (
                    import_month, filename, status, rows_in_file, rows_imported,
                    source_sha256, generation_token, owner_id, lease_until,
                    source_spool_path, source_artifact_required,
                    source_artifact_state, source_artifact_sha256,
                    source_artifact_bytes, source_artifact_retained_at,
                    source_artifact_retained_path
                ) VALUES (
                    $1, 'retained-oserror.xlsx', 'processing', 1, 0,
                    $2, gen_random_uuid(), gen_random_uuid(), now(),
                    $3, true,
                    'artifact_retained', $2, 12, now(),
                    $3
                )
                RETURNING id
                """,
                month,
                digest,
                str(retained_path),
            )
        monkeypatch.setattr(
            sales_import_recovery,
            "retain_sales_import_spool_file",
            MagicMock(side_effect=OSError("transient filesystem failure")),
        )

        assert await _reconcile_sales_artifacts(pool) == [snapshot_id]
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT source_artifact_state, source_artifact_sha256,
                       source_artifact_bytes, source_artifact_retained_path
                FROM import_snapshots WHERE id = $1
                """,
                snapshot_id,
            )
            assert dict(row) == {
                "source_artifact_state": "artifact_retained",
                "source_artifact_sha256": digest,
                "source_artifact_bytes": 12,
                "source_artifact_retained_path": str(retained_path),
            }
            await conn.execute("DELETE FROM import_snapshots WHERE id = $1", snapshot_id)
    finally:
        await close_db_pool()


class _AsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> bool:
        return False


def _async_value(value: object):
    async def get(*_args: object, **_kwargs: object) -> object:
        return value

    return get
