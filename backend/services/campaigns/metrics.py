"""Finite metric names for Campaigns observability."""

from __future__ import annotations

from typing import Literal

from prometheus_client import Counter, Histogram

from services.campaigns.dates import CampaignDateRangeReason

CampaignMetric = Literal["pool_wait", "db_load", "compute"]

CAMPAIGN_REQUEST_REJECTED_TOTAL = Counter(
    "campaign_request_rejected_total",
    "Campaign requests rejected before execution.",
    ("reason",),
)
CAMPAIGN_POOL_WAIT_SECONDS = Histogram(
    "campaign_pool_wait_seconds",
    "Time spent waiting for the Campaigns database connection.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2),
)
CAMPAIGN_DB_LOAD_SECONDS = Histogram(
    "campaign_db_load_seconds",
    "Time spent materializing the immutable Campaigns database snapshot.",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3),
)
CAMPAIGN_COMPUTE_SECONDS = Histogram(
    "campaign_compute_seconds",
    "Time spent mapping a materialized Campaigns snapshot after releasing the pool connection.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
CAMPAIGN_DEADLINE_EXCEEDED_TOTAL = Counter(
    "campaign_deadline_exceeded_total",
    "Campaign requests that exhausted the request-wide deadline.",
    ("phase",),
)
_CAMPAIGN_DEADLINE_PHASES = frozenset({"pool_wait", "db_load", "compute"})
_CAMPAIGN_REQUEST_REJECTION_REASONS = frozenset(
    {
        "invalid_iso_date",
        "start_date_after_end_date",
        "cross_month_range_not_supported",
    }
)


def metric_name(metric: CampaignMetric) -> str:
    return f"campaign_{metric}_seconds"


def record_campaign_request_rejected(reason: CampaignDateRangeReason) -> None:
    """Record only the bounded range-policy reasons accepted by this metric."""
    if reason not in _CAMPAIGN_REQUEST_REJECTION_REASONS:
        raise ValueError("Unsupported campaign request rejection reason")
    CAMPAIGN_REQUEST_REJECTED_TOTAL.labels(reason=reason).inc()


def record_campaign_deadline_exceeded(phase: CampaignMetric) -> None:
    if phase not in _CAMPAIGN_DEADLINE_PHASES:
        raise ValueError("Unsupported campaign deadline phase")
    CAMPAIGN_DEADLINE_EXCEEDED_TOTAL.labels(phase=phase).inc()
