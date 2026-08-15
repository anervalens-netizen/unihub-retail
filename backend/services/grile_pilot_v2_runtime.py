"""Queue and worker lifecycle for the isolated Grile V2 projection."""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
import hashlib
import importlib
import logging
import re
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

from arq.constants import result_key_prefix
from arq.jobs import Job, JobStatus as ArqJobStatus

from request_context import bind_request_id, get_request_id, reset_request_id
import services.jobs as jobs_service
from services.grile_pilot_v2_registry import PILOT_V2_MONTH


logger = logging.getLogger(__name__)
_MONTH_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SHEETS_EPOCH = date(1899, 12, 30)
_BUCHAREST_TZ = ZoneInfo("Europe/Bucharest")


def _serial_day(value: date) -> int:
    return (value - _SHEETS_EPOCH).days


def _serial_instant(value: datetime) -> float:
    local_value = value.astimezone(_BUCHAREST_TZ)
    return (local_value.date() - _SHEETS_EPOCH).days + (
        local_value.hour * 3600 + local_value.minute * 60 + local_value.second
    ) / 86400


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _sales_source_revision(
    cutoff: date,
    forecast_factor: Decimal,
    *row_groups: Iterable[Mapping[str, Any]],
) -> int:
    """Return a Sheets-safe fingerprint of every non-Campaigns input."""
    digest = hashlib.sha256()
    for header_value in (cutoff, forecast_factor):
        encoded = str(header_value).encode()
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    for rows in row_groups:
        for row in rows:
            for key in sorted(row.keys()):
                for value in (key, row[key]):
                    encoded = str(value if value is not None else "").encode()
                    digest.update(len(encoded).to_bytes(4, "big"))
                    digest.update(encoded)
    return int.from_bytes(digest.digest()[:6], "big")


def _google_value(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, bool):
        return {"userEnteredValue": {"boolValue": value}}
    if isinstance(value, date):
        return {"userEnteredValue": {"numberValue": _serial_day(value)}}
    if isinstance(value, (Decimal, int, float)):
        return {"userEnteredValue": {"numberValue": float(value)}}
    return {"userEnteredValue": {"stringValue": str(value)}}


def _formula(value: str) -> dict[str, Any]:
    return {"userEnteredValue": {"formulaValue": value}}


def _rows(values: Iterable[Iterable[Any]]) -> list[dict[str, Any]]:
    return [{"values": [_google_value(value) for value in row]} for row in values]


def _source_head_lineage(
    cutoff_row: Mapping[str, Any] | None,
    sales_head: Mapping[str, Any] | None,
    campaign_head: Mapping[str, Any] | None,
) -> tuple[date, str, int, int]:
    if cutoff_row is None or cutoff_row["cutoff_date"] is None:
        raise RuntimeError("Authoritative sales cutoff is unavailable")
    if sales_head is None:
        raise RuntimeError("Authoritative sales outbox head is unavailable")
    if campaign_head is None:
        raise RuntimeError("Authoritative Campaigns projection is unavailable")
    authority_head = str(campaign_head["authority_head"] or "")
    if int(campaign_head["authority_count"] or 0) != 1 or not authority_head.startswith(
        "campaign:"
    ):
        raise RuntimeError("Authoritative Campaigns revision is inconsistent")
    try:
        campaign_revision = int(authority_head.removeprefix("campaign:"))
    except ValueError as exc:
        raise RuntimeError("Authoritative Campaigns revision is invalid") from exc
    return (
        cutoff_row["cutoff_date"],
        str(sales_head["generation_hash"] or ""),
        int(sales_head["revision"] or 0),
        campaign_revision,
    )


def _require_revision(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Grile V2 {name} revision is invalid")


def _validate_lineage(
    *,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
) -> None:
    if not _SHA256_RE.fullmatch(generation_hash):
        raise ValueError("Grile V2 generation hash is invalid")
    for name, revision in (
        ("sales", sales_revision),
        ("campaign", campaign_revision),
        ("contest", contest_revision),
    ):
        _require_revision(revision, name)


async def enqueue_grile_pilot_v2_sync(
    *,
    month: str,
    trigger: str,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
) -> Job:
    """Queue one generation-bound sync for the isolated Grile V2 pilot."""
    if not _MONTH_RE.fullmatch(month):
        raise ValueError("Grile V2 month is invalid")
    normalized_trigger = trigger.strip()[:128]
    if not normalized_trigger:
        raise ValueError("Grile V2 trigger is required")
    _validate_lineage(
        generation_hash=generation_hash,
        sales_revision=sales_revision,
        campaign_revision=campaign_revision,
        contest_revision=contest_revision,
    )
    pool = await jobs_service._require_arq_pool()
    job_id = f"grile-pilot-v2:{month}:{generation_hash}:{sales_revision}"
    enqueue_args = (
        "grile_pilot_v2_sync_background",
        month,
        normalized_trigger,
        generation_hash,
        sales_revision,
        campaign_revision,
        contest_revision,
        get_request_id(),
    )
    job = await jobs_service._publish_arq_job(
        pool,
        *enqueue_args,
        _job_id=job_id,
        _queue_name=jobs_service.GRILE_QUEUE_NAME,
    )
    if job is not None:
        return job
    existing = Job(job_id, pool, _queue_name=jobs_service.GRILE_QUEUE_NAME)
    existing_status = await existing.status()
    if existing_status in {ArqJobStatus.queued, ArqJobStatus.in_progress}:
        return existing
    if existing_status is ArqJobStatus.complete:
        result = await existing.result_info()
        if result is not None and result.success:
            return existing
    await pool.delete(result_key_prefix + job_id)
    replacement = await jobs_service._publish_arq_job(
        pool,
        *enqueue_args,
        _job_id=job_id,
        _queue_name=jobs_service.GRILE_QUEUE_NAME,
    )
    if replacement is not None:
        return replacement
    raise RuntimeError("Failed to enqueue Grile V2 sync")


async def sync_grile_pilot_v2_once(
    ctx: dict,
    *,
    trigger: str,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
) -> dict[str, Any]:
    logger.info(
        "Starting Grile V2 sync trigger=%s generation=%s revision=%s",
        trigger,
        generation_hash,
        sales_revision,
    )
    lock = ctx.setdefault("grile_pilot_v2_sync_lock", asyncio.Lock())
    async with lock:
        sync_module = importlib.import_module("services.grile_pilot_v2_sync")
        return await sync_module.sync_pilot_v2_sheets(
            ctx["db_pool"],
            ctx["grile_monthly_google"],
            generation_hash=generation_hash,
            sales_revision=sales_revision,
            campaign_revision=campaign_revision,
            contest_revision=contest_revision,
        )


def start_grile_pilot_v2_sync(ctx: dict) -> None:
    """Compatibility no-op: recovery now arrives only through the outbox."""
    ctx.pop("grile_pilot_v2_sync_stop", None)
    ctx.pop("grile_pilot_v2_sync_task", None)


async def stop_grile_pilot_v2_sync(ctx: dict) -> None:
    """Stop a legacy recovery task during rollback-safe mixed runtime trees."""
    stop = ctx.pop("grile_pilot_v2_sync_stop", None)
    if stop is not None:
        stop.set()
    task = ctx.pop("grile_pilot_v2_sync_task", None)
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def grile_pilot_v2_sync_background(
    ctx: dict,
    month: str,
    trigger: str,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    if month != PILOT_V2_MONTH:
        raise ValueError("Grile V2 sync is limited to the August 2026 pilot")
    _validate_lineage(
        generation_hash=generation_hash,
        sales_revision=sales_revision,
        campaign_revision=campaign_revision,
        contest_revision=contest_revision,
    )
    token = bind_request_id(request_id) if request_id else None
    try:
        return await sync_grile_pilot_v2_once(
            ctx,
            trigger=trigger,
            generation_hash=generation_hash,
            sales_revision=sales_revision,
            campaign_revision=campaign_revision,
            contest_revision=contest_revision,
        )
    finally:
        if token is not None:
            reset_request_id(token)
