from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from db.connection import get_pool
from repositories.visits_report import VisitsReportRepository


def _month_bounds(month: str) -> tuple[date, date]:
    start = date.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def _wire_value(value: Any) -> Any:
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _wire_row(row: Any) -> dict[str, Any]:
    return {key: _wire_value(value) for key, value in dict(row).items()}


class VisitsReportPostgresRepository:
    """Async read repository for FieldOps-owned PostgreSQL visits."""

    def __init__(self, *, images_dir=None) -> None:
        self._report_helpers = VisitsReportRepository(images_dir=images_dir)

    async def query_report(
        self,
        month: str,
        *,
        store_metadata: dict[str, dict[str, str]],
        site_codes: list[str] | None,
    ) -> dict[str, Any]:
        month_start, month_end = _month_bounds(month)
        clauses = [
            "status <> 'draft'",
            "data_raport >= $1",
            "data_raport < $2",
        ]
        params: list[Any] = [month_start, month_end]
        if site_codes is not None:
            if not site_codes:
                clauses.append("FALSE")
            else:
                params.append(site_codes)
                clauses.append(f"magazin = ANY(${len(params)}::text[])")
        pool = await get_pool()
        async with pool.acquire() as connection:
            records = await connection.fetch(
                f"""
                SELECT magazin, asm, regional, firma, completion_pct,
                       curatenie, imagine, uniforma, afise, produse_promo,
                       data_raport
                FROM fieldops_visits
                WHERE {" AND ".join(clauses)}
                """,
                *params,
            )
        raw_rows = [_wire_row(record) for record in records]
        rows = self._report_helpers._aggregate_report_rows(raw_rows, store_metadata)
        total = len(raw_rows)
        completion_values = [float(row.get("completion_pct") or 0) for row in raw_rows]
        return {
            "total": total,
            "magazine_unice": len(
                {row.get("magazin") for row in raw_rows if row.get("magazin")}
            ),
            "avg_completion": (
                round(sum(completion_values) / total, 1) if total else 0.0
            ),
            "rows": rows,
        }

    async def query_tree(
        self,
        *,
        month: str | None = None,
        store_metadata: dict[str, dict[str, str]],
        site_codes: list[str] | None,
    ) -> list[dict[str, Any]]:
        clauses = ["status <> 'draft'"]
        params: list[Any] = []
        if month is not None:
            month_start, month_end = _month_bounds(month)
            params.extend([month_start, month_end])
            clauses.extend(["data_raport >= $1", "data_raport < $2"])
        if site_codes is not None:
            if not site_codes:
                clauses.append("FALSE")
            else:
                params.append(site_codes)
                clauses.append(f"magazin = ANY(${len(params)}::text[])")
        pool = await get_pool()
        async with pool.acquire() as connection:
            records = await connection.fetch(
                f"""
                SELECT id, data_raport, ora_trimitere, asm, team_leader_name,
                       magazin, firma, completion_pct, foto1, foto2, foto3, foto4
                FROM fieldops_visits
                WHERE {" AND ".join(clauses)}
                ORDER BY team_leader_name ASC, data_raport DESC, ora_trimitere DESC
                """,
                *params,
            )
        return [
            self._report_helpers._enrich_visit_row(_wire_row(record), store_metadata)
            for record in records
        ]

    async def query_visit(self, visit_id: str) -> dict[str, Any] | None:
        pool = await get_pool()
        async with pool.acquire() as connection:
            record = await connection.fetchrow(
                "SELECT * FROM fieldops_visits WHERE id = $1",
                visit_id,
            )
        if record is None:
            return None
        result = _wire_row(record)
        for field in (
            "created_by_sub",
            "last_sync_receipt_id",
            "migration_source_hash",
            "migrated_at",
        ):
            result.pop(field, None)
        return result
