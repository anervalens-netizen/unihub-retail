from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.grile_monthly as grile
from services.grile_monthly import ExtractedAgentRow, StoreEntry


class AsyncAcquire:
    def __init__(self, conn: MagicMock):
        self.conn = conn

    async def __aenter__(self) -> MagicMock:
        return self.conn

    async def __aexit__(self, *args: object) -> None:
        return None


def fake_pool(conn: MagicMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value = AsyncAcquire(conn)
    return pool


def entry(
    *,
    company: str = "Mobiup",
    store: str = "Park Lake",
    sheet_id: str = "sheet-1",
    site_code: str = "SITE01",
    manager: str = "Manager 1",
) -> StoreEntry:
    return StoreEntry(company, store, sheet_id, site_code, manager)


def extracted(*, status: str = "OK", error: str = "") -> ExtractedAgentRow:
    return ExtractedAgentRow(
        company="Mobiup",
        store="Park Lake",
        slot=1,
        agent="Agent Test" if status == "OK" else "",
        base_salary=2600 if status == "OK" else "",
        sales_commission=300 if status == "OK" else "",
        extra_location_commission=25 if status == "OK" else "",
        extra_hours_pay=150 if status == "OK" else "",
        bonuri=480 if status == "OK" else "",
        worked_hours=176 if status == "OK" else "",
        status=status,
        error=error,
        sheet_id="sheet-1",
    )


def test_month_helpers_and_output_paths(tmp_path: Path) -> None:
    assert grile.next_ym("2026-12") == "2027-01"
    assert grile.next_ym("2026-05") == "2026-06"
    assert grile.month_slug(" Iunie 2026 / Test ") == "Iunie-2026-Test"
    assert grile.safe_filename('  <bad>|name... ') == "_bad__name"
    assert grile.safe_filename("...") == "untitled"
    assert grile.build_final_export_path(tmp_path, "Iunie 2026").name == (
        "Tabel Salarii - Iunie 2026.xlsx"
    )
    assert grile.build_archive_manifest_path(tmp_path, "Iunie 2026").name == (
        "archive-manifest-Iunie-2026.json"
    )
    assert grile.build_archive_zip_path(tmp_path, "Iunie 2026").name == (
        "Grile - Iunie 2026.zip"
    )
    assert grile.build_reset_report_path(tmp_path, "Iulie 2026").name == (
        "reset-report-Iulie-2026.json"
    )
    assert grile.build_manager_zip_path(
        tmp_path, "Iunie 2026", "Manager/Unu"
    ).name == "Grile - Iunie 2026 - Manager - Unu.zip"
    assert grile.resolve_output_path("Iunie 2026", "Park/Lake", tmp_path).name == (
        "Tabel Salarii - Iunie 2026 - TEST Park - Lake.xlsx"
    )


def test_credentials_require_existing_service_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("GRILE_GOOGLE_SA_FILE", str(missing))

    with pytest.raises(FileNotFoundError, match="Service account Google lipsa"):
        grile.get_credentials()


def test_credentials_load_existing_service_account(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials_file = tmp_path / "service-account.json"
    credentials_file.write_text("{}")
    expected = object()
    loader = MagicMock(return_value=expected)
    monkeypatch.setenv("GRILE_GOOGLE_SA_FILE", str(credentials_file))
    monkeypatch.setattr(
        "google.oauth2.service_account.Credentials.from_service_account_file",
        loader,
    )

    assert grile.get_credentials() is expected
    loader.assert_called_once_with(str(credentials_file), scopes=grile.SCOPES)


def test_build_google_services_uses_shared_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = object()
    calls: list[tuple[str, str, object, bool]] = []

    def build(service: str, version: str, *, credentials: object, cache_discovery: bool):
        calls.append((service, version, credentials, cache_discovery))
        return f"{service}-client"

    monkeypatch.setattr(grile, "get_credentials", lambda: credentials)
    monkeypatch.setattr(grile, "build", build)

    assert grile.build_google_services() == ("sheets-client", "drive-client")
    assert calls == [
        ("sheets", "v4", credentials, False),
        ("drive", "v3", credentials, False),
    ]


def test_retry_api_retries_transient_and_wraps_terminal_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    sleeps: list[float] = []

    class ApiError(Exception):
        def __init__(self, status: int):
            super().__init__(f"status {status}")
            self.resp = SimpleNamespace(status=status)

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ApiError(503)
        return "ok"

    monkeypatch.setattr(grile.time, "sleep", sleeps.append)
    assert grile.retry_api(flaky, label="read", attempts=4, base_delay=0.5) == "ok"
    assert sleeps == [0.5, 1.0]

    with pytest.raises(RuntimeError, match="read: status 400"):
        grile.retry_api(
            lambda: (_ for _ in ()).throw(ApiError(400)),
            label="read",
        )


@pytest.mark.asyncio
async def test_load_entries_normalizes_registry_and_filters() -> None:
    conn = MagicMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "registry_key": "Mobicell/AFI Cotroceni",
                "firma": "ignored",
                "locatie": "ignored",
                "sheet_id": "sheet-1",
                "site_code": "SITE01",
                "asm": " Manager 1 ",
            },
            {
                "registry_key": None,
                "firma": "Mobiup",
                "locatie": "Park Lake",
                "sheet_id": "sheet-2",
                "site_code": "SITE02",
                "asm": "",
            },
        ]
    )
    pool = fake_pool(conn)

    entries = await grile.load_entries(pool, only="manager 1")

    assert entries == [
        StoreEntry(
            "Mobicell",
            "AFI Cotroceni",
            "sheet-1",
            "SITE01",
            "Manager 1",
        )
    ]

    with pytest.raises(RuntimeError, match="No active grile"):
        await grile.load_entries(pool, only="missing")


def test_operation_serialization_and_number_helpers() -> None:
    assert grile._operation_to_dict(None) is None
    assert grile._operation_to_dict({"id": 1, "result": '{"ok": true}'}) == {
        "id": 1,
        "result": {"ok": True},
    }
    assert grile.scalar([]) == ""
    assert grile.scalar([[]]) == ""
    assert grile.scalar([[7]]) == 7
    assert grile.to_number(None) == 0
    assert grile.to_number(12) == 12
    assert grile.to_number("1.234,50") == 1234.5
    assert grile.to_number("invalid") == 0
    assert grile.to_number(object()) == 0
    assert grile.sum_scalars(
        [{"values": [["1,5"]]}, {"values": [[2]]}, {"values": []}]
    ) == 3.5


@pytest.mark.asyncio
async def test_operation_state_helpers_issue_expected_updates() -> None:
    conn = MagicMock()
    conn.execute = AsyncMock(
        side_effect=[
            "UPDATE 1",
            "UPDATE 0",
            "UPDATE 1",
            "UPDATE 1",
            "UPDATE 1",
            "UPDATE 1",
        ]
    )
    conn.executemany = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"status": "completed"})
    pool = fake_pool(conn)

    await grile.attach_monthly_operation_job(pool, operation_id=1, job_id="job-1")
    assert await grile.start_monthly_operation(pool, 1) is False
    await grile.heartbeat_monthly_operation(pool, 1)
    await grile.fail_monthly_operation(pool, 1, error_message="failed")
    await grile.ensure_reset_items(
        pool,
        operation_id=1,
        closing_month_key="2026-06",
        next_month_key="2026-07",
        entries=[entry()],
    )
    previous = await grile.get_previous_completed_reset_item(
        pool,
        closing_month_key="2026-06",
        site_code="SITE01",
    )
    await grile.mark_reset_item_running(pool, operation_id=1, site_code="SITE01")
    await grile.finish_reset_item(
        pool,
        operation_id=1,
        site_code="SITE01",
        status="completed",
    )

    assert previous == {"status": "completed"}
    records = conn.executemany.await_args.args[1]
    assert records[0][:7] == (
        1,
        "2026-06",
        "2026-07",
        "SITE01",
        "sheet-1",
        "Mobiup",
        "Park Lake",
    )


def test_validate_archive_manifest_accepts_complete_and_reports_all_failures(
    tmp_path: Path,
) -> None:
    xlsx = tmp_path / "store.xlsx"
    archive = tmp_path / "archive.zip"
    xlsx.write_bytes(b"xlsx")
    archive.write_bytes(b"zip")
    valid = {
        "registry_count": 1,
        "exported_count": 1,
        "error_count": 0,
        "zip_path": str(archive),
        "stores": [
            {
                "company": "Mobiup",
                "store": "Park Lake",
                "status": "OK",
                "xlsx_path": str(xlsx),
            }
        ],
    }
    assert grile.validate_archive_manifest(valid, 1) == (True, [])

    invalid = {
        "registry_count": 2,
        "exported_count": 0,
        "error_count": 1,
        "zip_path": str(tmp_path / "missing.zip"),
        "stores": [
            {
                "company": "Mobiup",
                "store": "Park Lake",
                "status": "ERROR",
                "xlsx_path": str(tmp_path / "missing.xlsx"),
            }
        ],
    }
    ok, errors = grile.validate_archive_manifest(invalid, 1)
    assert ok is False
    assert len(errors) == 6


def make_sheets_value_service(value_ranges: list[dict[str, Any]] | Exception):
    request = MagicMock()
    if isinstance(value_ranges, Exception):
        request.execute.side_effect = value_ranges
    else:
        request.execute.return_value = {"valueRanges": value_ranges}
    values = MagicMock()
    values.batchGet.return_value = request
    spreadsheets = MagicMock()
    spreadsheets.values.return_value = values
    service = MagicMock()
    service.spreadsheets.return_value = spreadsheets
    return service


def test_extract_store_rows_reads_two_slots_and_returns_error_row() -> None:
    values: list[dict[str, Any]] = []
    for agent in ("Agent 1", ""):
        raw = [
            agent,
            2600,
            10,
            20,
            30,
            40,
            50,
            25,
            150,
            480,
            176,
        ]
        values.extend({"values": [[value]]} if value != "" else {"values": []} for value in raw)

    rows = grile.extract_store_rows(make_sheets_value_service(values), entry())

    assert len(rows) == 1
    assert rows[0].agent == "Agent 1"
    assert rows[0].sales_commission == 150

    error_rows = grile.extract_store_rows(
        make_sheets_value_service(RuntimeError("Google failed")),
        entry(),
    )
    assert error_rows[0].status == "ERROR"
    assert "Google failed" in error_rows[0].error


@pytest.mark.asyncio
async def test_finalize_month_builds_output_with_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [entry(), entry(store="Store 2", sheet_id="sheet-2", site_code="SITE02")]
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=entries))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))
    monkeypatch.setattr(
        grile,
        "extract_store_rows",
        MagicMock(side_effect=[[extracted()], [extracted(status="ERROR", error="bad")]]),
    )

    output = await grile.finalize_month(
        MagicMock(),
        "Iunie 2026",
        only="test",
        delay=0,
    )

    assert output.exists()
    assert "TEST test" in output.name


@pytest.mark.asyncio
async def test_finalize_month_sleeps_only_between_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [entry(), entry(store="Store 2", sheet_id="sheet-2")]
    sleeps: list[float] = []
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=entries))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))
    monkeypatch.setattr(grile, "extract_store_rows", MagicMock(return_value=[extracted()]))
    monkeypatch.setattr(grile.time, "sleep", sleeps.append)

    await grile.finalize_month(MagicMock(), "Iunie 2026", delay=0.25)

    assert sleeps == [0.25]


def test_export_sheet_xlsx_success_empty_and_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Downloader:
        def __init__(self, handle, request):
            self.handle = handle
            self.request = request

        def next_chunk(self):
            self.handle.write(self.request)
            return None, True

    drive = MagicMock()
    drive.files.return_value.export_media.return_value = b"xlsx"
    monkeypatch.setattr(grile, "MediaIoBaseDownload", Downloader)
    output = tmp_path / "store.xlsx"

    result = grile.export_sheet_xlsx(drive, entry(), output)
    assert result["status"] == "OK"
    assert result["bytes"] == 4

    drive.files.return_value.export_media.return_value = b""
    empty = grile.export_sheet_xlsx(drive, entry(), tmp_path / "empty.xlsx")
    assert empty["status"] == "ERROR"

    drive.files.return_value.export_media.side_effect = RuntimeError("denied")
    failed = grile.export_sheet_xlsx(drive, entry(), tmp_path / "failed.xlsx")
    assert failed["status"] == "ERROR"
    assert failed["xlsx_path"] == ""


def test_archive_and_manager_zips_preserve_relative_paths(tmp_path: Path) -> None:
    archive_dir = grile.build_archive_dir(tmp_path, "Iunie 2026")
    first = archive_dir / "Mobiup" / "Store 1.xlsx"
    second = archive_dir / "Mobicell" / "Store 2.xlsx"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    zip_path = archive_dir / "all.zip"

    grile.create_archive_zip(zip_path, [first, second], archive_dir)
    manager_zips = grile.create_manager_zips(
        tmp_path,
        "Iunie 2026",
        [
            {"status": "OK", "manager": "Manager 1", "xlsx_path": str(first)},
            {"status": "OK", "manager": "", "xlsx_path": str(second)},
            {"status": "ERROR", "manager": "Ignored", "xlsx_path": ""},
        ],
    )

    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == [
            "Mobiup/Store 1.xlsx",
            "Mobicell/Store 2.xlsx",
        ]
    assert sorted(manager_zips) == ["Manager 1", "Neatribuit"]

    summary = grile.summarize_archive_results(
        "Iunie 2026",
        2,
        [
            {"status": "OK"},
            {"status": "ERROR"},
        ],
        zip_path,
        manager_zips,
    )
    assert summary["exported_count"] == 1
    assert summary["error_count"] == 1


@pytest.mark.asyncio
async def test_archive_month_writes_valid_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [
        entry(),
        entry(
            company="Mobicell",
            store="Store 2",
            sheet_id="sheet-2",
            site_code="SITE02",
            manager="Manager 2",
        ),
    ]
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=entries))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))

    def export(_drive: object, item: StoreEntry, output_path: Path) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(item.sheet_id.encode())
        return {
            "company": item.company,
            "store": item.store,
            "site_code": item.site_code,
            "manager": item.manager,
            "sheet_id": item.sheet_id,
            "status": "OK",
            "xlsx_path": str(output_path),
            "bytes": output_path.stat().st_size,
            "error": "",
        }

    monkeypatch.setattr(grile, "export_sheet_xlsx", export)

    manifest_path = await grile.archive_month(
        MagicMock(),
        "Iunie 2026",
        delay=0,
    )

    manifest = json.loads(manifest_path.read_text())
    assert manifest["exported_count"] == 2
    assert Path(manifest["zip_path"]).exists()
    assert len(manifest["manager_zip_paths"]) == 2


@pytest.mark.asyncio
async def test_archive_month_rejects_incomplete_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=[entry()]))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))
    monkeypatch.setattr(
        grile,
        "export_sheet_xlsx",
        lambda *_args: {
            "company": "Mobiup",
            "store": "Park Lake",
            "status": "ERROR",
            "xlsx_path": "",
            "error": "failed",
        },
    )

    with pytest.raises(RuntimeError, match="Archive is incomplete"):
        await grile.archive_month(MagicMock(), "Iunie 2026", delay=0)


@pytest.mark.asyncio
async def test_archive_month_sleeps_only_between_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = [entry(), entry(store="Store 2", sheet_id="sheet-2")]
    sleeps: list[float] = []
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=entries))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))

    def export(_drive: object, item: StoreEntry, output_path: Path) -> dict[str, Any]:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"x")
        return {
            "company": item.company,
            "store": item.store,
            "site_code": item.site_code,
            "manager": item.manager,
            "sheet_id": item.sheet_id,
            "status": "OK",
            "xlsx_path": str(output_path),
            "bytes": 1,
            "error": "",
        }

    monkeypatch.setattr(grile, "export_sheet_xlsx", export)
    monkeypatch.setattr(grile.time, "sleep", sleeps.append)

    await grile.archive_month(MagicMock(), "Iunie 2026", delay=0.25)

    assert sleeps == [0.25]


def test_archive_preconditions(tmp_path: Path) -> None:
    missing_export = tmp_path / "missing.xlsx"
    with pytest.raises(RuntimeError, match="Final export does not exist"):
        grile.assert_final_export_exists(missing_export, force=False)
    grile.assert_final_export_exists(missing_export, force=True)

    with pytest.raises(RuntimeError, match="Archive manifest does not exist"):
        grile.assert_archive_complete(
            tmp_path,
            "Iunie 2026",
            expected_count=1,
            force=False,
        )
    grile.assert_archive_complete(
        tmp_path,
        "Iunie 2026",
        expected_count=1,
        force=True,
    )

    manifest_path = grile.build_archive_manifest_path(tmp_path, "Iunie 2026")
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "registry_count": 0,
                "exported_count": 0,
                "error_count": 1,
                "stores": [],
                "zip_path": "",
            }
        )
    )
    with pytest.raises(RuntimeError, match="Archive is incomplete"):
        grile.assert_archive_complete(
            tmp_path,
            "Iunie 2026",
            expected_count=1,
            force=False,
        )


def test_reset_store_dry_run_success_and_error() -> None:
    assert grile.reset_store(None, entry(), dry_run=True)["status"] == "DRY_RUN"

    request = MagicMock()
    request.execute.return_value = {}
    values = MagicMock()
    values.batchClear.return_value = request
    spreadsheets = MagicMock()
    spreadsheets.values.return_value = values
    service = MagicMock()
    service.spreadsheets.return_value = spreadsheets
    assert grile.reset_store(service, entry(), dry_run=False)["status"] == "OK"

    request.execute.side_effect = RuntimeError("clear failed")
    result = grile.reset_store(service, entry(), dry_run=False)
    assert result["status"] == "ERROR"
    assert "clear failed" in result["error"]


@pytest.mark.asyncio
async def test_reset_month_dry_run_writes_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=[entry()]))

    report_path = await grile.reset_month(
        MagicMock(),
        "Iunie 2026",
        "Iulie 2026",
        dry_run=True,
        force=True,
        operation_id=7,
    )

    report = json.loads(report_path.read_text())
    assert report["operation_id"] == 7
    assert report["stores"][0]["status"] == "DRY_RUN"


@pytest.mark.asyncio
async def test_reset_month_live_failure_marks_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(grile, "load_entries", AsyncMock(return_value=[entry()]))
    monkeypatch.setattr(grile, "build_google_services", lambda: (object(), object()))
    monkeypatch.setattr(grile, "ensure_reset_items", AsyncMock())
    monkeypatch.setattr(grile, "heartbeat_monthly_operation", AsyncMock())
    monkeypatch.setattr(grile, "get_previous_completed_reset_item", AsyncMock(return_value=None))
    monkeypatch.setattr(grile, "mark_reset_item_running", AsyncMock())
    finish = AsyncMock()
    monkeypatch.setattr(grile, "finish_reset_item", finish)
    monkeypatch.setattr(
        grile,
        "reset_store",
        lambda *_args, **_kwargs: {
            "company": "Mobiup",
            "store": "Park Lake",
            "site_code": "SITE01",
            "sheet_id": "sheet-1",
            "status": "ERROR",
            "error": "Google failure",
            "ranges": [],
        },
    )

    with pytest.raises(RuntimeError, match="1 errors"):
        await grile.reset_month(
            MagicMock(),
            "Iunie 2026",
            "Iulie 2026",
            dry_run=False,
            force=True,
            operation_id=7,
            closing_month_key="2026-06",
            next_month_key="2026-07",
        )

    finish_call = finish.await_args
    assert finish_call is not None
    assert finish_call.kwargs["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["finalize", "archive", "reset"])
async def test_run_monthly_op_dispatches_and_finishes(
    op: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = object()
    monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(grile, "start_monthly_operation", AsyncMock(return_value=False))
    monkeypatch.setattr(grile, "heartbeat_monthly_operation", AsyncMock())
    monkeypatch.setattr(grile, "finalize_month", AsyncMock())
    monkeypatch.setattr(grile, "archive_month", AsyncMock())
    monkeypatch.setattr(grile, "reset_month", AsyncMock())
    finish = AsyncMock()
    monkeypatch.setattr(grile, "finish_monthly_operation", finish)

    result = await grile.run_monthly_op(
        op=op,
        month="2026-06",
        only="Store",
        dry_run=True,
        operation_id=9,
    )

    assert result["status"] == "success"
    assert result["operation_id"] == 9
    finish.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_monthly_op_captures_failure_and_validates_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Operatie necunoscuta"):
        await grile.run_monthly_op(op="invalid", month="2026-06")

    monkeypatch.setattr("db.connection.get_pool", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        grile,
        "finalize_month",
        AsyncMock(side_effect=RuntimeError("finalize failed")),
    )
    result = await grile.run_monthly_op(op="finalize", month="2026-06")
    assert result["status"] == "failed"
    assert result["exit_code"] == -1
    assert "finalize failed" in result["output"]


@pytest.mark.asyncio
async def test_fetch_download_final_archive_missing_and_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grile, "OUTPUTS_DIR", tmp_path)
    final_path = grile.build_final_export_path(tmp_path, "Iunie 2026")
    final_path.write_bytes(b"final")
    archive_path = grile.build_archive_zip_path(tmp_path, "Iunie 2026")
    archive_path.parent.mkdir(parents=True)
    archive_path.write_bytes(b"archive")

    content, filename, media = await grile.fetch_download("final", "2026-06")
    assert (content, filename) == (b"final", "Tabel Salarii - Iunie 2026.xlsx")
    assert "spreadsheetml" in media

    content, filename, media = await grile.fetch_download("archive", "2026-06")
    assert (content, filename, media) == (
        b"archive",
        "Arhiva Grile - Iunie 2026.zip",
        "application/zip",
    )

    archive_path.unlink()
    with pytest.raises(FileNotFoundError):
        await grile.fetch_download("archive", "2026-06")
    with pytest.raises(ValueError, match="Tip download necunoscut"):
        await grile.fetch_download("invalid", "2026-06")
