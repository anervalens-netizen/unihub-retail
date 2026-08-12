"""Authoritative Retail -> Google writer for the isolated Grile V2 pilot."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import logging
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from services.forecast import get_forecast_factor
from services.grile_monthly_google import GoogleSyncAdapter, call_with_backoff
from services.grile_monthly_integrity import secure_write_json
from services.grile_pilot_v2 import (
    PILOT_V2_SNAPSHOT_PATH,
    PILOT_V2_SNAPSHOT_SCHEMA_VERSION,
)
from services.grile_pilot_v2_registry import PILOT_V2_MONTH, PILOT_V2_SHEETS, PilotV2Sheet


logger = logging.getLogger(__name__)
_GOOGLE_TIMEOUT_SECONDS = 90.0
_SHEETS_EPOCH = date(1899, 12, 30)
_SUMMARY_SHEET_ID = 960600356
_LISTS_SHEET_ID = 1137938031
_DETAIL_SHEET_ID = 1874120601
_DETAIL_FIRST_ROW_INDEX = 10
_SALES_ROW_LIMIT = 4999
_WRITER_SCHEMA_VERSION = 1
_BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")


@dataclass(frozen=True)
class PilotV2Source:
    month: str
    cutoff: date
    sales_revision: int
    campaign_revision: int
    forecast_factor: Decimal
    daily_rows: tuple[Mapping[str, Any], ...]
    store_rows: tuple[Mapping[str, Any], ...]
    targets: Mapping[str, Decimal]
    sim_quantities: Mapping[tuple[str, str], int]
    incentive_rows: Mapping[tuple[str, str], Mapping[str, Any]]


def _serial_day(value: date) -> int:
    return (value - _SHEETS_EPOCH).days


def _serial_instant(value: datetime) -> float:
    local_value = value.astimezone(_BUCHAREST_TZ)
    return (local_value.date() - _SHEETS_EPOCH).days + (
        local_value.hour * 3600 + local_value.minute * 60 + local_value.second
    ) / 86400


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _sales_source_revision(
    cutoff: date,
    forecast_factor: Decimal,
    *row_groups: Iterable[Mapping[str, Any]],
) -> int:
    """Return a Sheets-safe fingerprint of every non-Campaigns input."""

    digest = hashlib.sha256()
    for header_value in (cutoff, forecast_factor):
        encoded = str(header_value).encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    for rows in row_groups:
        for row in rows:
            # asyncpg.Record iterates over values, unlike a normal Mapping.
            # Use its explicit key view so dates and strings are never sorted
            # against one another while producing the deterministic digest.
            for key in sorted(row.keys()):
                for cell_value in (key, row[key]):
                    encoded = str(
                        cell_value if cell_value is not None else ""
                    ).encode("utf-8")
                    digest.update(len(encoded).to_bytes(4, "big"))
                    digest.update(encoded)
    return int.from_bytes(digest.digest()[:6], "big")


def _google_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, date):
        return {"userEnteredValue": {"numberValue": _serial_day(value)}}
    if isinstance(value, (Decimal, int, float)):
        return {"userEnteredValue": {"numberValue": float(value)}}
    return {"userEnteredValue": {"stringValue": str(value)}}


_RO_WEEKDAYS = ("Lun", "Mar", "Mie", "Joi", "Vin", "Sâm", "Dum")


def _formula(value: str) -> dict[str, Any]:
    return {"userEnteredValue": {"formulaValue": value}}


def _rows(values: Iterable[Iterable[Any]]) -> list[dict[str, Any]]:
    return [{"values": [_google_value(value) for value in row]} for row in values]


async def load_pilot_v2_source(pool: Any, month: str) -> PilotV2Source:
    if month != PILOT_V2_MONTH:
        raise ValueError("Grile V2 sync is limited to the August 2026 pilot")
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            cutoff_row = await conn.fetchrow(
                """
                SELECT cutoff_date
                FROM reporting_sales_cutoff_v1
                WHERE import_month = $1
                """,
                month,
            )
            campaign_head = await conn.fetchrow(
                """
                SELECT MIN(authority_head) AS authority_head,
                       COUNT(DISTINCT authority_head)::INT AS authority_count
                FROM reporting_campaign_month_v3
                WHERE period = $1
                HAVING COUNT(*) > 0
                """,
                month,
            )
            if cutoff_row is None or cutoff_row["cutoff_date"] is None:
                raise RuntimeError("Authoritative sales cutoff is unavailable")
            if campaign_head is None:
                raise RuntimeError("Authoritative Campaigns projection is unavailable")
            authority_head = str(campaign_head["authority_head"] or "")
            if (
                int(campaign_head["authority_count"] or 0) != 1
                or not authority_head.startswith("campaign:")
            ):
                raise RuntimeError("Authoritative Campaigns revision is inconsistent")
            try:
                campaign_revision = int(authority_head.removeprefix("campaign:"))
            except ValueError as exc:
                raise RuntimeError("Authoritative Campaigns revision is invalid") from exc
            cutoff = cutoff_row["cutoff_date"]
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
            factor = Decimal(
                str(await get_forecast_factor(conn, month, cutoff_date=cutoff))
            )
            sales_revision = _sales_source_revision(
                cutoff,
                factor,
                daily_rows,
                store_rows,
                target_rows,
                sim_rows,
            )
    return PilotV2Source(
        month=month,
        cutoff=cutoff,
        sales_revision=sales_revision,
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
        "sales_revision": source.sales_revision,
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
            sheet_id=_LISTS_SHEET_ID,
            start_row=1,
            end_row=5000,
            start_column=0,
            end_column=4,
            rows=_rows(all_sales_rows),
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID,
            start_row=1,
            end_row=100,
            start_column=6,
            end_column=11,
            rows=_rows(store_rows),
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID,
            start_row=1,
            end_row=11,
            start_column=13,
            end_column=15,
            rows=base_config_rows,
        ),
        _range_update(
            sheet_id=_LISTS_SHEET_ID,
            start_row=13,
            end_row=26,
            start_column=13,
            end_column=15,
            rows=extended_config_rows,
        ),
        _summary_update(payload, target),
        _range_update(
            sheet_id=_DETAIL_SHEET_ID,
            start_row=_DETAIL_FIRST_ROW_INDEX,
            end_row=120,
            start_column=0,
            end_column=7,
            rows=_rows(daily_detail),
        ),
    ]


async def sync_pilot_v2_sheets(
    pool: Any,
    adapter: GoogleSyncAdapter,
    *,
    month: str = PILOT_V2_MONTH,
    force: bool = False,
) -> dict[str, Any]:
    source = await load_pilot_v2_source(pool, month)
    synced: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for sheet in PILOT_V2_SHEETS:
        try:
            sales_revision, campaign_revision, has_detail = await _read_sheet_state(adapter, sheet)
            if (
                not force
                and has_detail
                and sales_revision == source.sales_revision
                and campaign_revision == source.campaign_revision
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
        "month": month,
        "sales_revision": source.sales_revision,
        "campaign_revision": source.campaign_revision,
        "cutoff": source.cutoff.isoformat(),
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
    }
    if failed:
        raise RuntimeError(f"Grile V2 sync incomplete: {','.join(failed)}")
    await write_pilot_v2_snapshot(source)
    return result
