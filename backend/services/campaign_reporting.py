"""Immutable publisher for the UniHub Insight campaign read model.

This module deliberately delegates Promo/Incentive calculation to the existing
Retail evaluator.  It only aggregates evaluator output at the published store
grain and writes one candidate through the DB-owned CAS function.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import asyncpg

from repositories.campaigns import CampaignsRepository
from services.campaigns import (
    build_campaign_context,
    build_promotions_incentives_on_snapshot,
)
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
    parse_promotion_definitions,
)
from services.incentive_db import get_incentive_campaign
from services.product_lists import get_data_dir
from services.promotion_evaluation import PromotionEvaluation, PromotionEvaluationStatus


PublicationStatus = Literal["official", "partial", "unavailable"]
_HASH = hashlib.sha256


class CampaignReportingError(RuntimeError):
    """Campaign source cannot be published safely."""


@dataclass(frozen=True)
class CampaignReportingPublication:
    period: str
    generation_id: int
    revision: int
    row_count: int
    status: PublicationStatus
    input_sha256: str


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


def _json_default(value: object) -> object:
    if isinstance(value, (date, Decimal)):
        return str(value)
    raise TypeError(f"Unsupported campaign publication value: {type(value)!r}")


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(payload: object) -> str:
    return _HASH(_canonical_bytes(payload)).hexdigest()


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _promo_generation_metadata() -> tuple[dict[str, str | None], list[str]]:
    """Read only the already-validated immutable promo pointer, if present."""
    pointer_path = get_data_dir() / "promo_generations" / "current.json"
    if not pointer_path.exists():
        return {
            "generation_id": None,
            "config_sha256": None,
            "actuals_sha256": None,
            "material_sha256": None,
        }, ["promo_generation_pointer_unavailable"]
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        metadata = {
            "generation_id": _clean_text(pointer.get("generation_id")),
            "config_sha256": _clean_text(pointer.get("config_sha256")),
            "actuals_sha256": _clean_text(pointer.get("actuals_sha256")),
            "material_sha256": _clean_text(pointer.get("material_sha256")),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "generation_id": None,
            "config_sha256": None,
            "actuals_sha256": None,
            "material_sha256": None,
        }, ["promo_generation_pointer_invalid"]
    invalid = (
        (
            metadata["generation_id"] is not None
            and re.fullmatch(r"[0-9a-f]{32}", metadata["generation_id"]) is None
        )
        or any(
            value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None
            for key, value in metadata.items()
            if key != "generation_id"
        )
    )
    if invalid:
        return {
            "generation_id": None,
            "config_sha256": None,
            "actuals_sha256": None,
            "material_sha256": None,
        }, ["promo_generation_pointer_invalid"]
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
        raise CampaignReportingError(f"Nu exista snapshot sales complet pentru {period}.")
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
        warnings=(
            () if has_head else ("legacy_completed_snapshot_without_sales_head",)
        ),
    )


async def _store_agents(conn: asyncpg.Connection, period: str) -> list[_StoreAgent]:
    rows = await conn.fetch(
        """
        SELECT
            site_code,
            agent,
            locatie,
            firma,
            regional,
            asm
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


async def _focus_rows(conn: asyncpg.Connection, period: str, status: PublicationStatus) -> list[dict[str, Any]]:
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
        _row(
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


def _row(
    *,
    mechanism: str,
    campaign_key: str,
    site: _Store,
    agent: str,
    status: PublicationStatus,
    warnings: Iterable[str] = (),
    actual_sales: Decimal | None = None,
    actual_quantity: int | None = None,
    active_product_codes: Iterable[str] = (),
    promo_qualifying_bons: int | None = None,
    promo_discounted_units: int | None = None,
    promo_discount_value: Decimal | None = None,
    incentive_sold_quantity: int | None = None,
    incentive_eligible_quantity: int | None = None,
    incentive_qualified_quantity: int | None = None,
    incentive_value: Decimal | None = None,
    incentive_potential: Decimal | None = None,
    incentive_store_qualified: bool | None = None,
) -> dict[str, Any]:
    normalized_product_codes = sorted({str(code) for code in active_product_codes})
    return {
        "mechanism": mechanism,
        "campaign_key": campaign_key,
        "site_code": site.site_code,
        "agent": agent,
        "locatie": site.locatie,
        "firma": site.firma,
        "regional": site.regional,
        "asm": site.asm,
        "actual_sales": actual_sales,
        "actual_quantity": actual_quantity,
        "active_product_count": len(normalized_product_codes),
        "active_product_codes": normalized_product_codes,
        "promo_qualifying_bons": promo_qualifying_bons,
        "promo_discounted_units": promo_discounted_units,
        "promo_discount_value": promo_discount_value,
        "incentive_sold_quantity": incentive_sold_quantity,
        "incentive_eligible_quantity": incentive_eligible_quantity,
        "incentive_qualified_quantity": incentive_qualified_quantity,
        "incentive_value": incentive_value,
        "incentive_potential": incentive_potential,
        "incentive_store_qualified": incentive_store_qualified,
        "status": status,
        "warnings": sorted({warning for warning in warnings if warning}),
    }


def _status_from_evaluation(
    evaluation: PromotionEvaluation,
    sales_status: PublicationStatus,
) -> PublicationStatus:
    if evaluation.status is PromotionEvaluationStatus.INVALID:
        return "unavailable"
    if evaluation.status is PromotionEvaluationStatus.PARTIAL:
        return "partial"
    return sales_status


def _generation_status(rows: list[dict[str, Any]]) -> PublicationStatus:
    statuses = {str(row["status"]) for row in rows}
    if statuses == {"official"}:
        return "official"
    if statuses == {"unavailable"}:
        return "unavailable"
    return "partial"


def _promo_agent_metrics(
    result: Any,
    *,
    site_code: str,
    agent: str,
) -> tuple[int, int, Decimal] | tuple[None, None, None]:
    if result is None:
        return None, None, None
    discounted_units = sum(
        int(units)
        for (site, result_agent, _item), units in result.excluded_units.items()
        if site == site_code and result_agent == agent
    )
    discount_value = sum(
        (
            value
            for (site, result_agent, _item), value in result.excluded_discount_values.items()
            if site == site_code and result_agent == agent
        ),
        Decimal("0"),
    )
    # The canonical evaluator enforces one discounted unit per qualifying bon.
    return discounted_units, discounted_units, discount_value


def _source_agent(agent: str) -> str:
    return "-" if agent == "Neatribuit" else agent


def _decimal(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class CampaignReportingPublisher:
    """Materialize one month through canonical campaign evaluation and DB CAS."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def publish_month(
        self,
        period: str,
        *,
        requested_by_sub: str,
        reason: str,
        action: Literal["promote", "rollback"] = "promote",
    ) -> CampaignReportingPublication:
        if not requested_by_sub.strip() or not reason.strip():
            raise CampaignReportingError("Publisherul cere actor și motiv explicite.")
        async with self.pool.acquire() as conn:
            sales = await _sales_source(conn, period)
            store_agents = await _store_agents(conn, period)
            if not store_agents:
                raise CampaignReportingError(f"Nu exista magazine eligibile pentru {period}.")
            promo_metadata, pointer_warnings = _promo_generation_metadata()
            config, config_error = load_special_cards_config()
            definitions, definitions_error = parse_promotion_definitions(config, period)
            selected_definition, selected_error = parse_promotion_definition(config, period)
            promotion_error = selected_error or definitions_error
            incentive_campaign = await get_incentive_campaign(conn, period)
            rows = await _focus_rows(conn, period, sales.status)
            all_warnings = [*sales.warnings, *pointer_warnings]
            if config_error:
                all_warnings.append(config_error)
            if promotion_error:
                all_warnings.append(promotion_error)
            campaign_source_status: PublicationStatus = (
                "partial" if pointer_warnings else sales.status
            )

            agents_by_store: dict[str, list[_StoreAgent]] = defaultdict(list)
            for store_agent in store_agents:
                agents_by_store[store_agent.store.site_code].append(store_agent)
            campaign_repo = CampaignsRepository(self.pool)
            year, month = (int(value) for value in period.split("-", 1))
            campaign_start = date(year, month, 1)
            campaign_end = date(
                year + (month == 12),
                1 if month == 12 else month + 1,
                1,
            )
            campaign_end -= timedelta(days=1)

            for site_code, store_scopes in agents_by_store.items():
                store = store_scopes[0].store
                context = await build_campaign_context(
                    conn,
                    config_error=config_error,
                    promotion_definitions=definitions,
                    promotion_definition=selected_definition,
                    promotion_error=promotion_error,
                    incentive_campaign=incentive_campaign,
                    month=period,
                    firma=None,
                    regional=None,
                    asm=None,
                    site_code=site_code,
                    agent=None,
                    include_incentive=True,
                    current_scope=False,
                    include_closed_stores=False,
                )
                for definition, evaluation in context.promotion_evaluations:
                    row_status = _status_from_evaluation(
                        evaluation,
                        campaign_source_status,
                    )
                    result = evaluation.result
                    for store_agent in store_scopes:
                        source_sales, source_qty, source_product_codes = await _promotion_source_totals(
                            conn,
                            period=period,
                            site_code=site_code,
                            agent=store_agent.agent,
                            start_date=definition["start_date"],
                            end_date=definition["end_date"],
                            item_codes=evaluation.item_codes,
                        )
                        qualifying_bons, discounted_units, discount_value = _promo_agent_metrics(
                            result,
                            site_code=site_code,
                            agent=store_agent.agent,
                        )
                        rows.append(
                            _row(
                                mechanism="promo",
                                campaign_key=str(definition["key"]),
                                site=store,
                                agent=store_agent.agent,
                                status=row_status,
                                warnings=[evaluation.warning] if evaluation.warning else (),
                                actual_sales=source_sales,
                                actual_quantity=source_qty,
                                active_product_codes=source_product_codes,
                                promo_qualifying_bons=qualifying_bons,
                                promo_discounted_units=discounted_units,
                                promo_discount_value=discount_value,
                            )
                        )

                if incentive_campaign is not None:
                    canonical_incentive = await build_promotions_incentives_on_snapshot(
                        campaign_repo,
                        conn,
                        campaign_start,
                        campaign_end,
                        firma=None,
                        regional=None,
                        asm=None,
                        site_code=site_code,
                        agent=None,
                    )
                    incentive_status: PublicationStatus = (
                        campaign_source_status
                        if canonical_incentive["incentive_calculation_status"] == "complete"
                        else "unavailable"
                    )
                    incentive_agents = {
                        str(item.agent_name): item
                        for item in canonical_incentive["top_agents"]
                    }
                    scope_by_agent = {scope.agent: scope for scope in store_scopes}
                    for agent_name in sorted(set(scope_by_agent) | set(incentive_agents)):
                        source_sales, source_qty, source_product_codes = await _incentive_source_totals(
                            conn,
                            period=period,
                            site_code=site_code,
                            agent=_source_agent(agent_name),
                        )
                        allocation = incentive_agents.get(agent_name)
                        eligible_qty = (
                            int(allocation.qty_sold) if allocation is not None else 0
                        )
                        qualified = bool(
                            canonical_incentive["incentive_qualified_stores"]
                        )
                        rows.append(
                            _row(
                                mechanism="incentive",
                                campaign_key=f"incentive:{incentive_campaign['id']}",
                                site=store,
                                agent=agent_name,
                                status=incentive_status,
                                warnings=canonical_incentive["calculation_warnings"],
                                actual_sales=source_sales,
                                actual_quantity=source_qty,
                                active_product_codes=source_product_codes,
                                incentive_sold_quantity=source_qty,
                                incentive_eligible_quantity=(
                                    eligible_qty if incentive_status != "unavailable" else None
                                ),
                                incentive_qualified_quantity=(
                                    eligible_qty if qualified and incentive_status != "unavailable" else (
                                        0 if incentive_status != "unavailable" else None
                                    )
                                ),
                                incentive_value=(
                                    _decimal(allocation.val_incentive)
                                    if allocation is not None and incentive_status != "unavailable"
                                    else (Decimal("0") if incentive_status != "unavailable" else None)
                                ),
                                incentive_potential=(
                                    _decimal(allocation.incentive_potential)
                                    if allocation is not None and incentive_status != "unavailable"
                                    else (Decimal("0") if incentive_status != "unavailable" else None)
                                ),
                                incentive_store_qualified=(
                                    qualified if incentive_status != "unavailable" else None
                                ),
                            )
                        )

            rows.sort(
                key=lambda row: (
                    str(row["mechanism"]),
                    str(row["campaign_key"]),
                    str(row["site_code"]),
                    str(row["agent"]),
                )
            )
            final_sales = await _sales_source(conn, period)
            final_promo_metadata, final_pointer_warnings = _promo_generation_metadata()
            if final_sales != sales:
                raise CampaignReportingError(
                    "Snapshotul sales s-a schimbat în timpul publicării; reîncearcă."
                )
            if final_promo_metadata != promo_metadata or final_pointer_warnings != pointer_warnings:
                raise CampaignReportingError(
                    "Pointerul promo s-a schimbat în timpul publicării; reîncearcă."
                )
            status = _generation_status(rows)
            incentive_digest = (
                _sha256(incentive_campaign) if incentive_campaign is not None else None
            )
            input_payload = {
                "contract": "campaign-publication-v2",
                "period": period,
                "sales": asdict(sales),
                "promo": promo_metadata,
                "incentive_campaign_id": (
                    int(incentive_campaign["id"]) if incentive_campaign is not None else None
                ),
                "incentive_input_sha256": incentive_digest,
                "rows": rows,
                "status": status,
                "warnings": sorted(set(all_warnings)),
            }
            input_sha256 = _sha256(input_payload)
            expected_revision = await conn.fetchval(
                "SELECT revision FROM campaign_reporting_heads WHERE period = $1",
                period,
            )
            head = await conn.fetchrow(
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
                sorted(set(all_warnings)),
                input_sha256,
                _canonical_bytes(rows).decode("utf-8"),
                int(expected_revision or 0),
                requested_by_sub.strip(),
                reason.strip(),
                action,
            )
        if head is None:
            raise CampaignReportingError("Publisherul nu a primit capul CAS.")
        return CampaignReportingPublication(
            period=period,
            generation_id=int(head["generation_id"]),
            revision=int(head["revision"]),
            row_count=len(rows),
            status=status,
            input_sha256=input_sha256,
        )
