from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict
from unittest.mock import AsyncMock, MagicMock

import pytest

import services.grile_pilot_v2_sync as sync_module
from services.grile_pilot_v2_registry import PilotV2Sheet
from services.grile_pilot_v2_sync import (
    PilotV2Source,
    _batch_requests,
    _read_sheet_state,
    _sales_source_revision,
    _serial_day,
    _serial_instant,
    _snapshot_payload,
    _store_source,
    guard_sales_generation_lineage,
    load_pilot_v2_source,
    sync_pilot_v2_sheets,
)


GENERATION_HASH = "a" * 64
NEXT_GENERATION_HASH = "b" * 64
class _Lineage(TypedDict):
    generation_hash: str
    sales_revision: int
    campaign_revision: int
    contest_revision: int


LINEAGE: _Lineage = {
    "generation_hash": GENERATION_HASH,
    "sales_revision": 9,
    "campaign_revision": 11,
    "contest_revision": 7,
}


class _AsyncpgRecordLike(dict[str, Any]):
    """Mirror asyncpg.Record iteration, which yields values rather than keys."""

    def __iter__(self):
        return iter(self.values())


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return False


def _source() -> PilotV2Source:
    return PilotV2Source(
        month="2026-08",
        cutoff=date(2026, 8, 11),
        sales_generation_hash=GENERATION_HASH,
        sales_revision=9,
        source_revision=19,
        campaign_revision=11,
        forecast_factor=Decimal("2"),
        daily_rows=(
            {
                "sale_date": date(2026, 8, 1),
                "site_code": "SITE",
                "agent": "A1",
                "total_sales": Decimal("100"),
            },
            {
                "sale_date": date(2026, 8, 2),
                "site_code": "SITE",
                "agent": "EXT",
                "total_sales": Decimal("50"),
            },
        ),
        store_rows=(
            {
                "site_code": "SITE",
                "locatie": "Magazin",
                "firma": "Mobiup",
                "regional": "Regional",
                "asm": "Manager",
            },
        ),
        targets={"SITE": Decimal("3100")},
        sim_quantities={("SITE", "A1"): 4},
        incentive_rows={
            ("SITE", "A1"): {
                "incentive_eligible_quantity": 12,
                "incentive_value": Decimal("50"),
                "incentive_potential": Decimal("100"),
                "status": "official",
            }
        },
    )


def _sheet() -> PilotV2Sheet:
    return PilotV2Sheet("SITE", "sheet", "A1", "Agent One", "A2", "Agent Two")


def test_store_totals_include_external_agent_sales() -> None:
    payload = _store_source(_source(), _sheet())

    assert payload["store_sales"] == Decimal("150")
    assert payload["store_forecast"] == Decimal("300")
    assert payload["daily_detail"][1][2] == "EXT"
    assert payload["daily_detail"][1][5] == Decimal("50")


def test_batch_preserves_manual_salary_cells_and_writes_markers() -> None:
    requests = _batch_requests(_source(), _sheet())
    config_updates = [
        request["updateCells"]
        for request in requests
        if "updateCells" in request
        and request["updateCells"].get("range", {}).get("sheetId") == 1137938031
        and request["updateCells"]["range"].get("startColumnIndex") == 13
    ]

    assert [(item["range"]["startRowIndex"], item["range"]["endRowIndex"]) for item in config_updates] == [
        (1, 11),
        (13, 26),
    ]
    assert _serial_day(date(2026, 8, 11)) == 46245
    extended_values = config_updates[1]["rows"]
    assert extended_values[2]["values"][1]["userEnteredValue"]["numberValue"] == 9
    assert extended_values[3]["values"][1]["userEnteredValue"]["numberValue"] == 11
    assert extended_values[12]["values"][1]["userEnteredValue"]["numberValue"] == 1

    sales_update = requests[0]["updateCells"]
    assert sales_update["range"]["endRowIndex"] == 5000

    header_values = requests[4]["updateCells"]["rows"][0]["values"]
    assert header_values[4]["userEnteredValue"]["numberValue"] == 3100
    assert header_values[13]["userEnteredValue"]["formulaValue"] == (
        "=$E$2/DAY(EOMONTH($C$2;0))*0,9"
    )
    assert header_values[15]["userEnteredValue"]["formulaValue"] == (
        "=$E$2/DAY(EOMONTH($C$2;0))"
    )


def test_sync_timestamp_uses_bucharest_wall_clock() -> None:
    serial = _serial_instant(datetime(2026, 8, 12, 12, tzinfo=timezone.utc))

    assert serial == _serial_day(date(2026, 8, 12)) + 15 / 24


def test_sales_revision_uses_record_keys_not_record_iteration() -> None:
    row = {
        "sale_date": date(2026, 8, 1),
        "site_code": "SITE",
        "agent": "A1",
        "total_sales": Decimal("100"),
    }

    assert _sales_source_revision(
        date(2026, 8, 11), Decimal("2"), (_AsyncpgRecordLike(row),)
    ) == _sales_source_revision(date(2026, 8, 11), Decimal("2"), (row,))


def test_snapshot_payload_uses_the_same_authoritative_source_as_google(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PILOT_V2_SHEETS", (_sheet(),))
    payload = _snapshot_payload(_source())

    assert payload["schema_version"] == 1
    assert payload["month"] == "2026-08"
    assert payload["cutoff"] == "2026-08-11"
    assert payload["sales_generation_hash"] == GENERATION_HASH
    assert payload["sales_revision"] == 9
    assert payload["source_revision"] == 19
    assert payload["stores"] == {
        "SITE": {"target": "3100", "realized": "150", "forecast": "300"}
    }


@pytest.mark.asyncio
async def test_sheet_state_requires_current_writer_schema() -> None:
    class Adapter:
        def __init__(self, writer_schema: int) -> None:
            self.writer_schema = writer_schema

        async def request(self, *_args, **_kwargs):
            return {
                "valueRanges": [
                    {"values": [[9]]},
                    {"values": [[11]]},
                    {"values": [[self.writer_schema]]},
                    {"values": [["VÂNZĂRI ZILNICE & INCENTIVE"]]},
                ]
            }

    current: Any = Adapter(1)
    stale: Any = Adapter(0)
    assert await _read_sheet_state(current, _sheet()) == (9, 11, True)
    assert await _read_sheet_state(stale, _sheet()) == (9, 11, False)


@pytest.mark.asyncio
async def test_sheet_state_falls_back_for_legacy_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = AsyncMock(
        side_effect=[
            RuntimeError("detail tab missing"),
            {
                "valueRanges": [
                    {"values": [[9]]},
                    {"values": [[11]]},
                    {"values": [[1]]},
                ]
            },
        ]
    )
    monkeypatch.setattr(sync_module, "call_with_backoff", request)

    assert await _read_sheet_state(MagicMock(), _sheet()) == (9, 11, False)
    assert request.await_count == 2
    assert request.await_args_list[1].args[1] == "read_values"


@pytest.mark.asyncio
async def test_load_source_uses_one_repeatable_read_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = MagicMock()
    connection.transaction.return_value = _AsyncContext(None)
    connection.fetchrow = AsyncMock(
        side_effect=[
            {"cutoff_date": date(2026, 8, 11)},
            {"generation_hash": GENERATION_HASH, "revision": 9},
            {"authority_head": "campaign:11", "authority_count": 1},
        ]
    )
    connection.fetch = AsyncMock(
        side_effect=[
            [
                {
                    "sale_date": date(2026, 8, 1),
                    "site_code": "SITE",
                    "agent": "A1",
                    "total_sales": Decimal("100"),
                }
            ],
            [
                {
                    "site_code": "SITE",
                    "locatie": "Magazin",
                    "firma": "Mobiup",
                    "regional": "Regional",
                    "asm": "Manager",
                }
            ],
            [{"site_code": "SITE", "target_value": Decimal("3100")}],
            [{"site_code": "SITE", "agent": "A1", "total_quantity": 4}],
            [
                {
                    "site_code": "SITE",
                    "agent": "A1",
                    "incentive_eligible_quantity": 12,
                    "incentive_value": Decimal("50"),
                    "incentive_potential": Decimal("100"),
                    "status": "official",
                }
            ],
        ]
    )
    pool = MagicMock()
    pool.acquire.return_value = _AsyncContext(connection)
    forecast = AsyncMock(return_value=Decimal("2"))
    monkeypatch.setattr(sync_module, "get_forecast_factor", forecast)

    source = await load_pilot_v2_source(pool, "2026-08")

    assert (source.cutoff, source.sales_generation_hash, source.sales_revision) == (
        date(2026, 8, 11),
        GENERATION_HASH,
        9,
    )
    assert 0 < source.source_revision < 2**48
    assert source.campaign_revision == 11
    assert source.forecast_factor == Decimal("2")
    assert source.targets == {"SITE": Decimal("3100")}
    assert source.sim_quantities == {("SITE", "A1"): 4}
    assert source.incentive_rows[("SITE", "A1")]["status"] == "official"
    connection.transaction.assert_called_once_with(
        isolation="repeatable_read",
        readonly=True,
    )
    forecast.assert_awaited_once_with(
        connection,
        "2026-08",
        cutoff_date=date(2026, 8, 11),
    )
    queries = [str(call.args[0]) for call in connection.fetchrow.await_args_list]
    queries.extend(str(call.args[0]) for call in connection.fetch.await_args_list)
    joined_queries = "\n".join(queries)
    assert all(
        relation in joined_queries
        for relation in (
            "reporting_sales_cutoff_v1",
            "retail_outbox_events",
            "reporting_campaign_month_v3",
        )
    )
    assert all("sales_generation_heads" not in query for query in queries)
    assert all("campaign_reporting_rows" not in query for query in queries)


def test_grile_worker_receives_only_required_reporting_reads() -> None:
    migration = Path(
        "db/migrations/067_grile_v2_operations_read_authority.sql"
    ).read_text()

    for relation in (
        "reporting_agent_day",
        "reporting_cartela_day",
        "ai_forecast_runs",
        "ai_forecast_store_day",
        "reporting_sales_cutoff_v1",
        "reporting_campaign_month_v3",
    ):
        assert relation in migration
    assert "TO unihub_operations" in migration
    assert "sales_generation_heads" not in migration
    assert "campaign_reporting_rows" not in migration
    outbox_migration = Path(
        "db/migrations/069_ai_cohort_and_transactional_outbox.sql"
    ).read_text()
    assert "GRANT SELECT ON TABLE retail_outbox_events TO unihub_operations" in outbox_migration


def test_grile_worker_can_execute_only_required_forecast_digest() -> None:
    migration = Path(
        "db/migrations/068_grile_v2_forecast_digest_authority.sql"
    ).read_text()

    assert (
        "GRANT EXECUTE ON FUNCTION public.planning_forecast_run_sha256(BIGINT)"
        in migration
    )
    assert "TO unihub_operations" in migration
    assert "GRANT SELECT" not in migration
    assert "planning_forecast_runs" not in migration
    assert "planning_forecast_store_day" not in migration


@pytest.mark.asyncio
async def test_load_source_rejects_non_pilot_month() -> None:
    with pytest.raises(ValueError, match="August 2026"):
        await load_pilot_v2_source(MagicMock(), "2026-09")


@pytest.mark.asyncio
async def test_campaign_lineage_guard_locks_and_classifies_exact_or_superseded() -> None:
    connection = MagicMock()
    connection.transaction.return_value = _AsyncContext(None)
    connection.fetchrow = AsyncMock(
        side_effect=[
            {"generation_hash": GENERATION_HASH, "revision": 9},
            {"generation_hash": NEXT_GENERATION_HASH, "revision": 10},
        ]
    )
    pool = MagicMock()
    pool.acquire.return_value = _AsyncContext(connection)

    async with guard_sales_generation_lineage(
        pool,
        month="2026-08",
        generation_hash=GENERATION_HASH,
        sales_revision=9,
    ) as exact_status:
        assert exact_status == "current"
    async with guard_sales_generation_lineage(
        pool,
        month="2026-08",
        generation_hash=GENERATION_HASH,
        sales_revision=9,
    ) as delayed_status:
        assert delayed_status == "superseded"

    assert all("FOR SHARE OF head" in call.args[0] for call in connection.fetchrow.await_args_list)


@pytest.mark.asyncio
async def test_campaign_lineage_guard_rejects_same_revision_hash_mismatch() -> None:
    connection = MagicMock()
    connection.transaction.return_value = _AsyncContext(None)
    connection.fetchrow = AsyncMock(
        return_value={"generation_hash": NEXT_GENERATION_HASH, "revision": 9}
    )
    pool = MagicMock()
    pool.acquire.return_value = _AsyncContext(connection)

    with pytest.raises(RuntimeError, match="hash differs"):
        async with guard_sales_generation_lineage(
            pool,
            month="2026-08",
            generation_hash=GENERATION_HASH,
            sales_revision=9,
        ):
            pytest.fail("mismatched lineage entered the publication fence")


@pytest.mark.asyncio
async def test_sync_skips_current_sheet_and_updates_stale_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = PilotV2Sheet("SITE", "current", "A1", "Agent One", "A2", "Agent Two")
    stale = PilotV2Sheet("SITE", "stale", "A1", "Agent One", "A2", "Agent Two")
    monkeypatch.setattr(sync_module, "PILOT_V2_SHEETS", (current, stale))
    monkeypatch.setattr(sync_module, "load_pilot_v2_source", AsyncMock(return_value=_source()))
    monkeypatch.setattr(
        sync_module,
        "_read_sheet_state",
        AsyncMock(side_effect=[(9, 11, True), (8, 11, True)]),
    )
    write = AsyncMock(return_value={})
    snapshot = AsyncMock()
    monkeypatch.setattr(sync_module, "call_with_backoff", write)
    monkeypatch.setattr(sync_module, "write_pilot_v2_snapshot", snapshot)

    result = await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)

    assert result["status"] == "completed"
    assert result["sales_generation_hash"] == GENERATION_HASH
    assert result["sales_generation_revision"] == 9
    assert result["campaign_revision"] == 11
    assert result["contest_revision"] == 7
    assert result["synced"] == ["SITE"]
    assert result["skipped"] == ["SITE"]
    assert result["failed"] == []
    assert result["cutoff"] == "2026-08-11"
    snapshot.assert_awaited_once()
    assert write.await_count == 1
    write_call = write.await_args
    assert write_call is not None
    assert write_call.args[1] == "batch_update"
    assert write_call.args[2]["spreadsheet_id"] == "stale"


@pytest.mark.asyncio
async def test_sync_reports_provider_failure_without_hiding_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PILOT_V2_SHEETS", (_sheet(),))
    monkeypatch.setattr(sync_module, "load_pilot_v2_source", AsyncMock(return_value=_source()))
    monkeypatch.setattr(
        sync_module,
        "_read_sheet_state",
        AsyncMock(return_value=(None, None, False)),
    )
    monkeypatch.setattr(
        sync_module,
        "call_with_backoff",
        AsyncMock(side_effect=RuntimeError("Google unavailable")),
    )
    snapshot = AsyncMock()
    monkeypatch.setattr(sync_module, "write_pilot_v2_snapshot", snapshot)

    with pytest.raises(RuntimeError, match="sync incomplete: SITE"):
        await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)

    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_delayed_generation_is_superseded_before_google_or_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = PilotV2Source(
        **{
            **_source().__dict__,
            "sales_generation_hash": NEXT_GENERATION_HASH,
            "sales_revision": 10,
        }
    )
    read_state = AsyncMock()
    google_write = AsyncMock()
    snapshot = AsyncMock()
    monkeypatch.setattr(sync_module, "load_pilot_v2_source", AsyncMock(return_value=source))
    monkeypatch.setattr(sync_module, "_read_sheet_state", read_state)
    monkeypatch.setattr(sync_module, "call_with_backoff", google_write)
    monkeypatch.setattr(sync_module, "write_pilot_v2_snapshot", snapshot)

    result = await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)

    assert result == {
        "status": "superseded",
        "month": "2026-08",
        "sales_generation_hash": GENERATION_HASH,
        "sales_generation_revision": 9,
        "campaign_revision": 11,
        "contest_revision": 7,
        "current_sales_generation_hash": NEXT_GENERATION_HASH,
        "current_sales_generation_revision": 10,
        "synced": [],
        "skipped": [],
        "failed": [],
    }
    read_state.assert_not_awaited()
    google_write.assert_not_awaited()
    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_revision_hash_mismatch_fails_before_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_state = AsyncMock()
    google_write = AsyncMock()
    snapshot = AsyncMock()
    monkeypatch.setattr(
        sync_module,
        "load_pilot_v2_source",
        AsyncMock(
            return_value=PilotV2Source(
                **{**_source().__dict__, "sales_generation_hash": NEXT_GENERATION_HASH}
            )
        ),
    )
    monkeypatch.setattr(sync_module, "_read_sheet_state", read_state)
    monkeypatch.setattr(sync_module, "call_with_backoff", google_write)
    monkeypatch.setattr(sync_module, "write_pilot_v2_snapshot", snapshot)

    with pytest.raises(RuntimeError, match="hash differs"):
        await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)

    read_state.assert_not_awaited()
    google_write.assert_not_awaited()
    snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_exact_retry_is_marker_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sync_module, "PILOT_V2_SHEETS", (_sheet(),))
    monkeypatch.setattr(sync_module, "load_pilot_v2_source", AsyncMock(return_value=_source()))
    monkeypatch.setattr(
        sync_module,
        "_read_sheet_state",
        AsyncMock(side_effect=[(8, 10, True), (9, 11, True)]),
    )
    google_write = AsyncMock(return_value={})
    snapshot = AsyncMock()
    monkeypatch.setattr(sync_module, "call_with_backoff", google_write)
    monkeypatch.setattr(sync_module, "write_pilot_v2_snapshot", snapshot)

    first = await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)
    second = await sync_pilot_v2_sheets(MagicMock(), MagicMock(), **LINEAGE)

    assert first["synced"] == ["SITE"]
    assert second["skipped"] == ["SITE"]
    assert google_write.await_count == 1
    assert snapshot.await_count == 2
