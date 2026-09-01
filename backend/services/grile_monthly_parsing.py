"""Pure parsing and coverage policy for monthly Grile rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.grile_monthly_integrity import (
    MonthlyIntegrityError,
    decimal_text,
    finalize_manifest,
    parse_required_decimal,
)
from services.grile_monthly_types import (
    ExtractedAgentRow,
    StoreEntry,
    cells_for_entry,
)


def value_ranges_for_entry(entry: StoreEntry) -> list[str]:
    ranges: list[str] = []
    for cells in cells_for_entry(entry).values():
        ranges.extend(
            [
                f"Grila!{cells['agent']}",
                f"Grila!{cells['base_salary']}",
                *[f"Grila!{cell}" for cell in cells["sales_commission_cells"]],
                f"Grila!{cells['extra_location_commission']}",
                f"Grila!{cells['extra_hours_pay']}",
                f"Grila!{cells['bonuri']}",
                cells["worked_hours"],
            ]
        )
    return ranges


def scalar(values: list[list[Any]]) -> Any:
    if not values or not values[0]:
        return ""
    return values[0][0]


def to_number(value: Any, *, field: str = "value") -> float:
    return float(parse_required_decimal(value, field=field))


def sum_scalars(value_ranges: list[dict[str, Any]], *, field: str = "value") -> float:
    values = (scalar(value_range.get("values", [])) for value_range in value_ranges)
    return float(
        sum(
            (
                Decimal("0")
                if value in (None, "")
                else parse_required_decimal(value, field=field)
                for value in values
            ),
            start=Decimal("0"),
        )
    )


def error_row(
    entry: StoreEntry,
    *,
    slot: int,
    code: str,
    field: str = "",
) -> ExtractedAgentRow:
    return ExtractedAgentRow(
        site_code=entry.site_code,
        company=entry.company,
        store=entry.store,
        slot=slot,
        agent="",
        base_salary="",
        sales_commission="",
        extra_location_commission="",
        extra_hours_pay="",
        bonuri="",
        worked_hours="",
        status="ERROR",
        error_code=code,
        error=code,
        sheet_id=entry.sheet_id,
        error_field=field,
    )


def _closed_empty_slot(entry: StoreEntry, agent: Any, slot_values: list[Any]) -> bool:
    if not entry.is_closed or agent not in (None, ""):
        return False
    work_values = [*slot_values[2:9], slot_values[10]]
    return all(value in (None, "", 0, 0.0, False) for value in work_values)


def _valid_agent(agent: Any) -> bool:
    return (
        isinstance(agent, str)
        and bool(agent.strip())
        and all(ord(char) >= 32 and ord(char) != 127 for char in agent)
    )


def _empty_slot(slot_values: list[Any]) -> bool:
    return slot_values[0] in (None, "") and all(
        value in (None, "", 0, 0.0, False) for value in slot_values[1:]
    )


def _parsed_row(
    entry: StoreEntry,
    slot: int,
    slot_ranges: list[dict[str, Any]],
    slot_values: list[Any],
) -> ExtractedAgentRow:
    agent = slot_values[0]
    if not _valid_agent(agent):
        return error_row(entry, slot=slot, code="missing_or_invalid_agent")
    try:
        values = _numeric_slot_values(slot_ranges, slot_values)
    except MonthlyIntegrityError as exc:
        field = ""
        suffix = " is not a valid number"
        message = str(exc)
        if exc.code == "invalid_numeric_value" and message.endswith(suffix):
            field = message[: -len(suffix)]
        return error_row(entry, slot=slot, code=exc.code, field=field)
    return ExtractedAgentRow(
        site_code=entry.site_code,
        company=entry.company,
        store=entry.store,
        slot=slot,
        agent=agent.strip(),
        base_salary=values[0],
        sales_commission=values[1],
        extra_location_commission=values[2],
        extra_hours_pay=values[3],
        bonuri=values[4],
        worked_hours=values[5],
        status="OK",
        error_code="",
        error="",
        sheet_id=entry.sheet_id,
    )


def _numeric_slot_values(
    slot_ranges: list[dict[str, Any]],
    slot_values: list[Any],
) -> tuple[float, float, float, float, float, float]:
    return (
        to_number(slot_values[1], field="base_salary"),
        sum_scalars(slot_ranges[2:7], field="sales_commission"),
        to_number(slot_values[7], field="extra_location_commission"),
        to_number(slot_values[8], field="extra_hours_pay"),
        to_number(slot_values[9], field="meal_vouchers"),
        to_number(slot_values[10], field="worked_hours"),
    )


def _deduplicate_agents(
    entry: StoreEntry,
    rows: list[ExtractedAgentRow],
) -> list[ExtractedAgentRow]:
    seen_agents: set[str] = set()
    result: list[ExtractedAgentRow] = []
    for row in rows:
        normalized = str(row.agent).strip().casefold()
        if row.status == "OK" and normalized in seen_agents:
            result.append(error_row(entry, slot=row.slot, code="duplicate_agent"))
        else:
            if row.status == "OK":
                seen_agents.add(normalized)
            result.append(row)
    return result


def parse_store_rows(
    entry: StoreEntry,
    value_ranges: list[dict[str, Any]],
) -> list[ExtractedAgentRow]:
    rows: list[ExtractedAgentRow] = []
    for offset, slot in enumerate(cells_for_entry(entry)):
        slot_ranges = value_ranges[offset * 11 : (offset + 1) * 11]
        slot_values = [scalar(item.get("values", [])) for item in slot_ranges]
        if _empty_slot(slot_values) or _closed_empty_slot(entry, slot_values[0], slot_values):
            continue
        rows.append(_parsed_row(entry, slot, slot_ranges, slot_values))
    if not rows:
        return [] if entry.is_closed else [error_row(entry, slot=0, code="store_has_no_agent")]
    return _deduplicate_agents(entry, rows)


def finalization_coverage(
    entries: list[StoreEntry],
    rows: list[ExtractedAgentRow],
) -> tuple[int, int, int, int, list[str]]:
    entries_by_site, errors = _index_entries(entries)
    rows_by_site = _index_rows(entries_by_site, rows, errors)
    expected_agents = processed_agents = processed_stores = 0
    for site_code, entry in entries_by_site.items():
        expected, processed, completed = _store_coverage(
            entry,
            rows_by_site.get(site_code, []),
            errors,
        )
        expected_agents += expected
        processed_agents += processed
        processed_stores += int(completed)
    return (
        len(entries_by_site),
        processed_stores,
        expected_agents,
        processed_agents,
        sorted(set(errors)),
    )


def _index_entries(
    entries: list[StoreEntry],
) -> tuple[dict[str, StoreEntry], list[str]]:
    entries_by_site: dict[str, StoreEntry] = {}
    sheet_ids: set[str] = set()
    errors: list[str] = []
    for entry in entries:
        if entry.site_code in entries_by_site or entry.sheet_id in sheet_ids:
            errors.append("duplicate_registry_entry")
        entries_by_site[entry.site_code] = entry
        sheet_ids.add(entry.sheet_id)
    return entries_by_site, errors


def _index_rows(
    entries_by_site: dict[str, StoreEntry],
    rows: list[ExtractedAgentRow],
    errors: list[str],
) -> dict[str, list[ExtractedAgentRow]]:
    rows_by_site: dict[str, list[ExtractedAgentRow]] = {}
    for row in rows:
        expected = entries_by_site.get(row.site_code)
        if expected is None:
            errors.append("unexpected_store")
            continue
        if (row.sheet_id, row.company, row.store) != (
            expected.sheet_id,
            expected.company,
            expected.store,
        ):
            errors.append("contradictory_store_metadata")
        rows_by_site.setdefault(row.site_code, []).append(row)
    return rows_by_site


def _store_coverage(
    entry: StoreEntry,
    store_rows: list[ExtractedAgentRow],
    errors: list[str],
) -> tuple[int, int, bool]:
    if not store_rows and entry.is_closed:
        return 0, 0, True
    slot_rows = [row for row in store_rows if row.slot in cells_for_entry(entry)]
    valid_rows = [row for row in slot_rows if row.status == "OK"]
    store_errors = [
        row.error_code or "store_read_failed" for row in store_rows if row.status != "OK"
    ]
    if not store_rows:
        store_errors.append("store_not_processed")
    if not slot_rows:
        store_errors.append("store_has_no_agent")
    normalized_agents = {str(row.agent).strip().casefold() for row in valid_rows}
    if len(normalized_agents) != len(valid_rows):
        store_errors.append("duplicate_agent")
    errors.extend(store_errors)
    return len(slot_rows), len(valid_rows), not store_errors


def control_totals(rows: list[ExtractedAgentRow]) -> dict[str, str]:
    fields = (
        "base_salary",
        "sales_commission",
        "extra_location_commission",
        "extra_hours_pay",
        "bonuri",
        "worked_hours",
    )
    valid_rows = [row for row in rows if row.status == "OK"]
    totals = {
        field: decimal_text(
            sum(
                (Decimal(str(getattr(row, field))) for row in valid_rows),
                start=Decimal("0"),
            )
        )
        for field in fields
    }
    totals["salary_components"] = decimal_text(
        sum((_salary_components(row) for row in valid_rows), start=Decimal("0"))
    )
    return totals


def _salary_components(row: ExtractedAgentRow) -> Decimal:
    return sum(
        (
            Decimal(str(row.base_salary)),
            Decimal(str(row.sales_commission)),
            Decimal(str(row.extra_location_commission)),
            Decimal(str(row.extra_hours_pay)),
            Decimal(str(row.bonuri)),
        ),
        start=Decimal("0"),
    )


def source_registry(entries: list[StoreEntry]) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "site_code": entry.site_code,
                "sheet_id": entry.sheet_id,
                "template_version": entry.template_version,
            }
            for entry in entries
        ),
        key=lambda item: (item["site_code"], item["sheet_id"]),
    )


def with_source_registry(
    manifest: dict[str, Any],
    entries: list[StoreEntry],
) -> dict[str, Any]:
    enriched = dict(manifest)
    enriched["source_registry"] = source_registry(entries)
    return finalize_manifest(enriched)
