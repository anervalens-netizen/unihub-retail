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
            raise CampaignReportingError("Publisherul concursuri cere actor și motiv explicite.")
        config, config_error = load_contests_config()
        if config_error:
            raise CampaignReportingError("Configurația concursurilor este invalidă; capul existent rămâne activ.")
        config_sha256 = _sha256(config)
        # Do not retain a pool connection while ContestsService acquires its own;
        # imports deployments are allowed to use a one-connection pool.
        async with self.pool.acquire() as conn:
            sales = await _sales_source(conn, period)
        responses = await ContestsService(
            ContestsRepository(self.pool), self.pool
        ).get_active_contests(period)
        async with self.pool.acquire() as conn:
            site_codes = sorted(
                {
                    str(item.site_code)
                    for response in responses
                    for item in response.leaderboard
                    if item.site_code
                }
            )
            hierarchy_rows = await conn.fetch(
                """
                SELECT site_code, locatie, firma, regional, asm
                FROM stores
                WHERE site_code = ANY($1::TEXT[])
                """,
                site_codes,
            )
            hierarchy = {
                str(row["site_code"]): _Store(
                    site_code=str(row["site_code"]),
                    locatie=_clean_text(row["locatie"]),
                    firma=_clean_text(row["firma"]),
                    regional=_clean_text(row["regional"]),
                    asm=_clean_text(row["asm"]),
                )
                for row in hierarchy_rows
            }
            rows: list[dict[str, Any]] = []
            metadata: list[dict[str, Any]] = []
            for response in responses:
                response_data = response.model_dump()
                # Retain the full service payload as a generation artifact.  Rows below
                # deliberately repeat the public identity and scoring fields for Insight.
                metadata.append(response_data)
                for item in response.leaderboard:
                    if not item.site_code:
                        raise CampaignReportingError("Concursul canonic a produs un agent fără site_code.")
                    store = hierarchy.get(str(item.site_code))
                    if store is None:
                        raise CampaignReportingError("Concursul canonic a produs un site fără ierarhie Retail.")
                    warnings = []
                    if int(item.promo_points):
                        warnings.append("contest_promo_points_derive_from_units_not_receipts")
                    rows.append(
                        {
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
                            "status": sales.status,
                            "warnings": warnings,
                        }
                    )
            rows.sort(
                key=lambda row: (
                    str(row["contest_key"]),
                    int(row["rank"]),
                    str(row["site_code"]),
                    str(row["agent"]),
                )
            )
            final_sales = await _sales_source(conn, period)
            final_config, final_error = load_contests_config()
            if final_error or _sha256(final_config) != config_sha256:
                raise CampaignReportingError(
                    "Configurația concursurilor s-a schimbat în timpul publicării; reîncearcă."
                )
            if final_sales != sales:
                raise CampaignReportingError("Snapshotul sales s-a schimbat în timpul publicării; reîncearcă.")
            status: PublicationStatus = sales.status if rows else "unavailable"
            generation_warnings = list(sales.warnings)
            if not rows:
                generation_warnings.append("no_active_contest")
            input_payload = {
                "contract": "contest-publication-v1",
                "period": period,
                "sales": asdict(sales),
                "contest_config_sha256": config_sha256,
                "contests": metadata,
                "rows": rows,
                "status": status,
                "warnings": generation_warnings,
            }
            input_sha256 = _sha256(input_payload)
            expected_revision = await conn.fetchval(
                "SELECT revision FROM contest_reporting_heads WHERE period = $1", period
            )
            head = await conn.fetchrow(
                """
                SELECT * FROM public.publish_contest_reporting_generation(
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                    $12, $13, $14::JSONB, $15::JSONB, $16, $17, $18, $19
                )
                """,
                period, sales.source_generation, sales.authority, sales.authority_head,
                sales.status, sales.is_final, config_sha256, sales.cutoff,
                sales.coverage_numerator, sales.coverage_denominator, status,
                generation_warnings, input_sha256,
                _canonical_bytes(metadata).decode("utf-8"), _canonical_bytes(rows).decode("utf-8"),
                int(expected_revision or 0), requested_by_sub.strip(), reason.strip(), "promote",
            )
        if head is None:
            raise CampaignReportingError("Publisherul concursuri nu a primit capul CAS.")
        return ContestReportingPublication(
            period=period,
            generation_id=int(head["generation_id"]),
            revision=int(head["revision"]),
            row_count=len(rows),
            status=status,
            input_sha256=input_sha256,
        )
