"""Immutable publisher for the UniHub Insight contest read model.

The contest publisher reuses the canonical Retail ``ContestsService`` output
and only performs hierarchy enrichment, immutable generation shaping and the
DB-owned compare-and-set publication. Scoring remains owned by the existing
contest domain.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import asyncpg

from repositories.contests import ContestsRepository
from services.campaign_reporting import (
    CampaignReportingError,
    PublicationStatus,
    _Store,
    _canonical_bytes,
    _clean_text,
    _sales_source,
    _sha256,
)
from services.contests import ContestsService
from services.contests_config import load_contests_config


@dataclass(frozen=True)
class ContestReportingPublication:
    period: str
    generation_id: int
    revision: int
    row_count: int
    status: PublicationStatus
    input_sha256: str


async def _contest_hierarchy(
    conn: asyncpg.Connection,
    responses: list[Any],
) -> dict[str, _Store]:
    site_codes = sorted(
        {
            str(item.site_code)
            for response in responses
            for item in response.leaderboard
            if item.site_code
        }
    )
    rows = await conn.fetch(
        """
        SELECT site_code, locatie, firma, regional, asm
        FROM stores
        WHERE site_code = ANY($1::TEXT[])
        """,
        site_codes,
    )
    return {
        str(row["site_code"]): _Store(
            site_code=str(row["site_code"]),
            locatie=_clean_text(row["locatie"]),
            firma=_clean_text(row["firma"]),
            regional=_clean_text(row["regional"]),
            asm=_clean_text(row["asm"]),
        )
        for row in rows
    }


def _contest_publication_row(
    response: Any,
    item: Any,
    hierarchy: dict[str, _Store],
    *,
    status: PublicationStatus,
) -> dict[str, Any]:
    if not item.site_code:
        raise CampaignReportingError(
            "Concursul canonic a produs un agent fără site_code."
        )
    store = hierarchy.get(str(item.site_code))
    if store is None:
        raise CampaignReportingError(
            "Concursul canonic a produs un site fără ierarhie Retail."
        )
    warnings = (
        ["contest_promo_points_derive_from_units_not_receipts"]
        if int(item.promo_points)
        else []
    )
    return {
        "contest_key": response.key,
        "title": response.title,
        "subtitle": response.subtitle,
        "scope_label": response.scope_label,
        "start_date": response.start_date,
        "end_date": response.end_date,
        "store_count": response.store_count,
        "identity_policy": response.identity_policy,
        "rank": item.rank,
        "agent": item.agent,
        "site_code": item.site_code,
        "store_name": item.store_name,
        "locatie": store.locatie,
        "firma": store.firma,
        "regional": store.regional,
        "asm": store.asm,
        "focus_units": item.focus_units,
        "promo_units": item.promo_bonuri,
        "price_units": item.price_units,
        "focus_points": item.focus_points,
        "promo_points": item.promo_points,
        "price_points": item.price_points,
        "total_points": item.total_points,
        "prize": item.prize,
        "status": status,
        "warnings": warnings,
    }


def _contest_publication_rows(
    responses: list[Any],
    hierarchy: dict[str, _Store],
    *,
    status: PublicationStatus,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metadata = [response.model_dump() for response in responses]
    rows = [
        _contest_publication_row(response, item, hierarchy, status=status)
        for response in responses
        for item in response.leaderboard
    ]
    rows.sort(
        key=lambda row: (
            str(row["contest_key"]),
            int(row["rank"]),
            str(row["site_code"]),
            str(row["agent"]),
        )
    )
    return rows, metadata


def _contest_generation_payload(
    *,
    period: str,
    sales: Any,
    config_sha256: str,
    metadata: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> tuple[PublicationStatus, list[str], str]:
    status: PublicationStatus = sales.status if rows else "unavailable"
    warnings = list(sales.warnings)
    if not rows:
        warnings.append("no_active_contest")
    payload = {
        "contract": "contest-publication-v1",
        "period": period,
        "sales": asdict(sales),
        "contest_config_sha256": config_sha256,
        "contests": metadata,
        "rows": rows,
        "status": status,
        "warnings": warnings,
    }
    return status, warnings, _sha256(payload)


async def _publish_contest_generation(
    conn: asyncpg.Connection,
    *,
    period: str,
    sales: Any,
    config_sha256: str,
    status: PublicationStatus,
    warnings: list[str],
    input_sha256: str,
    metadata: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    requested_by_sub: str,
    reason: str,
) -> Any:
    expected_revision = await conn.fetchval(
        "SELECT revision FROM contest_reporting_heads WHERE period = $1",
        period,
    )
    return await conn.fetchrow(
        """
        SELECT * FROM public.publish_contest_reporting_generation(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
            $12, $13, $14::JSONB, $15::JSONB, $16, $17, $18, $19
        )
        """,
        period,
        sales.source_generation,
        sales.authority,
        sales.authority_head,
        sales.status,
        sales.is_final,
        config_sha256,
        sales.cutoff,
        sales.coverage_numerator,
        sales.coverage_denominator,
        status,
        warnings,
        input_sha256,
        _canonical_bytes(metadata).decode("utf-8"),
        _canonical_bytes(rows).decode("utf-8"),
        int(expected_revision or 0),
        requested_by_sub.strip(),
        reason.strip(),
        "promote",
    )


class ContestReportingPublisher:
    """Publish the existing canonical contest service without re-scoring it."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def publish_month(
        self,
        period: str,
        *,
        requested_by_sub: str,
        reason: str,
    ) -> ContestReportingPublication:
        if not requested_by_sub.strip() or not reason.strip():
            raise CampaignReportingError(
                "Publisherul concursuri cere actor și motiv explicite."
            )
        config, config_error = load_contests_config()
        if config_error:
            raise CampaignReportingError(
                "Configurația concursurilor este invalidă; capul existent rămâne activ."
            )
        config_sha256 = _sha256(config)
        async with self.pool.acquire() as conn:
            sales = await _sales_source(conn, period)
        responses = await ContestsService(
            ContestsRepository(self.pool),
            self.pool,
        ).get_active_contests(period)
        async with self.pool.acquire() as conn:
            hierarchy = await _contest_hierarchy(conn, responses)
            rows, metadata = _contest_publication_rows(
                responses,
                hierarchy,
                status=sales.status,
            )
            final_sales = await _sales_source(conn, period)
            final_config, final_error = load_contests_config()
            if final_error or _sha256(final_config) != config_sha256:
                raise CampaignReportingError(
                    "Configurația concursurilor s-a schimbat în timpul publicării; reîncearcă."
                )
            if final_sales != sales:
                raise CampaignReportingError(
                    "Snapshotul sales s-a schimbat în timpul publicării; reîncearcă."
                )
            status, warnings, input_sha256 = _contest_generation_payload(
                period=period,
                sales=sales,
                config_sha256=config_sha256,
                metadata=metadata,
                rows=rows,
            )
            head = await _publish_contest_generation(
                conn,
                period=period,
                sales=sales,
                config_sha256=config_sha256,
                status=status,
                warnings=warnings,
                input_sha256=input_sha256,
                metadata=metadata,
                rows=rows,
                requested_by_sub=requested_by_sub,
                reason=reason,
            )
        if head is None:
            raise CampaignReportingError(
                "Publisherul concursuri nu a primit capul CAS."
            )
        return ContestReportingPublication(
            period=period,
            generation_id=int(head["generation_id"]),
            revision=int(head["revision"]),
            row_count=len(rows),
            status=status,
            input_sha256=input_sha256,
        )
