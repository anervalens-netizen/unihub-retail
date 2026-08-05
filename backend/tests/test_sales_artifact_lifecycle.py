from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import asyncpg

import services.jobs as jobs
from db.connection import close_db_pool, get_pool
from services.sales_generation import SalesGenerationValidationError
from services.sales_generation_flow import promote_sales_generation


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

    retained = jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=7,
        expected_digest=digest,
        expected_bytes=12,
    )

    assert retained == tmp_path / "retained" / f"{digest}.source"
    assert not source.exists()
    assert retained.stat().st_mode & 0o777 == 0o600
    assert jobs.verify_sales_import_artifact(retained, digest, 12) == 12
    assert jobs.retain_sales_import_spool_file(
        source,
        import_month="2099-08",
        snapshot_id=7,
        expected_digest=digest,
        expected_bytes=12,
    ) == retained


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
        monkeypatch.setattr(jobs, "_fsync_file", lambda _path: (_ for _ in ()).throw(OSError("fsync fault")))
    else:
        monkeypatch.setattr(jobs, "_file_digest_and_size", lambda _path: ("0" * 64, 1))
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


class _AsyncContext:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> bool:
        return False


def _async_value(value: object):
    async def get(*_args: object, **_kwargs: object) -> object:
        return value

    return get
