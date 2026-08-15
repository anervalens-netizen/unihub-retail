"""Authoritative Retail -> Google writer for the isolated Grile V2 pilot."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import logging
from typing import Any, Iterable, Mapping
from services.forecast import get_forecast_factor
from services.grile_monthly_google import GoogleSyncAdapter, call_with_backoff
from services.grile_monthly_integrity import secure_write_json
from services.grile_pilot_v2 import (
    PILOT_V2_SNAPSHOT_PATH,
    PILOT_V2_SNAPSHOT_SCHEMA_VERSION,
)
from services.grile_pilot_v2_registry import PILOT_V2_MONTH, PILOT_V2_SHEETS, PilotV2Sheet
from services.grile_pilot_v2_runtime import (
    _decimal,
    _formula,
    _google_value,
    _rows,
    _sales_source_revision,
    _serial_day,
    _serial_instant,
    _source_head_lineage,
)
logger = logging.getLogger(__name__)
_GOOGLE_TIMEOUT_SECONDS = 90.0
_SUMMARY_SHEET_ID = 960600356
_LISTS_SHEET_ID = 1137938031
_DETAIL_SHEET_ID = 1874120601
_DETAIL_FIRST_ROW_INDEX = 10
_SALES_ROW_LIMIT = 4999
_WRITER_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class PilotV2Source:
    month: str
    cutoff: date
    sales_generation_hash: str
    sales_revision: int
    source_revision: int
    campaign_revision: int
    forecast_factor: Decimal
    daily_rows: tuple[Mapping[str, Any], ...]
    store_rows: tuple[Mapping[str, Any], ...]
    targets: Mapping[str, Decimal]
    sim_quantities: Mapping[tuple[str, str], int]
    incentive_rows: Mapping[tuple[str, str], Mapping[str, Any]]


_RO_WEEKDAYS = ("Lun", "Mar", "Mie", "Joi", "Vin", "Sâm", "Dum")


@asynccontextmanager
async def guard_sales_generation_lineage(
    pool: Any,
    *,
    month: str,
    generation_hash: str,
    sales_revision: int,
) -> AsyncIterator[str]:
    """Fence campaign publication to one exact immutable sales head."""
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            SELECT snap.manifest_sha256 AS generation_hash, head.revision
            FROM sales_generation_heads AS head
            JOIN import_snapshots AS snap ON snap.id = head.snapshot_id
            WHERE head.import_month = $1
            FOR SHARE OF head
            """,
            month,
        )
        if row is None:
            raise RuntimeError("Authoritative sales generation is unavailable")
        current_hash = str(row["generation_hash"] or "")
        current_revision = int(row["revision"] or 0)
        if current_revision > sales_revision:
            yield "superseded"
            return
        if current_revision < sales_revision:
            raise RuntimeError("Requested sales generation is ahead of the head")
        if current_hash != generation_hash:
            raise RuntimeError("Sales generation hash differs at the same revision")
        yield "current"


async def load_pilot_v2_source(pool: Any, month: str) -> PilotV2Source:
    if month != PILOT_V2_MONTH:
        raise ValueError("Grile V2 sync is limited to the August 2026 pilot")
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            cutoff_row = await conn.fetchrow(
                """SELECT cutoff_date FROM reporting_sales_cutoff_v1
                   WHERE import_month = $1""",
                month,
            )
            sales_head = await conn.fetchrow(
                """SELECT generation_hash, revision FROM retail_outbox_events
                   WHERE event_type = 'retail.sales_generation_promoted.v1'
                     AND aggregate_type = 'sales_generation'
                     AND aggregate_id = 'sales-' || $1
                   ORDER BY aggregate_sequence DESC LIMIT 1""",
                month,
            )
            campaign_head = await conn.fetchrow(
                """SELECT MIN(authority_head) AS authority_head,
                       COUNT(DISTINCT authority_head)::INT AS authority_count
                FROM reporting_campaign_month_v3
                WHERE period = $1 HAVING COUNT(*) > 0""",
                month,
            )
            cutoff, sales_hash, sales_revision, campaign_revision = _source_head_lineage(
                cutoff_row, sales_head, campaign_head
            )
            daily_rows = await conn.fetch(
                """
                SELECT sale_date, site_code, agent, total_sales
                FROM reporting_agent_day
                WHERE import_month = $1 AND sale_date <= $2
                ORDER BY sale_date, site_code, agent
                """,
                month,
                cutoff,
            )
            store_rows = await conn.fetch(
                """
                SELECT site_code, locatie, firma, regional, asm
                FROM stores
                WHERE is_active = true
                ORDER BY asm, firma, locatie, site_code
                """
            )
            target_rows = await conn.fetch(
                """
                SELECT site_code, target_value
                FROM store_targets
                WHERE import_month = $1
                ORDER BY site_code
                """,
                month,
            )
            sim_rows = await conn.fetch(
                """
                SELECT site_code, agent, SUM(total_quantity)::BIGINT AS total_quantity
                FROM reporting_cartela_day
                WHERE import_month = $1 AND sale_date <= $2
                GROUP BY site_code, agent
                ORDER BY site_code, agent
                """,
                month,
                cutoff,
            )
            incentive_rows = await conn.fetch(
                """
                SELECT site_code, agent, incentive_eligible_quantity,
                       incentive_value, incentive_potential, status
                FROM reporting_campaign_month_v3
                WHERE period = $1
                  AND mechanism = 'incentive'
                  AND mechanism_variant = 'incentive'
                ORDER BY site_code, agent
                """,
                month,
            )
            factor = Decimal(str(await get_forecast_factor(conn, month, cutoff_date=cutoff)))
            source_revision = _sales_source_revision(
                cutoff, factor, daily_rows, store_rows, target_rows, sim_rows
            )
    return PilotV2Source(
        month=month,
        cutoff=cutoff,
        sales_generation_hash=sales_hash,
        sales_revision=sales_revision,
        source_revision=source_revision,
        campaign_revision=campaign_revision,
        forecast_factor=factor,
        daily_rows=tuple(dict(row) for row in daily_rows),
        store_rows=tuple(dict(row) for row in store_rows),
        targets={str(row["site_code"]): _decimal(row["target_value"]) for row in target_rows},
        sim_quantities={
            (str(row["site_code"]), str(row["agent"])): int(row["total_quantity"] or 0)
            for row in sim_rows
        },
        incentive_rows={
            (str(row["site_code"]), str(row["agent"])): dict(row)
            for row in incentive_rows
        },
    )


def _value_ranges(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    ranges = response.get("valueRanges", [])
    return list(ranges) if isinstance(ranges, list) else []


def _first_value(value_range: Mapping[str, Any]) -> Any:
    values = value_range.get("values")
    if isinstance(values, list) and values and isinstance(values[0], list) and values[0]:
        return values[0][0]
    return None


async def _read_sheet_state(
    adapter: GoogleSyncAdapter,
    sheet: PilotV2Sheet,
) -> tuple[int | None, int | None, bool]:
    request = {
        "spreadsheet_id": sheet.sheet_id,
        "ranges": [
            "'Liste'!O16",
            "'Liste'!O17",
            "'Liste'!O26",
            "'Vânzări & Incentive'!A1",
        ],
        "value_render_option": "UNFORMATTED_VALUE",
    }
    try:
        response = await call_with_backoff(
            adapter,
            "read_values",
            request,
            label=f"pilot-v2-state:{sheet.site_code}",
            deadline=asyncio.get_running_loop().time() + _GOOGLE_TIMEOUT_SECONDS,
        )
    except Exception:
        # Older pilot sheets do not have the detail tab until the redesigned
        # template is propagated. Keep their markers readable and force sync.
        response = await call_with_backoff(
            adapter,
            "read_values",
            {
                "spreadsheet_id": sheet.sheet_id,
                "ranges": ["'Liste'!O16", "'Liste'!O17", "'Liste'!O26"],
                "value_render_option": "UNFORMATTED_VALUE",
            },
            label=f"pilot-v2-legacy-state:{sheet.site_code}",
            deadline=asyncio.get_running_loop().time() + _GOOGLE_TIMEOUT_SECONDS,
        )
    ranges = _value_ranges(response)
    sales_revision = int(_first_value(ranges[0])) if len(ranges) > 0 and _first_value(ranges[0]) not in (None, "") else None
    campaign_revision = int(_first_value(ranges[1])) if len(ranges) > 1 and _first_value(ranges[1]) not in (None, "") else None
    writer_schema = int(_first_value(ranges[2])) if len(ranges) > 2 and _first_value(ranges[2]) not in (None, "") else None
    has_current_detail = bool(
        writer_schema == _WRITER_SCHEMA_VERSION
        and len(ranges) > 3
        and _first_value(ranges[3])
    )
    return sales_revision, campaign_revision, has_current_detail


def _store_source(source: PilotV2Source, sheet: PilotV2Sheet) -> dict[str, Any]:
    rows = [row for row in source.daily_rows if str(row["site_code"]) == sheet.site_code]
    if not rows:
        raise RuntimeError(f"No sales source for pilot site {sheet.site_code}")
    store_sales = sum((_decimal(row["total_sales"]) for row in rows), Decimal("0"))
    all_sales_rows = [
        (
            row["sale_date"],
            str(row["agent"]),
            str(row["site_code"]),
            _decimal(row["total_sales"]),
        )
        for row in source.daily_rows
    ]
    store = next(
        (row for row in source.store_rows if str(row["site_code"]) == sheet.site_code),
        None,
    )
    if store is None:
        raise RuntimeError(f"Store hierarchy missing for pilot site {sheet.site_code}")
    name_by_code = {
        sheet.agent_one_code: sheet.agent_one_name,
        sheet.agent_two_code: sheet.agent_two_name,
    }
    agent_cumulative: dict[str, Decimal] = {}
    daily_detail = []
    for row in rows:
        code = str(row["agent"])
        amount = _decimal(row["total_sales"])
        agent_cumulative[code] = agent_cumulative.get(code, Decimal("0")) + amount
        daily_detail.append(
            (
                row["sale_date"],
                _RO_WEEKDAYS[row["sale_date"].weekday()],
                name_by_code.get(code, code),
                code,
                amount,
                agent_cumulative[code],
                str(store["locatie"]),
            )
        )
    incentive_one = source.incentive_rows.get((sheet.site_code, sheet.agent_one_code), {})
    incentive_two = source.incentive_rows.get((sheet.site_code, sheet.agent_two_code), {})
    return {
        "all_sales_rows": all_sales_rows,
        "daily_detail": daily_detail,
        "store_sales": store_sales,
        "store_forecast": store_sales * source.forecast_factor,
        "store": store,
        "target": source.targets.get(sheet.site_code),
        "sim_one": source.sim_quantities.get((sheet.site_code, sheet.agent_one_code), 0),
        "sim_two": source.sim_quantities.get((sheet.site_code, sheet.agent_two_code), 0),
        "incentive_one": incentive_one,
        "incentive_two": incentive_two,
    }


def _store_lookup_rows(source: PilotV2Source) -> list[tuple[Any, ...]]:
    store_rows = []
    for row in source.store_rows:
        store_target = source.targets.get(str(row["site_code"]))
        daily_target = store_target / Decimal("31") if store_target is not None else None
        store_rows.append(
            (
                str(row["asm"] or row["regional"] or ""),
                str(row["firma"]),
                str(row["locatie"]),
                str(row["site_code"]),
                daily_target,
            )
        )
    if len(store_rows) > 99:
        raise RuntimeError("Pilot V2 store lookup exceeds the bounded Google range")
    return store_rows


def _snapshot_payload(source: PilotV2Source) -> dict[str, Any]:
    stores: dict[str, dict[str, str]] = {}
    for sheet in PILOT_V2_SHEETS:
        payload = _store_source(source, sheet)
        target = payload["target"]
        if target is None:
            raise RuntimeError(f"Target missing for pilot site {sheet.site_code}")
        stores[sheet.site_code] = {
            "target": str(target),
            "realized": str(payload["store_sales"]),
            "forecast": str(payload["store_forecast"]),
        }
    return {
        "schema_version": PILOT_V2_SNAPSHOT_SCHEMA_VERSION,
        "month": source.month,
        "cutoff": source.cutoff.isoformat(),
        "sales_generation_hash": source.sales_generation_hash,
        "sales_revision": source.sales_revision,
        "source_revision": source.source_revision,
        "campaign_revision": source.campaign_revision,
        "stores": stores,
    }


async def write_pilot_v2_snapshot(source: PilotV2Source) -> None:
    payload = _snapshot_payload(source)
    await asyncio.to_thread(secure_write_json, PILOT_V2_SNAPSHOT_PATH, payload)


def _range_update(
    *,
    sheet_id: int,
    start_row: int,
    end_row: int,
    start_column: int,
    end_column: int,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "updateCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_column,
                "endColumnIndex": end_column,
            },
            "rows": rows,
            "fields": "userEnteredValue",
        }
    }


def _config_rows(
    source: PilotV2Source,
    sheet: PilotV2Sheet,
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    incentive_one = payload["incentive_one"]
    incentive_two = payload["incentive_two"]
    synced_at = _serial_instant(datetime.now(timezone.utc))
    config_rows = (
        ("Ultima dată importată", source.cutoff),
        ("Firma locație curentă", str(payload["store"]["firma"])),
        ("Locație curentă", str(payload["store"]["locatie"])),
        ("Manager locație curentă", str(payload["store"]["asm"] or payload["store"]["regional"])),
        ("Cod Agent 1", sheet.agent_one_code),
        ("Cod Agent 2", sheet.agent_two_code),
        ("SIM Agent 1", payload["sim_one"]),
        ("SIM Agent 2", payload["sim_two"]),
        ("Incentive Agent 1", incentive_one.get("incentive_value")),
        ("Incentive Agent 2", incentive_two.get("incentive_value")),
        (None, None),  # O12 salary base is manual and must be preserved.
        (None, None),  # O13 meal vouchers are manual and must be preserved.
        ("Vânzări magazin", payload["store_sales"]),
        ("Forecast magazin", payload["store_forecast"]),
        ("Revizie sales", source.sales_revision),
        ("Revizie Campaigns", source.campaign_revision),
        ("Ultima sincronizare", synced_at),
        ("Status sync", "Sincronizat · raport oficial"),
        ("Nume Agent 1", sheet.agent_one_name),
        ("Nume Agent 2", sheet.agent_two_name),
        ("Potențial 100% Agent 1", incentive_one.get("incentive_potential")),
        ("Potențial 100% Agent 2", incentive_two.get("incentive_potential")),
        ("Unități eligibile Agent 1", incentive_one.get("incentive_eligible_quantity")),
        ("Unități eligibile Agent 2", incentive_two.get("incentive_eligible_quantity")),
        ("Revizie writer V2", _WRITER_SCHEMA_VERSION),
    )
    base_rows = [
        {"values": [_google_value(label), _google_value(value)]}
        for label, value in config_rows[:10]
    ]
    extended_rows = [
        {"values": [_google_value(label), _google_value(value)]}
        for label, value in config_rows[12:]
    ]
    return base_rows, extended_rows


def _summary_update(payload: Mapping[str, Any], target: Decimal) -> dict[str, Any]:
    return {
        "updateCells": {
            "start": {"sheetId": _SUMMARY_SHEET_ID, "rowIndex": 1, "columnIndex": 0},
            "rows": [
                {
                    "values": [
                        _google_value(f"{payload['store']['firma']} {payload['store']['locatie']}"),
                        {},
                        _google_value(date(2026, 8, 1)),
                        {},
                        _google_value(target),
                        {},
                        {},
                        _formula('=TEXT(Liste!$O$14;"#,##0")&" lei · "&TEXT(IFERROR(Liste!$O$14/E2;0);"0.0%")'),
                        {},
                        {},
                        _formula('=TEXT(Liste!$O$15;"#,##0")&" lei · "&TEXT(IFERROR(Liste!$O$15/E2;0);"0.0%")'),
                        {},
                        {},
                        _formula("=$E$2/DAY(EOMONTH($C$2;0))*0,9"),
                        {},
                        _formula("=$E$2/DAY(EOMONTH($C$2;0))"),
                        {},
                    ]
                }
            ],
            "fields": "userEnteredValue",
        }
    }


def _batch_requests(source: PilotV2Source, sheet: PilotV2Sheet) -> list[dict[str, Any]]:
    payload = _store_source(source, sheet)
    target = payload["target"]
    if target is None:
        raise RuntimeError(f"Target missing for pilot site {sheet.site_code}")
    all_sales_rows = payload["all_sales_rows"]
    if len(all_sales_rows) > _SALES_ROW_LIMIT:
        raise RuntimeError("Pilot V2 sales source exceeds the bounded Google range")
    daily_detail = payload["daily_detail"]
    if len(daily_detail) > 110:
        raise RuntimeError(f"Daily detail exceeds template capacity for {sheet.site_code}")
    store_rows = _store_lookup_rows(source)
    base_config_rows, extended_config_rows = _config_rows(source, sheet, payload)
    return [
        _range_update(
            sheet_id=_LISTS_SHEET_ID, start_row=1, end_row=5000,
            start_column=0, end_column=4, rows=_rows(all_sales_rows),
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID, start_row=1, end_row=100,
            start_column=6, end_column=11, rows=_rows(store_rows),
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID, start_row=1, end_row=11,
            start_column=13, end_column=15, rows=base_config_rows,
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID, start_row=13, end_row=26,
            start_column=13, end_column=15, rows=extended_config_rows,
        ),
        _summary_update(payload, target),
        _range_update(
            sheet_id=_DETAIL_SHEET_ID, start_row=_DETAIL_FIRST_ROW_INDEX, end_row=120,
            start_column=0, end_column=7, rows=_rows(daily_detail),
        ),
    ]


async def sync_pilot_v2_sheets(
    pool: Any,
    adapter: GoogleSyncAdapter,
    *,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
    month: str = PILOT_V2_MONTH,
    force: bool = False,
) -> dict[str, Any]:
    source = await load_pilot_v2_source(pool, month)
    lineage = {
        "sales_generation_hash": generation_hash,
        "sales_generation_revision": sales_revision,
        "campaign_revision": campaign_revision,
        "contest_revision": contest_revision,
    }
    if source.sales_revision > sales_revision:
        return {
            "status": "superseded",
            "month": month,
            **lineage,
            "current_sales_generation_hash": source.sales_generation_hash,
            "current_sales_generation_revision": source.sales_revision,
            "synced": [],
            "skipped": [],
            "failed": [],
        }
    if source.sales_revision < sales_revision:
        raise RuntimeError("Requested Grile V2 sales generation is ahead of the head")
    if source.sales_generation_hash != generation_hash:
        raise RuntimeError("Grile V2 sales generation hash differs at the same revision")
    if source.campaign_revision != campaign_revision:
        raise RuntimeError("Grile V2 Campaigns lineage differs from the requested revision")
    synced: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for sheet in PILOT_V2_SHEETS:
        try:
            sheet_sales_revision, sheet_campaign_revision, has_detail = (
                await _read_sheet_state(adapter, sheet)
            )
            if (
                not force
                and has_detail
                and sheet_sales_revision == source.sales_revision
                and sheet_campaign_revision == source.campaign_revision
            ):
                skipped.append(sheet.site_code)
                continue
            await call_with_backoff(
                adapter,
                "batch_update",
                {
                    "spreadsheet_id": sheet.sheet_id,
                    "requests": _batch_requests(source, sheet),
                },
                label=f"pilot-v2-write:{sheet.site_code}",
                destructive=True,
                deadline=asyncio.get_running_loop().time() + _GOOGLE_TIMEOUT_SECONDS,
            )
            synced.append(sheet.site_code)
        except Exception:
            failed.append(sheet.site_code)
            logger.exception("Grile V2 sync failed site=%s", sheet.site_code)
    result = {
        "status": "completed",
        "month": month,
        **lineage,
        "sales_revision": source.sales_revision,
        "source_revision": source.source_revision,
        "cutoff": source.cutoff.isoformat(),
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
    }
    if failed:
        raise RuntimeError(f"Grile V2 sync incomplete: {','.join(failed)}")
    await write_pilot_v2_snapshot(source)
    return result
