"""Static contracts for additive Campaigns v3, Contests v1 and Grile v1."""
from __future__ import annotations

import re
import json
import os
from pathlib import Path

import asyncpg
import pytest

ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "db" / "migrations" / "057_insight_contest_grile_campaign_v3.sql").read_text(
    encoding="utf-8"
)
PUBLISHER = (ROOT / "services" / "campaign_reporting.py").read_text(encoding="utf-8")
CONTEST_PUBLISHER = (ROOT / "services" / "contest_reporting.py").read_text(encoding="utf-8")


def _view_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\) WITH \(security_barrier = true\)",
        SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def test_v5_keeps_exact_source_snapshot_shape_and_versions_are_additive() -> None:
    assert _view_columns("reporting_source_snapshot_v5") == (
        "domain", "period", "source", "source_generation", "authority", "authority_head",
        "contract_version", "rule_version", "status", "as_of", "cutoff", "is_final",
        "coverage_numerator", "coverage_denominator", "produced_at", "warnings",
    )
    assert "reporting_source_snapshot_v4 WHERE domain <> 'campaigns'" in SQL
    assert "CREATE OR REPLACE VIEW reporting_campaign_month_v2" not in SQL
    assert "campaign-publication-v3" in SQL
    assert "campaign_variant_unpublished" in SQL


def test_campaign_variant_is_config_derived_and_pos_never_claims_receipts() -> None:
    assert '"mechanism_variant": mechanism_variant' in PUBLISHER
    assert '"same_model_screen_camera"' in PUBLISHER
    assert "receipt_identity_available" in PUBLISHER
    assert "promo_qualifying_bons_unavailable_pos_units_only" in PUBLISHER
    assert "discounted_units if receipt_identity_available else None" in PUBLISHER
    assert "ALTER FUNCTION public.publish_campaign_reporting_generation" in SQL
    assert "publish_campaign_reporting_generation_v2" in SQL


def test_contest_contract_is_immutable_canonical_and_no_active_month_is_explicit() -> None:
    assert "class ContestReportingPublisher" in CONTEST_PUBLISHER
    assert "ContestsService(" in CONTEST_PUBLISHER
    assert "contest reporting generations are append-only" in SQL
    assert "contest reporting promotion ledger is append-only" in SQL
    assert "contest_config_sha256" in SQL
    assert "contest_metadata JSONB NOT NULL" in SQL
    assert "identity_policy" in SQL
    assert "qualifying_sales" not in SQL
    assert "qualifying_quantity" not in SQL
    assert "score BIGINT" not in SQL
    assert "no_active_contest" in CONTEST_PUBLISHER
    assert "contest_promo_points_derive_from_units_not_receipts" in CONTEST_PUBLISHER


def test_grile_contract_uses_current_fenced_projection_and_domain_metadata() -> None:
    columns = _view_columns("reporting_grile_month_v1")
    assert "source_run_id" in columns
    assert "generation" in columns
    assert "coverage_numerator" in columns
    assert "grile_store_current_status_fence" in SQL
    assert "grile-current-fenced-v1" in SQL
    assert "grile_current_fenced_projection_not_month_final" in SQL
    assert "grile_last_error:" in SQL


def test_reader_and_publisher_privileges_remain_narrow() -> None:
    assert "GRANT SELECT (agent_code, site_code, match_status, effective_from_month, person_id)" in SQL
    assert "TO unihub_sales_import" in SQL
    assert "FROM unihub_sales_import" in SQL
    assert "publish_campaign_reporting_generation_v2" in SQL
    assert "reporting_source_snapshot_v5, reporting_campaign_month_v3" in SQL
    assert "ALL TABLES" not in SQL
    assert "GRANT SELECT ON TABLE contest_reporting_rows TO unihub_insight_reader" not in SQL


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("UNIHUB_TEST_DATABASE") != "1",
    reason="requires the isolated PostgreSQL contract database",
)
async def test_contest_publisher_is_idempotent_and_keeps_empty_month_explicit() -> None:
    connection = await asyncpg.connect(os.environ["DATABASE_URL"])
    call = """
        SELECT generation_id, revision
        FROM public.publish_contest_reporting_generation(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
            $13, $14::JSONB, $15::JSONB, $16, $17, $18, $19
        )
    """
    try:
        args = (
            "2098-01", "sales:test", "sales_generation_head", "1", "official", True,
            "a" * 64, None, 1, 1, "unavailable", ["no_active_contest"], "b" * 64,
            json.dumps([]), json.dumps([]), 0, "test:contest", "empty canonical contest", "promote",
        )
        first = await connection.fetchrow(call, *args)
        assert first is not None
        assert (first["generation_id"], first["revision"]) == (1, 1)
        duplicate = await connection.fetchrow(call, *args)
        assert duplicate == first
        assert await connection.fetchval(
            "SELECT row_count FROM contest_reporting_generations WHERE id = $1",
            first["generation_id"],
        ) == 0
        assert await connection.fetchval(
            "SELECT status FROM contest_reporting_generations WHERE id = $1",
            first["generation_id"],
        ) == "unavailable"
        assert await connection.fetchval(
            "SELECT COUNT(*) FROM contest_reporting_promotions WHERE period = '2098-01'"
        ) == 1
        with pytest.raises(asyncpg.PostgresError, match="head revision conflict"):
            changed = (*args[:12], "c" * 64, *args[13:15], 0, *args[16:])
            await connection.fetchrow(call, *changed)
    finally:
        await connection.close()
