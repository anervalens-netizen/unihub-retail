"""Finite metric names for Campaigns observability."""

from __future__ import annotations

from typing import Literal

CampaignMetric = Literal["pool_wait", "db_load", "compute"]


def metric_name(metric: CampaignMetric) -> str:
    return f"campaign_{metric}_seconds"
