"""Shared row shapes and serializers for monthly Grile persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

import asyncpg


OPERATION_COLUMNS = """
    id, op, closing_month, only_filter, dry_run, status, job_id,
    triggered_by_email, requested_by_sub, approved_manifest_id, result,
    error_message, started_at, heartbeat_at, finished_at, created_at,
    execution_owner, execution_epoch, execution_lease_until,
    reconciliation_classification, reconciled_at, alerted_at
"""

RESET_ITEM_COLUMNS = """
    id, operation_id, closing_month, next_month, site_code, sheet_id,
    company, store, status, ranges, error_message, started_at, completed_at,
    backup_path, backup_sha256, rollback_status, restored_at, updated_at,
    created_at, checkpoint_phase, fence_epoch, destructive_intent_at,
    verified_at, reconciled_at, recovery_code
"""

MANIFEST_COLUMNS = """
    id, operation_id, closing_month, operation, status,
    expected_store_count, processed_store_count, expected_agent_count,
    processed_agent_count, error_count, control_totals, artifacts,
    source_backups, manifest, manifest_sha256, requested_by_sub,
    approved_by_sub, approved_at, error_code, verified_at, consumed_at,
    updated_at, created_at
"""


@dataclass(frozen=True)
class ResetItemInput:
    site_code: str
    sheet_id: str
    company: str
    store: str
    ranges: Sequence[str]


@dataclass(frozen=True)
class MonthlyExecutionLease:
    operation_id: int
    execution_owner: str
    execution_epoch: int
    execution_lease_until: Any


EXECUTION_LEASE_SECONDS = 300


def operation_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if data.get("result") and isinstance(data["result"], str):
        data["result"] = json.loads(data["result"])
    return data


def manifest_to_dict(row: asyncpg.Record | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("control_totals", "artifacts", "source_backups", "manifest"):
        if data.get(key) is not None and isinstance(data[key], str):
            data[key] = json.loads(data[key])
    return data
