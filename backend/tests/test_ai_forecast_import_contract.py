"""Fail-closed AI CSV import and persisted lineage contract."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

import asyncpg
import pytest

from scripts.import_ai_forecast import (
    ForecastImportLineage,
    import_forecast,
    load_lineage_manifest,
    validate_forecast_rows,
    validate_month_lineage,
    validate_row_counts,
)


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _lineage(**overrides: object) -> ForecastImportLineage:
    values: dict[str, object] = {
        "cohort_snapshot_id": uuid4(),
        "request_sha256": HASH_A,
        "raw_response_sha256": HASH_B,
        "response_sha256": HASH_C,
        "expected_pair_count": 2,
        "model_pair_count": 1,
        "fallback_pair_count": 1,
        "precision_loss_count": 0,
        "coverage_mode": "seasonal_fallback",
        "response_profile": "point_quantiles_v1",
    }
    values.update(overrides)
    return ForecastImportLineage(**values)  # type: ignore[arg-type]


def _rows() -> list[dict[str, str]]:
    return [
        {
            "target_month": "2026-09",
            "source_month": "2026-08",
            "site_code": "STORE-01",
            "forecast": "100.25",
            "method": "model_xreg",
        },
        {
            "target_month": "2026-09",
            "source_month": "2026-08",
            "site_code": "STORE-02",
            "forecast": "200.50",
            "method": "fallback_seasonal_last3",
        },
    ]


def _manifest_payload(lineage: ForecastImportLineage) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "targets": {
            "2026-09": {
                "cohort_snapshot_id": str(lineage.cohort_snapshot_id),
                "request_sha256": lineage.request_sha256,
                "raw_response_sha256": lineage.raw_response_sha256,
                "response_sha256": lineage.response_sha256,
                "expected_pair_count": lineage.expected_pair_count,
                "model_pair_count": lineage.model_pair_count,
                "fallback_pair_count": lineage.fallback_pair_count,
                "precision_loss_count": lineage.precision_loss_count,
                "coverage_mode": lineage.coverage_mode,
                "response_profile": lineage.response_profile,
            }
        },
    }


def test_valid_import_rows_and_lineage_counts_are_exact() -> None:
    rows = _rows()
    validate_forecast_rows(rows, metric="sales_value", horizon="current_month", anchor_month=None)
    validate_row_counts(rows, lineage=_lineage())


@pytest.mark.parametrize(
    ("mutation", "metric", "horizon", "anchor", "message"),
    [
        (lambda rows: rows[0].update(source_month=""), "sales_value", "current_month", None, "source_month"),
        (lambda rows: rows[1].update(site_code="STORE-01"), "sales_value", "current_month", None, "duplicata"),
        (lambda rows: rows[0].update(forecast="-1"), "sales_value", "current_month", None, "negativ"),
        (lambda rows: rows[0].update(forecast="NaN"), "sales_value", "current_month", None, "ne-finit"),
        (lambda rows: rows[0].update(forecast="1.5"), "units", "current_month", None, "integrale"),
        (lambda rows: rows[0].update(method=""), "sales_value", "current_month", None, "metoda"),
        (lambda rows: None, "sales_value", "rolling_12m", None, "anchor_month"),
    ],
)
def test_import_rows_reject_adversarial_inputs(
    mutation: Callable[[list[dict[str, str]]], None],
    metric: Literal["sales_value", "units"],
    horizon: str,
    anchor: str | None,
    message: str,
) -> None:
    rows = _rows()
    mutation(rows)
    with pytest.raises(RuntimeError, match=message):
        validate_forecast_rows(
            rows,
            metric=metric,
            horizon=horizon,
            anchor_month=anchor,
        )


def test_lineage_manifest_rejects_non_integer_and_unreconciled_counts(tmp_path: Path) -> None:
    lineage = _lineage()
    payload = _manifest_payload(lineage)
    target = payload["targets"]["2026-09"]
    target["expected_pair_count"] = True
    path = tmp_path / "lineage.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplet"):
        load_lineage_manifest(path)

    target["expected_pair_count"] = 3
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError, match="reconciliaza"):
        load_lineage_manifest(path)


def test_lineage_manifest_is_canonical_and_fail_closed_for_fallback(tmp_path: Path) -> None:
    lineage = _lineage(fallback_pair_count=0, model_pair_count=2, coverage_mode="fail_closed")
    path = tmp_path / "lineage.json"
    path.write_text(json.dumps(_manifest_payload(lineage), indent=2), encoding="utf-8")
    loaded, digest = load_lineage_manifest(path)
    assert loaded == {"2026-09": lineage}
    assert len(digest) == 64

    invalid = _manifest_payload(_lineage(coverage_mode="fail_closed"))
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(RuntimeError, match="nu permite fallback"):
        load_lineage_manifest(path)


class _FakeConnection:
    def __init__(self, *, snapshot: dict[str, object] | None, rows: list[dict[str, object]]) -> None:
        self.snapshot = snapshot
        self.rows = rows

    async def fetchrow(self, _query: str, _snapshot_id: UUID) -> dict[str, object] | None:
        return self.snapshot

    async def fetch(self, _query: str, _snapshot_id: UUID) -> list[dict[str, object]]:
        return self.rows


@pytest.mark.asyncio
async def test_month_lineage_rejects_unknown_store_and_uncertain_authority() -> None:
    lineage = _lineage()
    snapshot = {
        "source_month": "2026-08",
        "target_month": "2026-09",
        "expected_pair_count": 2,
        "state": "sealed",
    }
    cohort = [
        {"site_code": "STORE-01", "is_operating": True, "confidence": "confirmed"},
        {"site_code": "STORE-02", "is_operating": True, "confidence": "confirmed"},
    ]
    await validate_month_lineage(  # type: ignore[arg-type]
        _FakeConnection(snapshot=snapshot, rows=cohort),
        target_month="2026-09",
        rows=_rows(),
        lineage=lineage,
    )

    unknown_rows = _rows()
    unknown_rows[1]["site_code"] = "UNKNOWN"
    with pytest.raises(RuntimeError, match="exact perechile"):
        await validate_month_lineage(  # type: ignore[arg-type]
            _FakeConnection(snapshot=snapshot, rows=cohort),
            target_month="2026-09",
            rows=unknown_rows,
            lineage=lineage,
        )

    cohort[1]["confidence"] = "unknown"
    with pytest.raises(RuntimeError, match="ambigua"):
        await validate_month_lineage(  # type: ignore[arg-type]
            _FakeConnection(snapshot=snapshot, rows=cohort),
            target_month="2026-09",
            rows=_rows(),
            lineage=lineage,
        )


@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires isolated PostgreSQL with migration 069",
)
@pytest.mark.asyncio
async def test_import_persists_completed_run_only_with_exact_lineage(tmp_path: Path) -> None:
    suffix = uuid4().hex[:12]
    source_month = "2098-10"
    target_month = "2098-11"
    site_codes = [f"AC02-{suffix}-A", f"AC02-{suffix}-B"]
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await connection.executemany(
            """
            INSERT INTO stores (
                site_code, locatie, firma, regional, asm, is_active,
                first_seen_month, last_seen_month
            )
            VALUES ($1, 'contract-fixture', 'A', 'R', 'M', TRUE, $2, $2)
            ON CONFLICT (site_code) DO NOTHING
            """,
            [(site_code, source_month) for site_code in site_codes],
        )
        snapshot_id = await connection.fetchval(
            """
            INSERT INTO ai_forecast_cohort_snapshots (
                source_month, target_month, cutoff_at, source_generation,
                source_generation_sha256, authority_version, row_count,
                expected_pair_count
            ) VALUES ($1, $2, $3, $4, $5, 'historical_authority_v1', 2, 2)
            RETURNING id
            """,
            source_month,
            target_month,
            datetime(2098, 11, 1, tzinfo=timezone.utc),
            f"test-{suffix}",
            HASH_A,
        )
        await connection.executemany(
            """
            INSERT INTO ai_forecast_cohort_rows (
                snapshot_id, site_code, source_month, is_operating, firma,
                regional, asm, authority_source, confidence, source_generation,
                source_row_sha256, first_seen_month, last_seen_month
            ) VALUES ($1, $2, $3, TRUE, 'A', 'R', 'M',
                      'reporting_row+reporting_firma+org_assignment', 'confirmed',
                      $4, $5, $3, $3)
            """,
            [
                (snapshot_id, site_code, source_month, f"test-{suffix}", HASH_B)
                for site_code in site_codes
            ],
        )
        await connection.fetchrow("SELECT * FROM seal_ai_forecast_cohort_snapshot($1)", snapshot_id)
    finally:
        await connection.close()

    csv_path = tmp_path / "forecast.csv"
    csv_path.write_text(
        "target_month,source_month,site_code,forecast,method\n"
        f"{target_month},{source_month},{site_codes[0]},100.25,model_xreg\n"
        f"{target_month},{source_month},{site_codes[1]},200.50,fallback_seasonal_last3\n",
        encoding="utf-8",
    )
    lineage = _lineage(cohort_snapshot_id=snapshot_id)
    manifest_payload = _manifest_payload(lineage)
    manifest_payload["targets"] = {
        target_month: manifest_payload["targets"].pop("2026-09")
    }
    manifest_path = tmp_path / "lineage.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    args = argparse.Namespace(
        csv=str(csv_path),
        forecast_month=None,
        start_month=None,
        end_month=None,
        source_month=None,
        anchor_month=None,
        metric="sales_value",
        horizon="current_month",
        scenario="ac02-contract",
        mode="xreg + timesfm",
        variant=f"ac02-{suffix}",
        model_name=f"ac02-{suffix}",
        daily_profile_month=source_month,
        lineage_manifest=manifest_path,
        expected_lineage_sha256=None,
        replace=False,
    )
    run_id = await import_forecast(args)

    verification = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        run = await verification.fetchrow(
            """
            SELECT status, cohort_snapshot_id, expected_pair_count,
                   model_pair_count, fallback_pair_count, request_sha256,
                   raw_response_sha256, response_sha256, metadata
            FROM ai_forecast_runs WHERE id = $1
            """,
            run_id,
        )
        assert run is not None
        assert run["status"] == "completed"
        assert run["cohort_snapshot_id"] == snapshot_id
        assert (run["expected_pair_count"], run["model_pair_count"], run["fallback_pair_count"]) == (2, 1, 1)
        assert (run["request_sha256"], run["raw_response_sha256"], run["response_sha256"]) == (
            HASH_A,
            HASH_B,
            HASH_C,
        )
        assert await verification.fetchval(
            "SELECT count(*) FROM ai_forecast_store_month WHERE run_id = $1",
            run_id,
        ) == 2
        metadata = run["metadata"]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        assert metadata["imported_from"] == "forecast.csv" 
        assert str(tmp_path) not in json.dumps(run["metadata"])
    finally:
        await verification.close()
