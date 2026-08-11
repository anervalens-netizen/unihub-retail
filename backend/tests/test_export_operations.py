from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import repositories.export_operations as repository_module
import services.export_artifact_cleanup as cleanup_module
import services.export_operations as operations_module
import services.exports as exports_package
import services.jobs as jobs_module
import worker
from repositories.export_operations import (
    ExportOperationCapacityError,
    ExportOperationsRepository,
)
from services.export_operations import (
    ExportArtifactExpiredError,
    ExportArtifactIntegrityError,
    ExportOperationConflictError,
    ExportOperationNotFoundError,
    ExportOperationsService,
    StoredExportArtifact,
    cleanup_export_operations,
    export_artifact_ttl_seconds,
    open_verified_export_artifact,
    persist_export_artifact,
    public_export_operation,
    remove_export_artifact,
    sweep_orphan_export_artifacts,
)
from services.exports import XlsxArtifact
from services.jobs import JobPublishUncertainError


NOW = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)


def operation(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": 7,
        "kind": "daily_metrics",
        "status": "queued",
        "job_id": "export-complex:7",
        "request_payload": {
            "export_mode": "table",
            "dataset": "stores",
            "months": ["2026-08"],
            "daily_metrics": ["total_sales"],
        },
        "request_sha256": "a" * 64,
        "requested_by_sub": "owner-1",
        "execution_owner": None,
        "execution_epoch": 0,
        "execution_lease_until": None,
        "artifact_key": None,
        "artifact_sha256": None,
        "artifact_size": None,
        "peak_rss_bytes": None,
        "build_seconds": None,
        "cell_count": None,
        "download_filename": None,
        "error_code": None,
        "created_at": NOW,
        "updated_at": NOW,
        "started_at": None,
        "finished_at": None,
        "expires_at": None,
        "download_claimed_at": None,
    }
    value.update(overrides)
    return value


class Acquire:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(self, *_args: object) -> None:
        return None


class Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class Pool:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def acquire(self) -> Acquire:
        return Acquire(self.connection)


class Connection:
    def __init__(self) -> None:
        self.fetchrow_results: list[Any] = []
        self.fetchval_results: list[Any] = []
        self.fetch_results: list[Any] = []
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []

    def transaction(self) -> Transaction:
        return Transaction()

    async def execute(self, sql: str, *args: Any) -> str:
        self.calls.append(("execute", sql, args))
        return "SELECT 1"

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", sql, args))
        return self.fetchrow_results.pop(0) if self.fetchrow_results else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchval", sql, args))
        return self.fetchval_results.pop(0) if self.fetchval_results else None

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", sql, args))
        return self.fetch_results.pop(0) if self.fetch_results else []


def configure_artifacts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "artifacts"
    monkeypatch.setenv("EXPORT_ARTIFACT_DIR", str(root))
    return root


def test_artifact_persistence_hash_open_and_remove(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = configure_artifacts(monkeypatch, tmp_path)
    content = b"PK" + b"xlsx" * 50
    source = XlsxArtifact(
        BytesIO(content), "safe.xlsx", len(content), hashlib.sha256(content).hexdigest(), 1024, 0.1, 10
    )

    stored = persist_export_artifact(source)

    path = root / stored.key
    assert path.read_bytes() == content
    assert stat_mode(path) == 0o600
    assert stored.sha256 == hashlib.sha256(content).hexdigest()
    opened = open_verified_export_artifact(
        key=stored.key,
        expected_sha256=stored.sha256,
        expected_size=stored.size,
        filename=stored.filename,
    )
    assert b"".join(opened.iter_chunks(17)) == content
    opened.close()
    remove_export_artifact(stored.key)
    assert not path.exists()


def test_salary_artifact_uses_isolated_namespace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = configure_artifacts(monkeypatch, tmp_path)
    content = b"PK-salary"
    source = XlsxArtifact(
        BytesIO(content),
        "salary.xlsx",
        len(content),
        hashlib.sha256(content).hexdigest(),
        1024,
        0.1,
        10,
    )

    stored = persist_export_artifact(source, namespace="salary")

    assert stored.key.startswith("salary/")
    path = root / stored.key
    assert path.read_bytes() == content
    opened = open_verified_export_artifact(
        key=stored.key,
        expected_sha256=stored.sha256,
        expected_size=stored.size,
        filename=stored.filename,
    )
    assert b"".join(opened.iter_chunks()) == content
    opened.close()
    remove_export_artifact(stored.key)
    assert not path.exists()


def stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def test_artifact_integrity_rejects_tamper_and_invalid_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = configure_artifacts(monkeypatch, tmp_path)
    content = b"PK-valid"
    source = XlsxArtifact(
        BytesIO(content), "safe.xlsx", 8, hashlib.sha256(content).hexdigest(), 1024, 0.1, 10
    )
    stored = persist_export_artifact(source)
    (root / stored.key).write_bytes(b"tampered")

    with pytest.raises(ExportArtifactIntegrityError):
        open_verified_export_artifact(
            key=stored.key,
            expected_sha256=stored.sha256,
            expected_size=stored.size,
            filename=stored.filename,
        )
    with pytest.raises(ExportArtifactIntegrityError):
        remove_export_artifact("../escape.xlsx")


def test_artifact_persistence_rejects_size_mismatch_and_output_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_artifacts(monkeypatch, tmp_path)
    with pytest.raises(ExportArtifactIntegrityError, match="size changed"):
        persist_export_artifact(
            XlsxArtifact(
                BytesIO(b"short"), "x.xlsx", 99, hashlib.sha256(b"short").hexdigest(), 1024, 0.1, 10
            )
        )
    with pytest.raises(ExportArtifactIntegrityError, match="digest changed"):
        persist_export_artifact(
            XlsxArtifact(BytesIO(b"same-size"), "x.xlsx", 9, "0" * 64, 1024, 0.1, 10)
        )
    monkeypatch.setattr(operations_module, "EXPORT_MAX_OUTPUT_BYTES", 4)
    with pytest.raises(ExportArtifactIntegrityError, match="output budget"):
        persist_export_artifact(
            XlsxArtifact(
                BytesIO(b"12345"), "x.xlsx", 5, hashlib.sha256(b"12345").hexdigest(), 1024, 0.1, 10
            )
        )


def test_export_ttl_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXPORT_ARTIFACT_TTL_SECONDS", "300")
    assert export_artifact_ttl_seconds() == 300
    monkeypatch.setenv("EXPORT_ARTIFACT_TTL_SECONDS", "299")
    with pytest.raises(RuntimeError, match="between"):
        export_artifact_ttl_seconds()
    monkeypatch.setenv("EXPORT_ARTIFACT_TTL_SECONDS", "invalid")
    with pytest.raises(RuntimeError, match="integer"):
        export_artifact_ttl_seconds()


@pytest.mark.asyncio
async def test_cleanup_claims_expiry_before_unlink_and_removes_orphans(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = configure_artifacts(monkeypatch, tmp_path)
    expired_key = f"{'1' * 32}.xlsx"
    orphan_key = f"{'2' * 32}.xlsx"
    active_key = f"{'3' * 32}.xlsx"
    root.mkdir(parents=True)
    for key in (expired_key, orphan_key, active_key):
        (root / key).write_bytes(b"xlsx")
        os.utime(root / key, (1, 1))
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    temp_artifact = temp_root / "unihub-export-stale.xlsx"
    temp_artifact.write_bytes(b"temp")
    os.utime(temp_artifact, (1, 1))
    monkeypatch.setattr(operations_module.tempfile, "gettempdir", lambda: str(temp_root))

    repo = SimpleNamespace(
        reconcile_stale=AsyncMock(return_value=[8]),
        claim_expired=AsyncMock(return_value=[{"id": 7, "artifact_key": expired_key}]),
        active_artifact_keys=AsyncMock(return_value={active_key}),
    )
    await cleanup_export_operations(repo)  # type: ignore[arg-type]
    await sweep_orphan_export_artifacts(repo)  # type: ignore[arg-type]

    repo.claim_expired.assert_awaited_once_with()
    assert not (root / expired_key).exists()
    assert not (root / orphan_key).exists()
    assert (root / active_key).exists()
    assert not temp_artifact.exists()


@pytest.mark.asyncio
async def test_cleanup_failure_occurs_after_db_expiry_claim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure_artifacts(monkeypatch, tmp_path)
    repo = SimpleNamespace(
        reconcile_stale=AsyncMock(return_value=[]),
        claim_expired=AsyncMock(return_value=[{"id": 7, "artifact_key": f"{'4' * 32}.xlsx"}]),
    )
    monkeypatch.setattr(operations_module, "remove_export_artifact", MagicMock(side_effect=OSError("disk")))

    with pytest.raises(OSError):
        await cleanup_export_operations(repo)  # type: ignore[arg-type]
    repo.claim_expired.assert_awaited_once_with()


def test_public_operation_never_exposes_request_or_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations_module, "business_now", lambda: NOW)
    response = public_export_operation(
        operation(
            status="completed",
            download_filename="report.xlsx",
        artifact_size=42,
        artifact_sha256="b" * 64,
        peak_rss_bytes=1024,
        build_seconds=0.2,
        cell_count=10,
            finished_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    )
    assert response.can_download is True
    assert "request_payload" not in response.model_dump()
    assert "requested_by_sub" not in response.model_dump()
    claimed = public_export_operation(
        operation(
            status="completed",
            download_filename="report.xlsx",
            artifact_size=42,
            artifact_sha256="b" * 64,
            peak_rss_bytes=1024,
            build_seconds=0.2,
            cell_count=10,
            finished_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            download_claimed_at=NOW,
        )
    )
    assert claimed.can_download is True
    logically_expired = public_export_operation(
        operation(
            status="completed",
            download_filename="report.xlsx",
            artifact_size=42,
            artifact_sha256="b" * 64,
            peak_rss_bytes=1024,
            build_seconds=0.2,
            cell_count=10,
            finished_at=NOW - timedelta(hours=2),
            expires_at=NOW - timedelta(hours=1),
        )
    )
    assert logically_expired.status == "expired"
    assert logically_expired.can_download is False


@pytest.mark.asyncio
async def test_repository_reserve_is_owner_and_capacity_bounded() -> None:
    conn = Connection()
    conn.fetchval_results = [False, 0]
    conn.fetchrow_results = [operation()]
    repo = ExportOperationsRepository(Pool(conn))  # type: ignore[arg-type]

    result = await repo.reserve(
        kind="daily_metrics",
        request_payload={"filters": {"site_code": ["S1"]}},
        request_sha256="a" * 64,
        requested_by_sub="owner-1",
    )

    assert result and result["id"] == 7
    insert = next(call for call in conn.calls if call[0] == "fetchrow")
    assert "$5 || ':' || id::TEXT" in insert[1]
    assert insert[2][-1] == "export-complex"
    assert "owner-1" in insert[2]

    with pytest.raises(ValueError, match="queue identity"):
        await repo.reserve(
            kind="salary_agents",
            request_payload={"export_kind": "agents", "site_code": []},
            request_sha256="a" * 64,
            requested_by_sub="owner-2",
        )

    owner_conn = Connection()
    owner_conn.fetchval_results = [True, 0]
    with pytest.raises(ExportOperationCapacityError, match="already"):
        await ExportOperationsRepository(Pool(owner_conn)).reserve(  # type: ignore[arg-type]
            kind="daily_metrics",
            request_payload={},
            request_sha256="a" * 64,
            requested_by_sub="owner-1",
        )

    cap_conn = Connection()
    cap_conn.fetchval_results = [False, repository_module.MAX_ACTIVE_EXPORT_OPERATIONS]
    with pytest.raises(ExportOperationCapacityError, match="capacity"):
        await ExportOperationsRepository(Pool(cap_conn)).reserve(  # type: ignore[arg-type]
            kind="daily_metrics",
            request_payload={},
            request_sha256="a" * 64,
            requested_by_sub="owner-1",
        )


@pytest.mark.asyncio
async def test_repository_all_lifecycle_transitions_and_owner_reads() -> None:
    conn = Connection()
    conn.fetchrow_results = [
        operation(),
        operation(),
        operation(),
        operation(status="running", execution_epoch=1),
    ]
    conn.fetchval_results = [7, 7, 7, 7, 7, 7]
    conn.fetch_results = [[{"id": 7}], [{"id": 7, "artifact_key": f"{'5' * 32}.xlsx"}], [{"artifact_key": f"{'6' * 32}.xlsx"}]]
    repo = ExportOperationsRepository(Pool(conn))  # type: ignore[arg-type]

    assert await repo.get(7) is not None
    assert await repo.get_owned(7, requested_by_sub="owner-1") is not None
    assert await repo.get_resumable_owned(requested_by_sub="owner-1") is not None
    assert await repo.claim(
        7,
        execution_owner="worker",
        lease_seconds=300,
        allowed_kinds=("daily_metrics", "daily_comparison"),
    ) is not None
    assert await repo.claim_download_owned(7, requested_by_sub="owner-1") is None
    assert await repo.heartbeat(7, execution_owner="worker", execution_epoch=1, lease_seconds=300)
    assert await repo.complete(
        7,
        execution_owner="worker",
        execution_epoch=1,
        artifact_key=f"{'5' * 32}.xlsx",
        artifact_sha256="b" * 64,
        artifact_size=5,
        peak_rss_bytes=1024,
        build_seconds=0.2,
        cell_count=10,
        download_filename="report.xlsx",
        ttl_seconds=3600,
    )
    assert await repo.fail_queued(7, error_code="queue_failed")
    assert await repo.fail_running(
        7,
        execution_owner="worker",
        execution_epoch=1,
        error_code="worker_failed",
    )
    assert await repo.fail_running(
        7,
        execution_owner="worker",
        execution_epoch=1,
        error_code="worker_cancelled",
        cancelled=True,
    )
    # No fourth fetchrow result: cancellation reports no matching active owner row.
    assert await repo.cancel_owned(7, requested_by_sub="owner-1") is None
    assert await repo.reconcile_stale(queued_timeout_seconds=300) == [7]
    assert (await repo.claim_expired())[0]["id"] == 7
    assert await repo.mark_corrupt(7, artifact_key=f"{'5' * 32}.xlsx")
    assert await repo.active_artifact_keys() == {f"{'6' * 32}.xlsx"}


class FakeOperationRepo:
    def __init__(self, current: dict[str, Any] | None = None) -> None:
        self.current = current
        self.reserve = AsyncMock(return_value=operation())
        self.get_owned = AsyncMock(return_value=current)
        self.get_resumable_owned = AsyncMock(return_value=current)
        self.claim_download_owned = AsyncMock(return_value=current)
        self.fail_queued = AsyncMock(return_value=True)
        self.cancel_owned = AsyncMock(return_value=current)
        self.mark_corrupt = AsyncMock(return_value=True)
        self.reconcile_stale = AsyncMock(return_value=[])
        self.claim_expired = AsyncMock(return_value=[])
        self.active_artifact_keys = AsyncMock(return_value=set())


@pytest.mark.asyncio
async def test_service_reserve_status_cancel_and_publish_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = operation()
    fake = FakeOperationRepo(queued)
    service = ExportOperationsService(MagicMock())
    service.repo = fake  # type: ignore[assignment]
    monkeypatch.setattr(operations_module, "cleanup_export_operations", AsyncMock())
    monkeypatch.setattr(exports_package.ExportsService, "validate_complex_request", lambda *_args: "daily_metrics")
    enqueue = AsyncMock(return_value=SimpleNamespace(job_id="export-complex:7"))
    monkeypatch.setattr(operations_module, "enqueue_complex_export", enqueue)

    created = await service.reserve(queued["request_payload"], requested_by_sub="owner-1")
    assert created.id == 7
    assert (await service.status(7, requested_by_sub="owner-1")).job_id == "export-complex:7"
    assert (await service.resumable(requested_by_sub="owner-1")) is not None
    assert (await service.cancel(7, requested_by_sub="owner-1")).status == "queued"
    fake.get_owned.assert_awaited_with(7, requested_by_sub="owner-1")

    uncertain = JobPublishUncertainError(job_id="export-complex:7")
    enqueue.side_effect = uncertain
    with pytest.raises(JobPublishUncertainError) as exc:
        await service.reserve(queued["request_payload"], requested_by_sub="owner-1")
    assert exc.value.operation_id == 7
    fake.fail_queued.assert_not_awaited()

    enqueue.side_effect = RuntimeError("rejected")
    with pytest.raises(RuntimeError, match="rejected"):
        await service.reserve(queued["request_payload"], requested_by_sub="owner-1")
    fake.fail_queued.assert_awaited_with(7, error_code="queue_publish_failed")


@pytest.mark.asyncio
async def test_salary_reservation_uses_only_the_salary_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued = operation(
        kind="salary_agents",
        job_id="salary-export:7",
        request_payload={
            "export_kind": "agents",
            "company_name": None,
            "site_code": ["B, Nord"],
            "regional": None,
            "asm": None,
            "year": None,
            "month": None,
            "q": None,
        },
    )
    fake = FakeOperationRepo(queued)
    fake.reserve.return_value = queued
    service = ExportOperationsService(MagicMock())
    service.repo = fake  # type: ignore[assignment]
    salary_enqueue = AsyncMock(
        return_value=SimpleNamespace(job_id="salary-export:7")
    )
    generic_enqueue = AsyncMock()
    monkeypatch.setattr(operations_module, "enqueue_salary_export", salary_enqueue)
    monkeypatch.setattr(operations_module, "enqueue_complex_export", generic_enqueue)

    created = await service.reserve_salary(
        queued["request_payload"],
        requested_by_sub="owner-1",
    )

    assert created.kind == "salary_agents"
    salary_enqueue.assert_awaited_once_with(7)
    generic_enqueue.assert_not_awaited()
    assert fake.reserve.await_args is not None
    assert fake.reserve.await_args.kwargs["job_prefix"] == "salary-export"


@pytest.mark.asyncio
async def test_service_owner_not_found_and_terminal_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(operations_module, "business_now", lambda: NOW)
    service = ExportOperationsService(MagicMock())
    fake = FakeOperationRepo(None)
    service.repo = fake  # type: ignore[assignment]
    monkeypatch.setattr(operations_module, "cleanup_export_operations", AsyncMock())
    with pytest.raises(ExportOperationNotFoundError):
        await service.status(7, requested_by_sub="other-owner")
    with pytest.raises(ExportOperationNotFoundError):
        await service.cancel(7, requested_by_sub="other-owner")

    fake.current = operation(status="completed", finished_at=NOW)
    fake.get_owned.return_value = fake.current
    with pytest.raises(ExportOperationConflictError):
        await service.cancel(7, requested_by_sub="owner-1")

    fake.current = operation(status="expired", finished_at=NOW)
    fake.get_owned.return_value = fake.current
    fake.claim_download_owned.return_value = None
    with pytest.raises(ExportArtifactExpiredError):
        await service.download(7, requested_by_sub="owner-1")

    fake.current = operation(status="running", started_at=NOW, execution_owner="w", execution_epoch=1)
    fake.get_owned.return_value = fake.current
    with pytest.raises(ExportOperationConflictError):
        await service.download(7, requested_by_sub="owner-1")

    fake.current = operation(
        status="completed",
        finished_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        download_claimed_at=NOW,
    )
    fake.get_owned.return_value = fake.current
    fake.claim_download_owned.return_value = None
    monkeypatch.setattr(
        operations_module,
        "open_verified_export_artifact",
        MagicMock(return_value=XlsxArtifact(BytesIO(b"PK"), "retry.xlsx", 2)),
    )
    retried = await service.download(7, requested_by_sub="owner-1")
    assert b"".join(retried.iter_chunks()) == b"PK"
    retried.close()


@pytest.mark.asyncio
async def test_service_download_reverifies_hash_and_marks_corrupt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = configure_artifacts(monkeypatch, tmp_path)
    key = f"{'7' * 32}.xlsx"
    content = b"PK-download"
    root.mkdir(parents=True)
    (root / key).write_bytes(content)
    completed = operation(
        status="completed",
        artifact_key=key,
        artifact_sha256=hashlib.sha256(content).hexdigest(),
        artifact_size=len(content),
        download_filename="download.xlsx",
        finished_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    fake = FakeOperationRepo(completed)
    service = ExportOperationsService(MagicMock())
    service.repo = fake  # type: ignore[assignment]
    monkeypatch.setattr(operations_module, "cleanup_export_operations", AsyncMock())
    enqueue_cleanup = AsyncMock(return_value=SimpleNamespace(job_id="cleanup"))
    monkeypatch.setattr(
        operations_module,
        "enqueue_export_artifact_cleanup",
        enqueue_cleanup,
    )

    artifact = await service.download(7, requested_by_sub="owner-1")
    assert b"".join(artifact.iter_chunks()) == content
    artifact.close()

    fake.claim_download_owned.return_value = completed

    (root / key).write_bytes(b"tampered")
    with pytest.raises(ExportArtifactIntegrityError):
        await service.download(7, requested_by_sub="owner-1")
    fake.mark_corrupt.assert_awaited_once_with(7, artifact_key=key)
    enqueue_cleanup.assert_awaited_once_with(key)
    # The web authority remains read-only; only the owning worker deletes it.
    assert (root / key).exists()
    removed = await worker.remove_export_artifact_background(
        {"worker_role": "exports"}, key
    )
    assert removed == {"artifact_removed": True, "namespace": "generic"}
    assert not (root / key).exists()


@pytest.mark.asyncio
async def test_corrupt_download_cleanup_failure_keeps_bounded_integrity_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = f"{'7' * 32}.xlsx"
    completed = operation(
        status="completed",
        artifact_key=key,
        artifact_sha256="a" * 64,
        artifact_size=10,
        download_filename="download.xlsx",
        finished_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    fake = FakeOperationRepo(completed)
    service = ExportOperationsService(MagicMock())
    service.repo = fake  # type: ignore[assignment]
    monkeypatch.setattr(
        operations_module,
        "open_verified_export_artifact",
        MagicMock(side_effect=ExportArtifactIntegrityError("tampered")),
    )
    monkeypatch.setattr(
        operations_module,
        "enqueue_export_artifact_cleanup",
        AsyncMock(side_effect=OSError("queue unavailable")),
    )

    with pytest.raises(ExportArtifactIntegrityError, match="tampered"):
        await service.download(7, requested_by_sub="owner-1")

    fake.mark_corrupt.assert_awaited_once_with(7, artifact_key=key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "queue_name"),
    [
        (f"{'1' * 32}.xlsx", jobs_module.EXPORT_QUEUE_NAME),
        (f"salary/{'2' * 32}.xlsx", jobs_module.SALARY_EXPORT_QUEUE_NAME),
    ],
)
async def test_artifact_cleanup_is_routed_to_its_authority_queue(
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    queue_name: str,
) -> None:
    pool = MagicMock()
    published = AsyncMock(return_value=SimpleNamespace(job_id="cleanup"))
    monkeypatch.setattr(
        cleanup_module.jobs, "_require_arq_pool", AsyncMock(return_value=pool)
    )
    monkeypatch.setattr(cleanup_module.jobs, "_publish_arq_job", published)

    await cleanup_module.enqueue_export_artifact_cleanup(key)

    assert published.await_args is not None
    assert published.await_args.args[:3] == (
        pool,
        "remove_export_artifact_background",
        key,
    )
    assert published.await_args.kwargs["_queue_name"] == queue_name
    assert published.await_args.kwargs["_job_id"].startswith(
        "export-artifact-cleanup:"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "accepted"),
    [
        (cleanup_module.ArqJobStatus.queued, True),
        (cleanup_module.ArqJobStatus.not_found, False),
    ],
)
async def test_artifact_cleanup_recovers_a_deterministic_publish_collision(
    monkeypatch: pytest.MonkeyPatch,
    status: cleanup_module.ArqJobStatus,
    accepted: bool,
) -> None:
    pool = MagicMock()
    existing = SimpleNamespace(status=AsyncMock(return_value=status))
    monkeypatch.setattr(
        cleanup_module.jobs, "_require_arq_pool", AsyncMock(return_value=pool)
    )
    monkeypatch.setattr(
        cleanup_module.jobs, "_publish_arq_job", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(cleanup_module, "Job", MagicMock(return_value=existing))
    key = f"{'3' * 32}.xlsx"

    if accepted:
        assert await cleanup_module.enqueue_export_artifact_cleanup(key) is existing
    else:
        with pytest.raises(RuntimeError, match="Failed to enqueue"):
            await cleanup_module.enqueue_export_artifact_cleanup(key)


@pytest.mark.asyncio
async def test_artifact_cleanup_validates_identity_and_bounds_unknown_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Invalid export artifact"):
        await cleanup_module.enqueue_export_artifact_cleanup("../escape.xlsx")

    pool = MagicMock()
    existing = SimpleNamespace(status=AsyncMock(side_effect=OSError("transport")))
    monkeypatch.setattr(
        cleanup_module.jobs, "_require_arq_pool", AsyncMock(return_value=pool)
    )
    monkeypatch.setattr(
        cleanup_module.jobs, "_publish_arq_job", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(cleanup_module, "Job", MagicMock(return_value=existing))

    with pytest.raises(JobPublishUncertainError):
        await cleanup_module.enqueue_export_artifact_cleanup(f"{'4' * 32}.xlsx")


@pytest.mark.asyncio
async def test_artifact_cleanup_worker_rejects_cross_namespace_authority() -> None:
    with pytest.raises(RuntimeError, match="wrong worker authority"):
        await worker.remove_export_artifact_background(
            {"worker_role": "exports"},
            f"salary/{'2' * 32}.xlsx",
        )


@pytest.mark.asyncio
async def test_resumable_prefers_active_then_one_unclaimed_completed_download() -> None:
    conn = Connection()
    completed = operation(
        status="completed",
        artifact_key=f"{'9' * 32}.xlsx",
        artifact_sha256="b" * 64,
        artifact_size=42,
        peak_rss_bytes=1024,
        build_seconds=0.2,
        cell_count=10,
        download_filename="report.xlsx",
        finished_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    conn.fetchrow_results = [completed, {**completed, "download_claimed_at": NOW}]
    repo = ExportOperationsRepository(Pool(conn))  # type: ignore[arg-type]

    resumable = await repo.get_resumable_owned(requested_by_sub="owner-1")
    claimed = await repo.claim_download_owned(7, requested_by_sub="owner-1")

    assert resumable is not None and resumable["status"] == "completed"
    assert claimed is not None and claimed["download_claimed_at"] == NOW
    resumable_sql = conn.calls[0][1]
    assert "status IN ('queued', 'running')" in resumable_sql
    assert "download_claimed_at IS NULL" in resumable_sql
    assert "CASE WHEN status IN ('queued', 'running') THEN 0 ELSE 1 END" in resumable_sql
    claim_sql = conn.calls[1][1]
    assert "download_claimed_at = now()" in claim_sql
    assert "download_claimed_at IS NULL" in claim_sql


@pytest.mark.asyncio
async def test_worker_deletes_artifact_when_completion_fence_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = operation(
        status="running",
        execution_owner="worker",
        execution_epoch=1,
        started_at=NOW,
    )
    repo = SimpleNamespace(
        claim=AsyncMock(return_value=running),
        heartbeat=AsyncMock(return_value=True),
        complete=AsyncMock(return_value=False),
        get=AsyncMock(return_value=operation(status="cancelled", finished_at=NOW)),
        fail_running=AsyncMock(),
    )
    monkeypatch.setattr(repository_module, "ExportOperationsRepository", lambda _pool: repo)

    artifact = XlsxArtifact(
        BytesIO(b"PK-worker"),
        "worker.xlsx",
        9,
        hashlib.sha256(b"PK-worker").hexdigest(),
        1024,
        0.1,
        10,
    )

    class FakeExportsService:
        def __init__(self, _repo: Any) -> None:
            pass

        def validate_complex_request(self, _request: dict[str, Any]) -> str:
            return "daily_metrics"

        async def build_xlsx_artifact(self, _request: dict[str, Any]) -> XlsxArtifact:
            return artifact

    monkeypatch.setattr(exports_package, "ExportsService", FakeExportsService)
    monkeypatch.setattr(exports_package, "ExportsRepository", MagicMock, raising=False)
    stored = StoredExportArtifact(
        f"{'8' * 32}.xlsx", "c" * 64, 9, "worker.xlsx", 1024, 0.1, 10
    )
    monkeypatch.setattr(operations_module, "persist_export_artifact", MagicMock(return_value=stored))
    removed = MagicMock()
    monkeypatch.setattr(operations_module, "remove_export_artifact", removed)
    monkeypatch.setattr(operations_module, "sweep_orphan_export_artifacts", AsyncMock())

    result = await worker.build_complex_export_background({"db_pool": MagicMock()}, 7)

    assert result == {"operation_id": 7, "status": "cancelled"}
    removed.assert_called_once_with(stored.key)


@pytest.mark.asyncio
async def test_worker_cancel_is_terminal_and_never_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = operation(
        status="running",
        execution_owner="worker",
        execution_epoch=1,
        started_at=NOW,
    )
    repo = SimpleNamespace(
        claim=AsyncMock(return_value=running),
        heartbeat=AsyncMock(return_value=False),
        complete=AsyncMock(),
        get=AsyncMock(),
        fail_running=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(repository_module, "ExportOperationsRepository", lambda _pool: repo)

    class WaitingExportsService:
        def __init__(self, _repo: Any) -> None:
            pass

        def validate_complex_request(self, _request: dict[str, Any]) -> str:
            return "daily_metrics"

        async def build_xlsx_artifact(self, _request: dict[str, Any]) -> XlsxArtifact:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    async def cancel_owner(
        _repo: Any,
        *,
        worker_task: asyncio.Task[Any],
        **_kwargs: Any,
    ) -> None:
        await asyncio.sleep(0)
        worker_task.cancel()

    monkeypatch.setattr(exports_package, "ExportsService", WaitingExportsService)
    monkeypatch.setattr(exports_package, "ExportsRepository", MagicMock, raising=False)
    monkeypatch.setattr(worker, "_export_heartbeat_loop", cancel_owner)
    monkeypatch.setattr(operations_module, "sweep_orphan_export_artifacts", AsyncMock())

    with pytest.raises(asyncio.CancelledError):
        await worker.build_complex_export_background({"db_pool": MagicMock()}, 7)

    repo.complete.assert_not_awaited()
    repo.fail_running.assert_awaited_once()
    assert repo.fail_running.await_args.kwargs["cancelled"] is True


def test_migration_contains_fencing_acl_and_owner_active_cap() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "db"
        / "migrations"
        / "055_durable_export_operations.sql"
    ).read_text()
    assert "uq_export_operations_owner_active" in sql
    assert "execution_epoch" in sql and "execution_lease_until" in sql
    assert "GRANT SELECT ON TABLE export_operations TO unihub_web_read, unihub_operations" in sql
    assert "GRANT INSERT ON TABLE export_operations TO unihub_business_write" in sql
    assert "UPDATE (status, artifact_key, error_code" in sql
    assert "request_payload IS DISTINCT" in sql
    assert "NEW.status NOT IN ('expired', 'failed')" in sql
    assert "NEW.error_code IS DISTINCT FROM 'artifact_integrity_failed'" in sql
    assert "OLD.artifact_sha256 IS DISTINCT FROM NEW.artifact_sha256" in sql
    assert operations_module.EXPORT_QUEUE_STALE_SECONDS > (
        repository_module.MAX_ACTIVE_EXPORT_OPERATIONS * 7_200
    )
