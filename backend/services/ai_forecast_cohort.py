"""Historical as-of cohort authority; never consults the current store master."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
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
    locatie: str = ""


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


def source_month_cutoff(source_month: str) -> datetime:
    """Return the last representable instant of a Bucharest business month."""
    source_month = _month(source_month)
    year, month = (int(part) for part in source_month.split("-"))
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=BUCHAREST)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=BUCHAREST)
    return next_month - timedelta(microseconds=1)


def authority_generation(
    *,
    source_month: str,
    reporting: Sequence[ReportingObservation],
    targets: Sequence[OfficialTarget],
    activity_events: Sequence[ActivityEvent],
    org_assignments: Sequence[OrgAssignment],
) -> tuple[str, str]:
    """Fingerprint only historical authority inputs, independent of row order."""
    source_month = _month(source_month)
    payload = {
        "source_month": source_month,
        "reporting": sorted(
            (row.site_code, row.month, row.firma, row.total_sales, row.locatie)
            for row in reporting
        ),
        "targets": sorted((row.site_code, row.month) for row in targets),
        "activity_events": sorted(
            (
                row.site_code,
                _aware(row.occurred_at).isoformat(),
                row.is_active,
            )
            for row in activity_events
        ),
        "org_assignments": sorted(
            (
                row.site_code,
                row.regional,
                row.asm,
                row.valid_from_month,
                row.valid_to_month or "",
            )
            for row in org_assignments
        ),
    }
    digest = _canonical_hash(payload)
    return f"asof-{source_month}-{digest[:32]}", digest


def _covers(assignment: OrgAssignment, month: str) -> bool:
    return assignment.valid_from_month <= month and (
        assignment.valid_to_month is None or month <= assignment.valid_to_month
    )


def _validate_authority_inputs(
    source_month: str,
    cutoff_at: datetime,
    reporting: Sequence[ReportingObservation],
    targets: Sequence[OfficialTarget],
    activity_events: Sequence[ActivityEvent],
    org_assignments: Sequence[OrgAssignment],
) -> tuple[str, datetime]:
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
    return source_month, cutoff_at


def _split_activity_by_cutoff(
    activity_events: Sequence[ActivityEvent],
    cutoff_at: datetime,
) -> tuple[list[ActivityEvent], set[str]]:
    eligible_events = [event for event in activity_events if event.occurred_at <= cutoff_at]
    after_cutoff_sites = {
        event.site_code
        for event in activity_events
        if event.occurred_at > cutoff_at
    }
    return eligible_events, after_cutoff_sites


def _record_evidence_seen(
    evidence_months: dict[str, list[str]],
    *,
    site_code: str,
    month: str,
    source_month: str,
) -> None:
    if month <= source_month:
        evidence_months.setdefault(site_code, []).append(month)


def _build_evidence_months(
    source_month: str,
    reporting: Sequence[ReportingObservation],
    targets: Sequence[OfficialTarget],
    eligible_events: Sequence[ActivityEvent],
    org_assignments: Sequence[OrgAssignment],
) -> dict[str, list[str]]:
    evidence_months: dict[str, list[str]] = {}
    for observation in reporting:
        _record_evidence_seen(
            evidence_months,
            site_code=observation.site_code,
            month=observation.month,
            source_month=source_month,
        )
    for target in targets:
        _record_evidence_seen(
            evidence_months,
            site_code=target.site_code,
            month=target.month,
            source_month=source_month,
        )
    for event in eligible_events:
        _record_evidence_seen(
            evidence_months,
            site_code=event.site_code,
            month=event.occurred_at.astimezone(BUCHAREST).strftime("%Y-%m"),
            source_month=source_month,
        )
    for assignment in org_assignments:
        if assignment.valid_from_month <= source_month:
            _record_evidence_seen(
                evidence_months,
                site_code=assignment.site_code,
                month=assignment.valid_from_month,
                source_month=source_month,
            )
            if _covers(assignment, source_month):
                _record_evidence_seen(
                    evidence_months,
                    site_code=assignment.site_code,
                    month=source_month,
                    source_month=source_month,
                )
    return evidence_months


def _applicable_events_for_site(
    site_code: str,
    eligible_events: Sequence[ActivityEvent],
) -> list[ActivityEvent]:
    return sorted(
        (event for event in eligible_events if event.site_code == site_code),
        key=lambda event: event.occurred_at,
    )


def _has_official_target(site_code: str, source_month: str, targets: Sequence[OfficialTarget]) -> bool:
    return any(
        target.site_code == site_code and target.month == source_month
        for target in targets
    )


def _source_reporting_for_site(
    site_code: str,
    source_month: str,
    reporting: Sequence[ReportingObservation],
) -> list[ReportingObservation]:
    return [
        observation
        for observation in reporting
        if observation.site_code == site_code and observation.month == source_month
    ]


def _resolve_operating_authority(
    *,
    applicable_events: Sequence[ActivityEvent],
    has_target: bool,
    source_reporting: Sequence[ReportingObservation],
) -> tuple[bool | None, str]:
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
    return is_operating, operating_source


def _covering_org_for_site(
    site_code: str,
    source_month: str,
    org_assignments: Sequence[OrgAssignment],
) -> list[OrgAssignment]:
    return [
        assignment
        for assignment in org_assignments
        if assignment.site_code == site_code and _covers(assignment, source_month)
    ]


def _resolve_firma(source_reporting: Sequence[ReportingObservation]) -> tuple[list[str], bool]:
    firms = sorted({item.firma for item in source_reporting if item.firma.strip()})
    return firms, len(firms) > 1


def _resolve_org_label(covering_org: Sequence[OrgAssignment]) -> tuple[str | None, str | None, bool]:
    if len(covering_org) == 1:
        return covering_org[0].regional, covering_org[0].asm, False
    if len(covering_org) > 1:
        return None, None, True
    return None, None, False


def _resolve_confidence(
    *,
    is_operating: bool | None,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    ambiguous: bool,
) -> Confidence:
    if ambiguous:
        return "ambiguous"
    if is_operating is not None and firma is not None and regional is not None and asm is not None:
        return "confirmed"
    return "unknown"


def _build_authority_source(
    *,
    operating_source: str,
    firma: str | None,
    covering_org: Sequence[OrgAssignment],
) -> str:
    firma_token = "reporting_firma" if firma is not None else "missing_firma"
    if len(covering_org) == 1:
        org_token = "org_assignment"
    elif len(covering_org) > 1:
        org_token = "ambiguous_org"
    else:
        org_token = "missing_org"
    return "+".join((operating_source, firma_token, org_token))


def _build_cohort_row(
    *,
    site_code: str,
    source_month: str,
    is_operating: bool | None,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    operating_source: str,
    covering_org: Sequence[OrgAssignment],
    confidence: Confidence,
    source_generation: str,
    first_seen_month: str,
    last_seen_month: str,
) -> CohortRow:
    authority_source = _build_authority_source(
        operating_source=operating_source,
        firma=firma,
        covering_org=covering_org,
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
        "first_seen_month": first_seen_month,
        "last_seen_month": last_seen_month,
    }
    return CohortRow(
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
        first_seen_month=first_seen_month,
        last_seen_month=last_seen_month,
    )


def _site_in_target_window(
    *,
    site_code: str,
    source_month: str,
    evidence_months: dict[str, list[str]],
) -> tuple[str, str] | None:
    months = evidence_months[site_code]
    first_seen = min(months)
    last_seen = max(months)
    if not first_seen <= source_month <= last_seen:
        return None
    return first_seen, last_seen


def _build_cohort_rows(
    source_month: str,
    *,
    reporting: Sequence[ReportingObservation],
    targets: Sequence[OfficialTarget],
    eligible_events: Sequence[ActivityEvent],
    org_assignments: Sequence[OrgAssignment],
    source_generation: str,
    evidence_months: dict[str, list[str]],
) -> list[CohortRow]:
    rows: list[CohortRow] = []
    for site_code in sorted(evidence_months):
        window = _site_in_target_window(
            site_code=site_code,
            source_month=source_month,
            evidence_months=evidence_months,
        )
        if window is None:
            continue
        first_seen, last_seen = window
        applicable_events = _applicable_events_for_site(site_code, eligible_events)
        has_target = _has_official_target(site_code, source_month, targets)
        source_reporting = _source_reporting_for_site(site_code, source_month, reporting)
        is_operating, operating_source = _resolve_operating_authority(
            applicable_events=applicable_events,
            has_target=has_target,
            source_reporting=source_reporting,
        )
        covering_org = _covering_org_for_site(site_code, source_month, org_assignments)
        firms, firma_ambiguous = _resolve_firma(source_reporting)
        firma = firms[0] if len(firms) == 1 else None
        regional, asm, org_ambiguous = _resolve_org_label(covering_org)
        confidence = _resolve_confidence(
            is_operating=is_operating,
            firma=firma,
            regional=regional,
            asm=asm,
            ambiguous=firma_ambiguous or org_ambiguous,
        )
        rows.append(
            _build_cohort_row(
                site_code=site_code,
                source_month=source_month,
                is_operating=is_operating,
                firma=firma,
                regional=regional,
                asm=asm,
                operating_source=operating_source,
                covering_org=covering_org,
                confidence=confidence,
                source_generation=source_generation,
                first_seen_month=first_seen,
                last_seen_month=last_seen,
            )
        )
    return rows


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
    source_month, cutoff_at = _validate_authority_inputs(
        source_month, cutoff_at, reporting, targets, activity_events, org_assignments,
    )
    eligible_events, after_cutoff_sites = _split_activity_by_cutoff(activity_events, cutoff_at)
    evidence_months = _build_evidence_months(
        source_month, reporting, targets, eligible_events, org_assignments,
    )
    rows = _build_cohort_rows(
        source_month,
        reporting=reporting,
        targets=targets,
        eligible_events=eligible_events,
        org_assignments=org_assignments,
        source_generation=source_generation,
        evidence_months=evidence_months,
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
        SELECT site_code, import_month AS month, firma, locatie,
               SUM(total_sales)::TEXT AS total_sales
        FROM reporting_agent_month
        WHERE import_month <= $1
        GROUP BY site_code, import_month, firma, locatie
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


def resolution_sha256(resolution: CohortResolution) -> str:
    """Stable cohort digest derived from sanitized row evidence."""
    return _canonical_hash(sanitized_resolution_manifest(resolution))
