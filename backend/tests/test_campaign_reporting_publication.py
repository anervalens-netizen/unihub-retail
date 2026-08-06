"""Static and unit checks for the immutable Campaigns publication contract."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import re

from services.campaign_reporting import _Store, _promo_agent_metrics, _row


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "db"
    / "migrations"
    / "053_insight_campaign_publication.sql"
)
SQL = MIGRATION.read_text(encoding="utf-8")
PUBLISHER = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "campaign_reporting.py"
).read_text(encoding="utf-8")


def _view_columns(view_name: str) -> tuple[str, ...]:
    match = re.search(
        rf"CREATE OR REPLACE VIEW {view_name} \((.*?)\)\s*WITH \(security_barrier = true\)",
        SQL,
        flags=re.DOTALL,
    )
    assert match, f"missing versioned security-barrier view {view_name}"
    return tuple(column.strip() for column in match.group(1).split(","))


def test_campaign_views_keep_explicit_agent_and_metric_contract() -> None:
    assert _view_columns("reporting_source_snapshot_v4") == (
        "domain",
        "period",
        "source",
        "source_generation",
        "authority",
        "authority_head",
        "contract_version",
        "rule_version",
        "status",
        "as_of",
        "cutoff",
        "is_final",
        "coverage_numerator",
        "coverage_denominator",
        "produced_at",
        "warnings",
    )
    assert _view_columns("reporting_campaign_month_v2") == (
        "period",
        "mechanism",
        "campaign_key",
        "site_code",
        "agent",
        "locatie",
        "firma",
        "regional",
        "asm",
        "actual_sales",
        "actual_quantity",
        "active_product_count",
        "active_product_codes",
        "promo_qualifying_bons",
        "promo_discounted_units",
        "promo_discount_value",
        "incentive_sold_quantity",
        "incentive_eligible_quantity",
        "incentive_qualified_quantity",
        "incentive_value",
        "incentive_potential",
        "incentive_store_qualified",
        "source",
        "source_generation",
        "authority",
        "authority_head",
        "contract_version",
        "rule_version",
        "status",
        "as_of",
        "cutoff",
        "is_final",
        "coverage_numerator",
        "coverage_denominator",
        "produced_at",
        "warnings",
    )
    assert "PRIMARY KEY (generation_id, mechanism, campaign_key, site_code, agent)" in SQL
    assert "active_product_count = cardinality(active_product_codes)" in SQL
    assert "campaign_reporting_product_codes_are_canonical" in SQL
    assert "row.agent" in SQL


def test_campaign_publication_is_append_only_cas_and_fails_closed_when_stale() -> None:
    assert "campaign reporting generations are append-only" in SQL
    assert "campaign reporting rows are append-only" in SQL
    assert "campaign reporting promotion ledger is append-only" in SQL
    assert "campaign reporting head accepts only a new generation and revision CAS advance" in SQL
    assert "pg_advisory_xact_lock" in SQL
    assert "p_expected_revision" in SQL
    assert "p_action NOT IN ('promote', 'rollback')" in SQL
    assert "campaign.reporting" not in SQL
    assert "campaign_reporting_not_published" in SQL
    assert "campaign.sales_source_generation = sales.source_generation" in SQL
    assert "reporting_source_snapshot_v3 AS snapshot\nWHERE snapshot.domain <> 'campaigns'" in SQL
    assert "CREATE OR REPLACE VIEW reporting_source_snapshot_v3" not in SQL
    assert "CREATE OR REPLACE VIEW reporting_campaign_month_v1" not in SQL


def test_publisher_reuses_canonical_evaluators_and_preserves_agent_totals() -> None:
    assert "_build_campaign_context(" in PUBLISHER
    assert "campaign_service.get_promotions_incentives(" in PUBLISHER
    assert "Pointerul promo s-a schimbat în timpul publicării" in PUBLISHER
    assert "Snapshotul sales s-a schimbat în timpul publicării" in PUBLISHER
    assert '"active_product_codes": normalized_product_codes' in PUBLISHER
    assert "def evaluate_promotion" not in PUBLISHER
    result = SimpleNamespace(
        excluded_units={
            ("S1", "Ana", "A"): 2,
            ("S1", "Ana", "B"): 1,
            ("S1", "Bogdan", "A"): 4,
        },
        excluded_discount_values={
            ("S1", "Ana", "A"): Decimal("10.00"),
            ("S1", "Ana", "B"): Decimal("5.00"),
            ("S1", "Bogdan", "A"): Decimal("20.00"),
        },
    )
    assert _promo_agent_metrics(result, site_code="S1", agent="Ana") == (
        3,
        3,
        Decimal("15.00"),
    )
    assert _promo_agent_metrics(result, site_code="S1", agent="Bogdan") == (
        4,
        4,
        Decimal("20.00"),
    )
    assert _promo_agent_metrics(None, site_code="S1", agent="Ana") == (
        None,
        None,
        None,
    )


def test_product_codes_are_sorted_deduplicated_and_counted_at_row_grain() -> None:
    row = _row(
        mechanism="incentive",
        campaign_key="incentive:5",
        site=_Store("S1", "Loc", "Mobiup", "R", "A"),
        agent="Ana",
        status="partial",
        active_product_codes=("P-2", "P-1", "P-2"),
    )
    assert row["active_product_codes"] == ["P-1", "P-2"]
    assert row["active_product_count"] == 2
