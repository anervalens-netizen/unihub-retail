"""Historical as-of cohort authority; never consults the current store master."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Literal, Sequence
from uuid import UUID
from zoneinfo import ZoneInfo

import asyncpg


BUCHAREST = ZoneInfo("Europe/Bucharest")
Confidence = Literal["confirmed", "unknown", "ambiguous"]


class CohortAuthorityError(ValueError):
    """Historical authority is malformed or cannot be persisted safely."""


@dataclass(frozen=True, slots=True)
class ReportingObservation:
    site_code: str
    month: str
    firma: str
    total_sales: str


@dataclass(frozen=True, slots=True)
class OfficialTarget:
    site_code: str
    month: str


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    site_code: str
    occurred_at: datetime
    is_active: bool


@dataclass(frozen=True, slots=True)
class OrgAssignment:
    site_code: str
    regional: str
    asm: str
    valid_from_month: str
    valid_to_month: str | None


@dataclass(frozen=True, slots=True)
class CohortRow:
    site_code: str
    source_month: str
    is_operating: bool | None
    firma: str | None
    regional: str | None
    asm: str | None
    authority_source: str
    confidence: Confidence
    source_generation: str
    source_row_sha256: str
    first_seen_month: str
    last_seen_month: str


@dataclass(frozen=True, slots=True)
class CohortResolution:
    rows: tuple[CohortRow, ...]
    excluded_after_cutoff: tuple[str, ...]
    blocked_site_codes: tuple[str, ...]
    decision: Literal["READY", "BLOCKED"]


def _month(value: str) -> str:
    if len(value) != 7 or value[4] != "-":
        raise CohortAuthorityError("business month must use YYYY-MM")
    try:
        year, month = (int(part) for part in value.split("-"))
    except ValueError as exc:
        raise CohortAuthorityError("business month must use YYYY-MM") from exc
    if year < 2000 or not 1 <= month <= 12 or value != f"{year:04d}-{month:02d}":
        raise CohortAuthorityError("business month must use YYYY-MM")
    return value


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CohortAuthorityError("cohort cutoff and activity instants must be aware")
    return value


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _covers(assignment: OrgAssignment, month: str) -> bool:
    return assignment.valid_from_month <= month and (
        assignment.valid_to_month is None or month <= assignment.valid_to_month
    )


def resolve_asof_cohort(
    *,
    source_month: str,
    cutoff_at: datetime,
    source_generation: str,
    reporting: Sequence[ReportingObservation],
    targets: Sequence[OfficialTarget],
    activity_events: Sequence[ActivityEvent],
    org_assignments: Sequence[OrgAssignment],
) -> CohortResolution:
    source_month = _month(source_month)
    cutoff_at = _aware(cutoff_at)
    for observation in reporting:
        _month(observation.month)
    for target in targets:
        _month(target.month)
    for assignment in org_assignments:
        _month(assignment.valid_from_month)
        if assignment.valid_to_month is not None:
            _month(assignment.valid_to_month)
    for event in activity_events:
        _aware(event.occurred_at)

    eligible_events = [event for event in activity_events if event.occurred_at <= cutoff_at]
    after_cutoff_sites = {
        event.site_code
        for event in activity_events
        if event.occurred_at > cutoff_at
    }
    evidence_months: dict[str, list[str]] = {}

    def add_seen(site_code: str, month: str) -> None:
        if month <= source_month:
            evidence_months.setdefault(site_code, []).append(month)

    for observation in reporting:
        add_seen(observation.site_code, observation.month)
    for target in targets:
        add_seen(target.site_code, target.month)
    for event in eligible_events:
        add_seen(event.site_code, event.occurred_at.astimezone(BUCHAREST).strftime("%Y-%m"))
    for assignment in org_assignments:
        if assignment.valid_from_month <= source_month:
            add_seen(assignment.site_code, assignment.valid_from_month)
            if _covers(assignment, source_month):
                add_seen(assignment.site_code, source_month)

    rows: list[CohortRow] = []
    for site_code in sorted(evidence_months):
        months = evidence_months[site_code]
        first_seen = min(months)
        last_seen = max(months)
        if not first_seen <= source_month <= last_seen:
            continue

        applicable_events = sorted(
            (event for event in eligible_events if event.site_code == site_code),
            key=lambda event: event.occurred_at,
        )
        has_target = any(
            target.site_code == site_code and target.month == source_month
            for target in targets
        )
        source_reporting = [
            observation
            for observation in reporting
            if observation.site_code == site_code and observation.month == source_month
        ]
        operating_source = "missing_operating_authority"
        is_operating: bool | None = None
        if applicable_events:
            is_operating = applicable_events[-1].is_active
            operating_source = "activity_event"
        elif has_target:
            is_operating = True
            operating_source = "official_target"
        elif source_reporting:
            is_operating = True
            operating_source = "reporting_row"

        firms = sorted({item.firma for item in source_reporting if item.firma.strip()})
        covering_org = [
            assignment
            for assignment in org_assignments
            if assignment.site_code == site_code and _covers(assignment, source_month)
        ]
        ambiguous = len(firms) > 1 or len(covering_org) > 1
        firma = firms[0] if len(firms) == 1 else None
        regional = covering_org[0].regional if len(covering_org) == 1 else None
        asm = covering_org[0].asm if len(covering_org) == 1 else None
        confidence: Confidence = (
            "ambiguous"
            if ambiguous
            else "confirmed"
            if is_operating is not None and firma is not None and regional is not None and asm is not None
            else "unknown"
        )
        authority_source = "+".join(
            (
                operating_source,
                "reporting_firma" if firma is not None else "missing_firma",
                "org_assignment" if len(covering_org) == 1 else "ambiguous_org" if len(covering_org) > 1 else "missing_org",
            )
        )
        unhashed = {
            "site_code": site_code,
            "source_month": source_month,
            "is_operating": is_operating,
            "firma": firma,
            "regional": regional,
            "asm": asm,
            "authority_source": authority_source,
            "confidence": confidence,
            "source_generation": source_generation,
            "first_seen_month": first_seen,
            "last_seen_month": last_seen,
        }
        rows.append(
            CohortRow(
                site_code=site_code,
                source_month=source_month,
                is_operating=is_operating,
                firma=firma,
                regional=regional,
                asm=asm,
                authority_source=authority_source,
                confidence=confidence,
                source_generation=source_generation,
                source_row_sha256=_canonical_hash(unhashed),
                first_seen_month=first_seen,
                last_seen_month=last_seen,
            )
        )

    blocked = tuple(row.site_code for row in rows if row.confidence != "confirmed")
    included = {row.site_code for row in rows}
    return CohortResolution(
        rows=tuple(rows),
        excluded_after_cutoff=tuple(sorted(after_cutoff_sites - included)),
        blocked_site_codes=blocked,
        decision="BLOCKED" if blocked else "READY",
    )


async def fetch_asof_evidence(
    connection: asyncpg.Connection,
    *,
    source_month: str,
    cutoff_at: datetime,
) -> tuple[
    list[ReportingObservation],
    list[OfficialTarget],
    list[ActivityEvent],
    list[OrgAssignment],
]:
    """Read only historical authorities. The current `stores` table is absent by design."""
    reporting_rows = await connection.fetch(
        """
        SELECT site_code, import_month AS month, firma,
               SUM(total_sales)::TEXT AS total_sales
        FROM reporting_agent_month
        WHERE import_month <= $1
        GROUP BY site_code, import_month, firma
        """,
        source_month,
    )
    target_rows = await connection.fetch(
        """
        SELECT site_code, import_month AS month
        FROM store_targets
        WHERE import_month <= $1
        """,
        source_month,
    )
    activity_rows = await connection.fetch(
        """
        SELECT site_code, created_at AS occurred_at, new_is_active AS is_active
        FROM store_activity_events
        """,
    )
    org_rows = await connection.fetch(
        """
        SELECT site_code, regional, asm, valid_from_month, valid_to_month
        FROM store_org_assignments
        WHERE valid_from_month <= $1
        """,
        source_month,
    )
    return (
        [ReportingObservation(**dict(row)) for row in reporting_rows],
        [OfficialTarget(**dict(row)) for row in target_rows],
        [ActivityEvent(**dict(row)) for row in activity_rows],
        [OrgAssignment(**dict(row)) for row in org_rows],
    )


async def persist_asof_cohort_snapshot(
    connection: asyncpg.Connection,
    *,
    source_month: str,
    target_month: str,
    cutoff_at: datetime,
    source_generation: str,
    source_generation_sha256: str,
    authority_version: str = "historical_authority_v1",
) -> tuple[UUID, str, CohortResolution]:
    evidence = await fetch_asof_evidence(
        connection,
        source_month=source_month,
        cutoff_at=cutoff_at,
    )
    resolution = resolve_asof_cohort(
        source_month=source_month,
        cutoff_at=cutoff_at,
        source_generation=source_generation,
        reporting=evidence[0],
        targets=evidence[1],
        activity_events=evidence[2],
        org_assignments=evidence[3],
    )
    expected_pair_count = sum(
        row.confidence == "confirmed" and row.is_operating is True
        for row in resolution.rows
    )
    snapshot_id = await connection.fetchval(
        """
        INSERT INTO ai_forecast_cohort_snapshots (
            source_month, target_month, cutoff_at, source_generation,
            source_generation_sha256, authority_version, row_count,
            expected_pair_count
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        source_month,
        target_month,
        cutoff_at,
        source_generation,
        source_generation_sha256,
        authority_version,
        len(resolution.rows),
        expected_pair_count,
    )
    await connection.executemany(
        """
        INSERT INTO ai_forecast_cohort_rows (
            snapshot_id, site_code, source_month, is_operating, firma,
            regional, asm, authority_source, confidence, source_generation,
            source_row_sha256, first_seen_month, last_seen_month
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
        )
        """,
        [
            (
                snapshot_id,
                row.site_code,
                row.source_month,
                row.is_operating,
                row.firma,
                row.regional,
                row.asm,
                row.authority_source,
                row.confidence,
                row.source_generation,
                row.source_row_sha256,
                row.first_seen_month,
                row.last_seen_month,
            )
            for row in resolution.rows
        ],
    )
    sealed = await connection.fetchrow(
        "SELECT id, cohort_sha256 FROM seal_ai_forecast_cohort_snapshot($1)",
        snapshot_id,
    )
    if sealed is None:
        raise CohortAuthorityError("cohort snapshot seal returned no evidence")
    return UUID(str(sealed["id"])), str(sealed["cohort_sha256"]), resolution


def sanitized_resolution_manifest(resolution: CohortResolution) -> dict[str, object]:
    """Expose authority status and hashes, never organisation/person payloads."""
    return {
        "decision": resolution.decision,
        "row_count": len(resolution.rows),
        "blocked_site_codes": list(resolution.blocked_site_codes),
        "excluded_after_cutoff": list(resolution.excluded_after_cutoff),
        "rows": [
            {
                "site_code": row.site_code,
                "confidence": row.confidence,
                "authority_source": row.authority_source,
                "source_row_sha256": row.source_row_sha256,
                "first_seen_month": row.first_seen_month,
                "last_seen_month": row.last_seen_month,
            }
            for row in resolution.rows
        ],
    }
