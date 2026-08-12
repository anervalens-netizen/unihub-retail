"""Database source loaders for immutable campaign reporting publication."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Literal

import asyncpg

from services.product_lists import get_data_dir


PublicationStatus = Literal["official", "partial", "unavailable"]


class CampaignReportingError(RuntimeError):
    """Campaign source cannot be published safely."""


@dataclass(frozen=True)
class _SalesSource:
    source_generation: str
    authority: str
    authority_head: str
    status: PublicationStatus
    is_final: bool
    cutoff: date | None
    coverage_numerator: int
    coverage_denominator: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Store:
    site_code: str
    locatie: str | None
    firma: str | None
    regional: str | None
    asm: str | None


@dataclass(frozen=True)
class _StoreAgent:
    store: _Store
    agent: str


def _agents_by_store(
    store_agents: list[_StoreAgent],
) -> dict[str, list[_StoreAgent]]:
    output: dict[str, list[_StoreAgent]] = defaultdict(list)
    for store_agent in store_agents:
        output[store_agent.store.site_code].append(store_agent)
    return output


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _empty_promo_metadata() -> dict[str, str | None]:
    return {
        "generation_id": None,
        "config_sha256": None,
        "actuals_sha256": None,
        "material_sha256": None,
    }


def _promo_generation_metadata() -> tuple[dict[str, str | None], list[str]]:
    """Read only the already-validated immutable promo pointer, if present."""
    pointer_path = get_data_dir() / "promo_generations" / "current.json"
    if not pointer_path.exists():
        return _empty_promo_metadata(), ["promo_generation_pointer_unavailable"]
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        metadata = {
            "generation_id": _clean_text(pointer.get("generation_id")),
            "config_sha256": _clean_text(pointer.get("config_sha256")),
            "actuals_sha256": _clean_text(pointer.get("actuals_sha256")),
            "material_sha256": _clean_text(pointer.get("material_sha256")),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return _empty_promo_metadata(), ["promo_generation_pointer_invalid"]
    invalid_id = (
        metadata["generation_id"] is not None
        and re.fullmatch(r"[0-9a-f]{32}", metadata["generation_id"]) is None
    )
    invalid_hash = any(
        value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
        for key, value in metadata.items()
        if key != "generation_id"
    )
    if invalid_id or invalid_hash:
        return _empty_promo_metadata(), ["promo_generation_pointer_invalid"]
    return metadata, []


async def _sales_source(conn: asyncpg.Connection, period: str) -> _SalesSource:
    row = await conn.fetchrow(
        """
        WITH selected AS (
            SELECT
                snapshot.*,
                head.snapshot_id AS head_snapshot_id,
                head.revision AS head_revision,
                ROW_NUMBER() OVER (
                    ORDER BY
                        (head.snapshot_id IS NOT NULL) DESC,
                        snapshot.promoted_at DESC NULLS LAST,
                        snapshot.finished_at DESC NULLS LAST,
                        snapshot.id DESC
                ) AS selection_rank
            FROM import_snapshots AS snapshot
            LEFT JOIN sales_generation_heads AS head
              ON head.import_month = snapshot.import_month
             AND head.snapshot_id = snapshot.id
            WHERE snapshot.import_month = $1
              AND snapshot.status = 'completed'
        )
        SELECT * FROM selected WHERE selection_rank = 1
        """,
        period,
    )
    if row is None:
        raise CampaignReportingError(
            f"Nu exista snapshot sales complet pentru {period}."
        )
    has_head = row["head_snapshot_id"] is not None
    return _SalesSource(
        source_generation=(
            f"sales:{row['generation_token']}"
            if row["generation_token"]
            else f"snapshot:{row['id']}"
        ),
        authority="sales_generation_head" if has_head else "legacy_completed_snapshot",
        authority_head=str(row["head_revision"] if has_head else row["id"]),
        status="official" if has_head else "partial",
        is_final=bool(row["is_month_final"]),
        cutoff=row["cutoff_date"],
        coverage_numerator=int(row["rows_imported"] or 0),
        coverage_denominator=int(row["rows_in_file"] or row["rows_imported"] or 0),
        warnings=(() if has_head else ("legacy_completed_snapshot_without_sales_head",)),
    )


async def _store_agents(
    conn: asyncpg.Connection,
    period: str,
) -> list[_StoreAgent]:
    rows = await conn.fetch(
        """
        SELECT site_code, agent, locatie, firma, regional, asm
        FROM reporting_agent_month
        WHERE import_month = $1
          AND locatie NOT ILIKE 'TR%'
          AND locatie NOT ILIKE '%cartel%'
        ORDER BY site_code, agent
        """,
        period,
    )
    return [
        _StoreAgent(
            store=_Store(
                site_code=str(row["site_code"]),
                locatie=_clean_text(row["locatie"]),
                firma=_clean_text(row["firma"]),
                regional=_clean_text(row["regional"]),
                asm=_clean_text(row["asm"]),
            ),
            agent=str(row["agent"]),
        )
        for row in rows
    ]


async def _focus_rows(
    conn: asyncpg.Connection,
    period: str,
    status: PublicationStatus,
    row_builder: Callable[..., dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT
            focus.site_code,
            focus.agent,
            MAX(focus.locatie) AS locatie,
            MAX(focus.firma) AS firma,
            MAX(focus.regional) AS regional,
            MAX(focus.asm) AS asm,
            COALESCE(SUM(focus.total_sales), 0) AS actual_sales,
            COALESCE(SUM(focus.total_quantity), 0)::BIGINT AS actual_quantity,
            COALESCE(
                ARRAY_AGG(DISTINCT focus.item_code ORDER BY focus.item_code)
                    FILTER (WHERE focus.total_quantity > 0),
                ARRAY[]::TEXT[]
            ) AS active_product_codes
        FROM reporting_focus_item_month AS focus
        WHERE focus.import_month = $1
          AND focus.locatie NOT ILIKE 'TR%'
          AND focus.locatie NOT ILIKE '%cartel%'
        GROUP BY focus.site_code, focus.agent
        ORDER BY focus.site_code, focus.agent
        """,
        period,
    )
    return [
        row_builder(
            mechanism="focus",
            campaign_key="focus",
            site=_Store(
                site_code=str(record["site_code"]),
                locatie=_clean_text(record["locatie"]),
                firma=_clean_text(record["firma"]),
                regional=_clean_text(record["regional"]),
                asm=_clean_text(record["asm"]),
            ),
            agent=str(record["agent"]),
            status=status,
            mechanism_variant="focus",
            actual_sales=Decimal(record["actual_sales"] or 0),
            actual_quantity=int(record["actual_quantity"] or 0),
            active_product_codes=list(record["active_product_codes"] or []),
        )
        for record in rows
    ]


async def _promotion_source_totals(
    conn: asyncpg.Connection,
    *,
    period: str,
    site_code: str,
    agent: str,
    start_date: date,
    end_date: date,
    item_codes: list[str],
) -> tuple[Decimal, int, list[str]]:
    row = await conn.fetchrow(
        """
        SELECT
            COALESCE(SUM(total_sales), 0) AS actual_sales,
            COALESCE(SUM(net_quantity), 0)::BIGINT AS actual_quantity,
            COALESCE(
                ARRAY_AGG(DISTINCT item_code ORDER BY item_code)
                    FILTER (WHERE positive_quantity > 0),
                ARRAY[]::TEXT[]
            ) AS active_product_codes
        FROM reporting_item_day
        WHERE import_month = $1
          AND site_code = $2
          AND agent = $3
          AND sale_date BETWEEN $4 AND $5
          AND item_code = ANY($6::TEXT[])
        """,
        period,
        site_code,
        agent,
        start_date,
        end_date,
        item_codes,
    )
    return (
        Decimal(row["actual_sales"] or 0),
        int(row["actual_quantity"] or 0),
        list(row["active_product_codes"] or []),
    )


async def _incentive_source_totals(
    conn: asyncpg.Connection,
    *,
    period: str,
    site_code: str,
    agent: str,
) -> tuple[Decimal, int, list[str]]:
    row = await conn.fetchrow(
        """
        SELECT
            COALESCE(SUM(agg.total_sales), 0) AS actual_sales,
            COALESCE(SUM(agg.net_quantity), 0)::BIGINT AS actual_quantity,
            COALESCE(
                ARRAY_AGG(DISTINCT agg.item_code ORDER BY agg.item_code)
                    FILTER (WHERE agg.positive_quantity > 0),
                ARRAY[]::TEXT[]
            ) AS active_product_codes
        FROM reporting_item_day AS agg
        JOIN incentive_campaigns AS campaign
          ON campaign.month = agg.import_month
        JOIN incentive_products AS product
          ON product.campaign_id = campaign.id
         AND product.item_code = agg.item_code
         AND agg.sale_date BETWEEN product.valid_from AND product.valid_to
        WHERE agg.import_month = $1
          AND agg.site_code = $2
          AND agg.agent = $3
        """,
        period,
        site_code,
        agent,
    )
    return (
        Decimal(row["actual_sales"] or 0),
        int(row["actual_quantity"] or 0),
        list(row["active_product_codes"] or []),
    )


async def _publish_campaign_generation(
    conn: asyncpg.Connection,
    *,
    period: str,
    sales: _SalesSource,
    promo_metadata: dict[str, str | None],
    incentive_campaign: dict[str, Any] | None,
    incentive_digest: str | None,
    status: PublicationStatus,
    warnings: list[str],
    input_sha256: str,
    rows_json: str,
    requested_by_sub: str,
    reason: str,
) -> Any:
    expected_revision = await conn.fetchval(
        "SELECT revision FROM campaign_reporting_heads WHERE period = $1",
        period,
    )
    return await conn.fetchrow(
        """
        SELECT * FROM public.publish_campaign_reporting_generation(
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
            $12, $13, $14, $15, $16, $17, $18, $19::JSONB, $20,
            $21, $22, $23
        )
        """,
        period,
        sales.source_generation,
        sales.authority,
        sales.authority_head,
        sales.status,
        sales.is_final,
        promo_metadata["generation_id"],
        promo_metadata["config_sha256"],
        promo_metadata["actuals_sha256"],
        promo_metadata["material_sha256"],
        int(incentive_campaign["id"]) if incentive_campaign is not None else None,
        incentive_digest,
        sales.cutoff,
        sales.coverage_numerator,
        sales.coverage_denominator,
        status,
        sorted(set(warnings)),
        input_sha256,
        rows_json,
        int(expected_revision or 0),
        requested_by_sub.strip(),
        reason.strip(),
        "promote",
    )
