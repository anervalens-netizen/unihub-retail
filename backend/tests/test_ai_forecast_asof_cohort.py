"""Frozen temporal fixtures for historical AI cohort authority."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.ai_forecast_cohort import (
    ActivityEvent,
    CohortAuthorityError,
    OfficialTarget,
    OrgAssignment,
    ReportingObservation,
    authority_generation,
    resolution_sha256,
    resolve_asof_cohort,
    sanitized_resolution_manifest,
    source_month_cutoff,
)
from scripts.run_ai_forecast_xreg import fetch_asof_stores


CUTOFF = datetime(2026, 7, 31, 20, 59, 59, tzinfo=timezone.utc)


def report(site: str, *, firma: str = "Mobiup", total: str = "0") -> ReportingObservation:
    return ReportingObservation(site, "2026-07", firma, total)


def org(
    site: str,
    regional: str = "RM OLD",
    asm: str = "ASM OLD",
    start: str = "2026-01",
    end: str | None = "2026-07",
) -> OrgAssignment:
    return OrgAssignment(site, regional, asm, start, end)


def resolution(
    *,
    reporting=(),
    targets=(),
    events=(),
    assignments=(),
):
    return resolve_asof_cohort(
        source_month="2026-07",
        cutoff_at=CUTOFF,
        source_generation="sales-generation-2026-07",
        reporting=list(reporting),
        targets=list(targets),
        activity_events=list(events),
        org_assignments=list(assignments),
    )


def test_opened_after_cutoff_is_not_backdated_into_cohort() -> None:
    result = resolution(
        events=[ActivityEvent("OPEN-LATE", CUTOFF + timedelta(seconds=1), True)],
        assignments=[org("OPEN-LATE", start="2026-08", end=None)],
    )
    assert result.rows == ()
    assert result.excluded_after_cutoff == ("OPEN-LATE",)


def test_closed_after_cutoff_stays_operating_as_of_source_cutoff() -> None:
    result = resolution(
        reporting=[report("CLOSE-LATE", total="100")],
        events=[ActivityEvent("CLOSE-LATE", CUTOFF + timedelta(seconds=1), False)],
        assignments=[org("CLOSE-LATE")],
    )
    row = result.rows[0]
    assert row.site_code == "CLOSE-LATE"
    assert row.is_operating is True
    assert row.authority_source.startswith("reporting_row+")
    assert row.confidence == "confirmed"


def test_zero_sales_with_official_target_is_operating() -> None:
    result = resolution(
        reporting=[report("ZERO-TARGET", total="0")],
        targets=[OfficialTarget("ZERO-TARGET", "2026-07")],
        assignments=[org("ZERO-TARGET")],
    )
    row = result.rows[0]
    assert row.is_operating is True
    assert row.authority_source.startswith("official_target+")
    assert result.decision == "READY"


def test_missing_operating_authority_is_unknown_and_blocks() -> None:
    result = resolution(assignments=[org("NO-AUTHORITY")])
    row = result.rows[0]
    assert row.is_operating is None
    assert row.confidence == "unknown"
    assert result.blocked_site_codes == ("NO-AUTHORITY",)
    assert result.decision == "BLOCKED"


def test_current_org_is_never_used_for_historical_source_month() -> None:
    result = resolution(
        reporting=[report("ORG-CHANGE")],
        assignments=[
            org("ORG-CHANGE", "RM OLD", "ASM OLD", "2026-01", "2026-07"),
            org("ORG-CHANGE", "RM CURRENT", "ASM CURRENT", "2026-08", None),
        ],
    )
    row = result.rows[0]
    assert (row.regional, row.asm) == ("RM OLD", "ASM OLD")
    assert "CURRENT" not in str(sanitized_resolution_manifest(result))


def test_old_current_master_method_and_asof_method_have_frozen_delta() -> None:
    reporting = [report("STAY"), report("CLOSED")]
    result = resolution(
        reporting=reporting,
        events=[ActivityEvent("CLOSED", CUTOFF - timedelta(days=1), False)],
        assignments=[org("STAY"), org("CLOSED")],
    )
    asof_operating = {row.site_code for row in result.rows if row.is_operating is True}
    simulated_current_master = {"STAY", "OPEN-LATE"}
    assert asof_operating == {"STAY"}
    assert simulated_current_master - asof_operating == {"OPEN-LATE"}
    assert asof_operating - simulated_current_master == set()


def test_ambiguous_firm_or_org_is_auditable_and_blocked() -> None:
    result = resolution(
        reporting=[report("AMB", firma="Mobiup"), report("AMB", firma="Mobicell")],
        assignments=[org("AMB"), org("AMB", "RM 2", "ASM 2")],
    )
    row = result.rows[0]
    assert row.confidence == "ambiguous"
    assert row.firma is None and row.regional is None and row.asm is None
    assert result.decision == "BLOCKED"


def test_naive_cutoff_and_events_are_rejected() -> None:
    with pytest.raises(CohortAuthorityError, match="aware"):
        resolve_asof_cohort(
            source_month="2026-07",
            cutoff_at=datetime(2026, 7, 31),
            source_generation="generation",
            reporting=[],
            targets=[],
            activity_events=[],
            org_assignments=[],
        )
    with pytest.raises(CohortAuthorityError, match="aware"):
        resolution(events=[ActivityEvent("NAIVE", datetime(2026, 7, 1), True)])


def test_authority_generation_and_cohort_hash_are_order_independent() -> None:
    reports = [report("SECOND"), report("FIRST")]
    assignments = [org("SECOND"), org("FIRST")]
    first = authority_generation(
        source_month="2026-07",
        reporting=reports,
        targets=[],
        activity_events=[],
        org_assignments=assignments,
    )
    second = authority_generation(
        source_month="2026-07",
        reporting=list(reversed(reports)),
        targets=[],
        activity_events=[],
        org_assignments=list(reversed(assignments)),
    )
    assert first == second
    assert resolution_sha256(
        resolution(reporting=reports, assignments=assignments)
    ) == resolution_sha256(
        resolution(
            reporting=list(reversed(reports)),
            assignments=list(reversed(assignments)),
        )
    )
    assert source_month_cutoff("2026-07").astimezone(timezone.utc) == datetime(
        2026, 7, 31, 20, 59, 59, 999999, tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_backtest_store_loader_never_reads_current_store_master() -> None:
    class HistoricalConnection:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def fetch(self, query: str, *_args: object) -> list[dict[str, object]]:
            self.queries.append(query)
            if "reporting_agent_month" in query:
                return [
                    {
                        "site_code": "HIST",
                        "month": "2026-07",
                        "firma": "Mobiup",
                        "locatie": "Historical Store",
                        "total_sales": "100",
                    }
                ]
            if "store_org_assignments" in query:
                return [
                    {
                        "site_code": "HIST",
                        "regional": "RM OLD",
                        "asm": "ASM OLD",
                        "valid_from_month": "2026-01",
                        "valid_to_month": "2026-07",
                    }
                ]
            return []

    connection = HistoricalConnection()
    cohort = await fetch_asof_stores(  # type: ignore[arg-type]
        connection,
        source_month="2026-07",
        excluded_site_codes=[],
    )
    assert [(row.site_code, row.locatie, row.regional) for row in cohort.stores] == [
        ("HIST", "Historical Store", "RM OLD")
    ]
    assert len(cohort.cohort_sha256) == 64
    assert all("FROM stores\n" not in query for query in connection.queries)
