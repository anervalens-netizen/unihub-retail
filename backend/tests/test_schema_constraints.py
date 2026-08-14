from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from models import (
    ImportJobStatus,
    ImportResponse,
    StoreTargetInput,
    VisitMonthGroup,
    VisitReportRow,
)
from services.imports import _to_public_import_status
from services.jobs import JobResult, JobStatus
from schemas.agents import AgentEvaluationPeriod, AgentListItem, StoreCoverageItem


def test_month_contract_rejects_invalid_calendar_months() -> None:
    valid = ImportResponse(
        import_month="2026-12",
        rows_in_file=1,
        rows_imported=1,
        rows_filtered=0,
        store_count=1,
        agent_count=1,
        snapshot_id=1,
        filename="sales.xlsx",
        is_month_final=True,
    )
    assert valid.import_month == "2026-12"

    for invalid_month in ("2026-00", "2026-13", "26-01", "2026-1", "not-a-month"):
        with pytest.raises(ValidationError):
            ImportResponse(
                import_month=invalid_month,
                rows_in_file=1,
                rows_imported=1,
                rows_filtered=0,
                store_count=1,
                agent_count=1,
                snapshot_id=1,
                filename="sales.xlsx",
                is_month_final=True,
            )


def test_import_and_target_write_values_are_bounded() -> None:
    with pytest.raises(ValidationError):
        ImportResponse(
            import_month="2026-01",
            rows_in_file=-1,
            rows_imported=0,
            rows_filtered=0,
            store_count=0,
            agent_count=0,
            snapshot_id=1,
            filename="sales.xlsx",
            is_month_final=False,
        )

    for invalid_target in (Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(ValidationError):
            StoreTargetInput(
                site_code="S1",
                import_month="2026-01",
                target_value=invalid_target,
            )


def test_public_status_contracts_reject_unknown_values() -> None:
    with pytest.raises(ValidationError):
        ImportJobStatus.model_validate({"job_id": "job-1", "status": "running"})

    with pytest.raises(ValidationError):
        StoreCoverageItem.model_validate(
            {
                "site_code": "S1",
                "locatie": "Magazin",
                "firma": "Firma",
                "regional": "Regional",
                "asm": "ASM",
                "status": "unknown",
                "agent_count": 0,
            }
        )


def test_completed_sales_status_accepts_persisted_manifest_integrity_fields() -> None:
    result = _to_public_import_status(
        JobResult(
            job_id="sales-job-1",
            status=JobStatus.COMPLETE,
            result={
                "import_month": "2026-08",
                "rows_in_file": 1,
                "rows_imported": 1,
                "rows_filtered": 0,
                "store_count": 1,
                "agent_count": 1,
                "snapshot_id": 1,
                "filename": "sales.xlsx",
                "is_month_final": False,
                "manifest": {
                    "stage_rows_sha256": "a" * 64,
                    "parser_resources": {
                        "format": "xlsx",
                        "rows": 1,
                        "parse_seconds": 0.01,
                    },
                    "generation_state": "validated",
                },
            },
        )
    )

    assert result.result is not None
    assert result.result.manifest is not None
    assert result.result.manifest.stage_rows_sha256 == "a" * 64
    assert result.result.manifest.parser_resources == {
        "format": "xlsx",
        "rows": 1,
        "parse_seconds": 0.01,
    }


def test_completed_sales_status_ignores_internal_worker_fencing_fields() -> None:
    result = _to_public_import_status(
        JobResult(
            job_id="sales-job-1",
            status=JobStatus.COMPLETE,
            result={
                "import_month": "2026-08",
                "rows_in_file": 1,
                "rows_imported": 1,
                "rows_filtered": 0,
                "store_count": 1,
                "agent_count": 1,
                "snapshot_id": 1,
                "filename": "sales.xlsx",
                "is_month_final": False,
                "owner_id": "internal-only-fence-id",
            },
        )
    )

    assert result.result is not None
    assert result.result.snapshot_id == 1


@pytest.mark.parametrize(
    "invalid_percentage",
    [-0.01, 100.01, float("nan"), float("inf")],
)
def test_visit_percentages_are_finite_and_bounded(invalid_percentage: float) -> None:
    with pytest.raises(ValidationError):
        VisitReportRow(
            magazin="Magazin",
            asm=None,
            regional=None,
            firma=None,
            nr_vizite=1,
            avg_completion=invalid_percentage,
            curatenie_pct=100,
            imagine_pct=100,
            uniforma_pct=100,
            afise_pct=100,
            produse_promo_pct=100,
            last_visit=None,
        )

def test_openapi_schema_exposes_month_pattern_and_status_enums() -> None:
    import_schema = ImportResponse.model_json_schema()["properties"]
    assert import_schema["import_month"]["pattern"] == r"^\d{4}-(0[1-9]|1[0-2])$"
    assert ImportJobStatus.model_json_schema()["properties"]["status"]["enum"] == [
        "queued",
        "in_progress",
        "complete",
        "not_found",
    ]
    assert StoreCoverageItem.model_json_schema()["properties"]["status"]["enum"] == [
        "covered",
        "uncovered",
        "closed",
        "inactive",
    ]


@pytest.mark.parametrize("period", ["2026-07", "2025-01..curent", "custom"])
def test_agent_evaluation_period_accepts_api_labels(period: str) -> None:
    assert TypeAdapter(AgentEvaluationPeriod).validate_python(period) == period


@pytest.mark.parametrize(
    "period",
    ["2026-00", "2026-13", "2026-1", "2025-01..2026-07", "all", ""],
)
def test_agent_evaluation_period_rejects_unknown_labels(period: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(AgentEvaluationPeriod).validate_python(period)


def test_visit_month_group_accepts_explicit_undated_bucket() -> None:
    group = VisitMonthGroup(month="—", nr_vizite=1, days=[])
    assert group.month == "—"

    with pytest.raises(ValidationError):
        VisitMonthGroup(month="unknown", nr_vizite=1, days=[])
