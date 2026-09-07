"""Effective-once sales-generation projection chain for the outbox worker."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import hashlib
import json
import re
from typing import Any


SALES_EVENT_TYPE = "retail.sales_generation_promoted.v1"
_MONTH_RE = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

Publisher = Callable[..., Awaitable[Any]]


class _SalesGenerationSuperseded(Exception):
    """The requested generation is no longer the authoritative sales head."""


def _payload(event: Any) -> dict[str, Any]:
    value = event.payload
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise RuntimeError("sales outbox payload is invalid")
    return value


def _revision(publication: Any, name: str) -> int:
    revision = (
        publication.get("revision")
        if isinstance(publication, Mapping)
        else getattr(publication, "revision", None)
    )
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise RuntimeError(f"{name} publication revision is invalid")
    return revision


def _cache_key(payload: Mapping[str, Any]) -> tuple[str, str, int] | None:
    month = payload.get("month")
    generation_hash = payload.get("generation_hash")
    revision = payload.get("revision")
    if (
        not isinstance(month, str)
        or not isinstance(generation_hash, str)
        or not isinstance(revision, int)
        or isinstance(revision, bool)
    ):
        return None
    return month, generation_hash, revision


def _superseded_effect(
    *,
    month: str,
    generation_hash: str,
    sales_revision: int,
) -> dict[str, object]:
    generation_key = f"grile_v2:{generation_hash}:{sales_revision}"
    effect = {
        "contract": "grile-v2-sales-superseded-v1",
        "domain_generation_key": generation_key,
        "generation_hash": generation_hash,
        "month": month,
        "outcome": "superseded",
        "sales_revision": sales_revision,
    }
    return {
        "domain_generation_key": generation_key,
        "effect_sha256": _canonical_sha256(effect),
        "generation_hash": generation_hash,
        "outcome": "superseded",
        "sales_revision": sales_revision,
    }


def _superseded_receipt(
    *,
    month: str,
    generation_hash: str,
    sales_revision: int,
) -> dict[str, str]:
    result = _superseded_effect(
        month=month,
        generation_hash=generation_hash,
        sales_revision=sales_revision,
    )
    return {
        "consumer": "grile_v2",
        "domain_generation_key": str(result["domain_generation_key"]),
        "effect_sha256": str(result["effect_sha256"]),
    }


def _require_publication_result(
    result: Any,
    *,
    generation_hash: str,
    revision: int,
) -> Mapping[str, Any]:
    if not isinstance(result, Mapping):
        raise RuntimeError("campaign publication worker returned no result")
    if result.get("status") != "superseded":
        return result
    expected = {
        "sales_generation_hash": generation_hash,
        "sales_generation_revision": revision,
        "promotion": None,
        "contest": None,
        "grile_v2_job_id": None,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError("superseded campaign publication lineage differs")
    raise _SalesGenerationSuperseded


def _receipt_from_grile_result(
    result: Any,
    *,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
) -> dict[str, str]:
    if not isinstance(result, Mapping):
        raise RuntimeError("Grile V2 delivery result is invalid")
    if result.get("outcome") == "superseded":
        if (
            result.get("generation_hash") != generation_hash
            or result.get("sales_revision") != sales_revision
        ):
            raise RuntimeError("superseded Grile V2 delivery lineage differs")
        return _validated_effect_receipt(result, generation_hash, sales_revision)
    expected = {
        "generation_hash": generation_hash,
        "sales_revision": sales_revision,
        "campaign_revision": campaign_revision,
        "contest_revision": contest_revision,
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise RuntimeError("Grile V2 delivery lineage differs")
    return _validated_effect_receipt(result, generation_hash, sales_revision)


def _validated_effect_receipt(
    result: Mapping[str, Any],
    generation_hash: str,
    sales_revision: int,
) -> dict[str, str]:
    generation_key = result.get("domain_generation_key")
    effect_sha256 = result.get("effect_sha256")
    if generation_key != f"grile_v2:{generation_hash}:{sales_revision}":
        raise RuntimeError("Grile V2 generation receipt differs")
    if not isinstance(effect_sha256, str) or not _SHA256_RE.fullmatch(
        effect_sha256
    ):
        raise RuntimeError("Grile V2 effect digest is invalid")
    return {
        "consumer": "grile_v2",
        "domain_generation_key": generation_key,
        "effect_sha256": effect_sha256,
    }


async def _retired_grile_v2_effect(
    *,
    month: str,
    generation_hash: str,
    sales_revision: int,
    campaign_revision: int,
    contest_revision: int,
) -> dict[str, object]:
    """Acknowledge the retired pilot without queue or Google side effects."""
    key = f"grile_v2:{generation_hash}:{sales_revision}"
    effect = {
        "contract": "grile-v2-retired-v1",
        "domain_generation_key": key,
        "month": month,
        "sales_generation_hash": generation_hash,
        "sales_revision": sales_revision,
        "campaign_revision": campaign_revision,
        "contest_revision": contest_revision,
        "outcome": "retired",
    }
    return {
        "domain_generation_key": key,
        "effect_sha256": _canonical_sha256(effect),
        "outcome": "retired",
        "generation_hash": generation_hash,
        "sales_revision": sales_revision,
        "campaign_revision": campaign_revision,
        "contest_revision": contest_revision,
    }


async def deliver_sales_generation_event(
    event: Any,
    *,
    publish_campaigns: Publisher,
    publish_contests: Publisher,
    sync_grile_v2: Publisher,
) -> dict[str, str]:
    """Project one sales event; callbacks must be independently idempotent."""
    if event.event_type != SALES_EVENT_TYPE:
        raise RuntimeError("sales delivery received an unsupported event")
    payload = _payload(event)
    month = payload.get("month")
    generation_hash = payload.get("generation_hash")
    revision = payload.get("revision")
    if not isinstance(month, str) or not _MONTH_RE.fullmatch(month):
        raise RuntimeError("sales delivery month is invalid")
    if not isinstance(generation_hash, str) or not _SHA256_RE.fullmatch(
        generation_hash
    ):
        raise RuntimeError("sales delivery generation is invalid")
    if generation_hash != event.generation_hash:
        raise RuntimeError("sales delivery generation lineage differs")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise RuntimeError("sales delivery revision is invalid")
    if revision != event.revision:
        raise RuntimeError("sales delivery revision lineage differs")

    try:
        campaign = await publish_campaigns(
            month=month,
            generation_hash=generation_hash,
            revision=revision,
        )
        contest = await publish_contests(
            month=month,
            generation_hash=generation_hash,
            revision=revision,
        )
    except _SalesGenerationSuperseded:
        return _superseded_receipt(
            month=month,
            generation_hash=generation_hash,
            sales_revision=revision,
        )
    campaign_revision = _revision(campaign, "campaign")
    contest_revision = _revision(contest, "contest")
    result = await sync_grile_v2(
        month=month,
        generation_hash=generation_hash,
        sales_revision=revision,
        campaign_revision=campaign_revision,
        contest_revision=contest_revision,
    )
    return _receipt_from_grile_result(
        result,
        generation_hash=generation_hash,
        sales_revision=revision,
        campaign_revision=campaign_revision,
        contest_revision=contest_revision,
    )


def build_sales_generation_consumer(ctx: dict[str, Any]) -> Publisher:
    """Bind existing import/Grile queues without adding a queue identity."""
    if "db_pool" not in ctx:
        raise RuntimeError("outbox consumer requires the operations runtime context")
    publication_tasks: dict[tuple[str, str, int], asyncio.Task[Any]] = {}
    publication_lock = asyncio.Lock()

    async def run_publication(
        month: str,
        generation_hash: str,
        revision: int,
    ) -> Any:
        from services.jobs import enqueue_campaign_reporting_publication

        job = await enqueue_campaign_reporting_publication(
            month=month,
            requested_by_sub="system:outbox",
            reason=f"sales_outbox:{generation_hash}:{revision}",
            generation_hash=generation_hash,
            sales_revision=revision,
        )
        return await job.result(timeout=900, poll_delay=0.5)

    async def publication(
        month: str,
        generation_hash: str,
        revision: int,
    ) -> Mapping[str, Any]:
        key = (month, generation_hash, revision)
        async with publication_lock:
            task = publication_tasks.get(key)
            if task is None:
                task = asyncio.create_task(
                    run_publication(month, generation_hash, revision),
                    name=f"outbox-campaign-publication-{month}",
                )
                publication_tasks[key] = task
        try:
            result = await task
        except BaseException:
            async with publication_lock:
                if publication_tasks.get(key) is task:
                    publication_tasks.pop(key, None)
            raise
        return _require_publication_result(
            result,
            generation_hash=generation_hash,
            revision=revision,
        )

    async def publish_campaigns(
        *, month: str, generation_hash: str, revision: int
    ) -> dict[str, int]:
        result = await publication(month, generation_hash, revision)
        campaign = result.get("promotion")
        return {"revision": _revision(campaign, "campaign")}

    async def publish_contests(
        *, month: str, generation_hash: str, revision: int
    ) -> dict[str, int]:
        result = await publication(month, generation_hash, revision)
        contest = result.get("contest")
        return {"revision": _revision(contest, "contest")}

    async def sync_grile_v2(
        *,
        month: str,
        generation_hash: str,
        sales_revision: int,
        campaign_revision: int,
        contest_revision: int,
    ) -> dict[str, object]:
        return await _retired_grile_v2_effect(
            month=month,
            generation_hash=generation_hash,
            sales_revision=sales_revision,
            campaign_revision=campaign_revision,
            contest_revision=contest_revision,
        )

    async def consume(event: Any) -> dict[str, str]:
        payload = _payload(event)
        cache_key = _cache_key(payload)
        try:
            return await deliver_sales_generation_event(
                event,
                publish_campaigns=publish_campaigns,
                publish_contests=publish_contests,
                sync_grile_v2=sync_grile_v2,
            )
        finally:
            async with publication_lock:
                if cache_key is not None:
                    publication_tasks.pop(cache_key, None)

    return consume


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
