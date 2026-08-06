from __future__ import annotations

import ast
from pathlib import Path

import services.campaigns as campaigns


BACKEND = Path(__file__).resolve().parents[1]
CAMPAIGN_SYMBOLS = {
    "CampaignContext",
    "compute_promotion_result",
    "fetch_promo_incentive_summary",
    "get_store_incentive_multipliers",
    "load_campaign_context",
}


def test_campaigns_exposes_one_public_cross_module_api() -> None:
    assert all(hasattr(campaigns, name) for name in CAMPAIGN_SYMBOLS)
    dashboard_queries = (BACKEND / "services/dashboard/queries.py").read_text(
        encoding="utf-8"
    )
    for legacy_name in (
        "DashboardCampaignContext",
        "_compute_dashboard_promotion_result",
        "_fetch_promo_incentive_summary",
        "_get_store_incentive_multipliers",
        "_load_dashboard_campaign_context",
    ):
        assert legacy_name not in dashboard_queries


def test_campaign_consumers_do_not_import_private_dashboard_campaign_helpers() -> None:
    targets = [
        BACKEND / "services/campaigns/__init__.py",
        BACKEND / "services/campaigns/context.py",
        BACKEND / "services/campaigns/summary.py",
        BACKEND / "services/dashboard/orchestration.py",
        BACKEND / "services/dashboard/specials_data.py",
        BACKEND / "services/exports/loaders.py",
        BACKEND / "services/exports/service.py",
        BACKEND / "services/erp_reconciliation.py",
    ]
    forbidden = {
        "DashboardCampaignContext",
        "_compute_dashboard_promotion_result",
        "_fetch_promo_incentive_summary",
        "_get_store_incentive_multipliers",
        "_load_dashboard_campaign_context",
    }
    for path in targets:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (forbidden & {alias.name for alias in node.names})


def test_campaign_reporting_has_no_service_construction_or_second_pool_lane() -> None:
    source = (BACKEND / "services/campaign_reporting.py").read_text(encoding="utf-8")
    assert "CampaignsService(" not in source
    assert "build_promotions_incentives_on_snapshot(" in source
