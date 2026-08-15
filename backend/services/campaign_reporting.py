"""Immutable publisher for the UniHub Insight campaign read model.
This module deliberately delegates Promo/Incentive calculation to the existing
Retail evaluator.  It only aggregates evaluator output at the published store
grain and writes one candidate through the DB-owned CAS function.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

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
from services.promotion_evaluation import PromotionEvaluation, PromotionEvaluationStatus
from services.campaign_reporting_sources import (
    CampaignReportingError,
    PublicationStatus,
    _SalesSource,
    _Store,
    _StoreAgent,
    _agents_by_store,
    _clean_text,
    _focus_rows as _load_focus_rows,
    _incentive_source_totals,
    _publish_campaign_generation,
    _promo_generation_metadata,
    _promotion_source_totals,
    _sales_source,
    _store_agents,
)


_HASH = hashlib.sha256


@dataclass(frozen=True)
class CampaignReportingPublication:
    period: str
    generation_id: int
    revision: int
    row_count: int
    status: PublicationStatus
    input_sha256: str




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


async def _focus_rows(conn: asyncpg.Connection, period: str, status: PublicationStatus) -> list[dict[str, Any]]:
    return await _load_focus_rows(conn, period, status, _row)


def _row(
    *,
    mechanism: str,
    campaign_key: str,
    site: _Store,
    agent: str,
    status: PublicationStatus,
    mechanism_variant: str | None = None,
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
        "mechanism_variant": mechanism_variant,
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
    receipt_identity_available: bool,
) -> tuple[int | None, int, Decimal] | tuple[None, None, None]:
    if result is None:
        return None, None, None
    source_agent = _source_agent(agent)
    discounted_units = sum(
        int(units)
        for (site, result_agent, _item), units in result.excluded_units.items()
        if site == site_code and result_agent == source_agent
    )
    discount_value = sum(
        (
            Decimal(str(value))
            for (site, result_agent, _item), value in result.excluded_discount_values.items()
            if site == site_code and result_agent == source_agent
        ),
        Decimal("0"),
    )
    # POS actuals carry discounted units, not receipt identities.  A merged
    # POS + rule tail cannot safely claim a monthly receipt count either.
    return (
        discounted_units if receipt_identity_available else None,
        discounted_units,
        discount_value,
    )


def _promo_receipt_identity_available(definition: dict[str, Any]) -> bool:
    """Only a wholly rule-based evaluator retains a receipt identity."""
    return not bool(
        definition.get("actuals_source_file") or definition.get("actuals_file")
    )


def _promo_mechanism_variant(definition: dict[str, Any]) -> str:
    """Publish the validated promo rule type, never infer a family from its key."""
    variant = str(definition.get("rule_type") or "selected_item_copurchase")
    if variant not in {
        "selected_item_copurchase",
        "same_model_screen_camera",
        "trigger_discounted",
    }:
        raise CampaignReportingError("Tipul promo nu poate fi publicat stabil.")
    return variant


def _promo_store_agents(
    result: Any,
    *,
    site_code: str,
    store_agents: list[_StoreAgent],
) -> list[_StoreAgent]:
    """Expose canonical Neatribuit totals produced under the source agent '-'."""
    if result is None or not store_agents:
        return store_agents
    has_unassigned = any(
        site == site_code and result_agent == "-"
        for site, result_agent, _item in result.excluded_units
    )
    has_published_unassigned = any(
        scope.agent in {"-", "Neatribuit"} for scope in store_agents
    )
    if not has_unassigned or has_published_unassigned:
        return store_agents
    return [*store_agents, _StoreAgent(store_agents[0].store, "Neatribuit")]


def _source_agent(agent: str) -> str:
    return "-" if agent == "Neatribuit" else agent


def _decimal(value: object | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _campaign_month_bounds(period: str) -> tuple[date, date]:
    year, month = (int(value) for value in period.split("-", 1))
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return start, end - timedelta(days=1)


async def _promotion_publication_rows(
    conn: asyncpg.Connection,
    *,
    period: str,
    site_code: str,
    store: _Store,
    store_scopes: list[_StoreAgent],
    context: Any,
    source_status: PublicationStatus,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for definition, evaluation in context.promotion_evaluations:
        row_status = _status_from_evaluation(evaluation, source_status)
        result = evaluation.result
        for store_agent in _promo_store_agents(
            result,
            site_code=site_code,
            store_agents=store_scopes,
        ):
            sales, quantity, product_codes = await _promotion_source_totals(
                conn,
                period=period,
                site_code=site_code,
                agent=_source_agent(store_agent.agent),
                start_date=definition["start_date"],
                end_date=definition["end_date"],
                item_codes=evaluation.item_codes,
            )
            receipt_identity_available = _promo_receipt_identity_available(definition)
            qualifying_bons, discounted_units, discount_value = _promo_agent_metrics(
                result,
                site_code=site_code,
                agent=store_agent.agent,
                receipt_identity_available=receipt_identity_available,
            )
            warnings = [evaluation.warning] if evaluation.warning else []
            if not receipt_identity_available:
                warnings.append(
                    "promo_qualifying_bons_unavailable_pos_units_only"
                )
            rows.append(
                _row(
                    mechanism="promo",
                    campaign_key=str(definition["key"]),
                    site=store,
                    agent=store_agent.agent,
                    status=row_status,
                    mechanism_variant=_promo_mechanism_variant(definition),
                    warnings=warnings,
                    actual_sales=sales,
                    actual_quantity=quantity,
                    active_product_codes=product_codes,
                    promo_qualifying_bons=qualifying_bons,
                    promo_discounted_units=discounted_units,
                    promo_discount_value=discount_value,
                )
            )
    return rows


def _incentive_publication_row(
    *,
    campaign_id: int,
    store: _Store,
    agent_name: str,
    status: PublicationStatus,
    canonical: dict[str, Any],
    allocation: Any | None,
    source_sales: Decimal,
    source_qty: int,
    source_product_codes: list[str],
) -> dict[str, Any]:
    available = status != "unavailable"
    eligible_qty = int(allocation.qty_sold) if allocation is not None else 0
    qualified = bool(canonical["incentive_qualified_stores"])
    value = _decimal(allocation.val_incentive) if allocation is not None else Decimal("0")
    potential = (
        _decimal(allocation.incentive_potential)
        if allocation is not None
        else Decimal("0")
    )
    return _row(
        mechanism="incentive",
        campaign_key=f"incentive:{campaign_id}",
        site=store,
        agent=agent_name,
        status=status,
        mechanism_variant="incentive",
        warnings=canonical["calculation_warnings"],
        actual_sales=source_sales,
        actual_quantity=source_qty,
        active_product_codes=source_product_codes,
        incentive_sold_quantity=source_qty,
        incentive_eligible_quantity=eligible_qty if available else None,
        incentive_qualified_quantity=(eligible_qty if qualified else 0) if available else None,
        incentive_value=value if available else None,
        incentive_potential=potential if available else None,
        incentive_store_qualified=qualified if available else None,
    )


async def _incentive_publication_rows(
    conn: asyncpg.Connection,
    *,
    repo: CampaignsRepository,
    period: str,
    site_code: str,
    store: _Store,
    store_scopes: list[_StoreAgent],
    campaign: dict[str, Any] | None,
    source_status: PublicationStatus,
) -> list[dict[str, Any]]:
    if campaign is None:
        return []
    start, end = _campaign_month_bounds(period)
    canonical = await build_promotions_incentives_on_snapshot(
        repo,
        conn,
        start,
        end,
        firma=None,
        regional=None,
        asm=None,
        site_code=site_code,
        agent=None,
    )
    status: PublicationStatus = (
        source_status
        if canonical["incentive_calculation_status"] == "complete"
        else "unavailable"
    )
    allocations = {str(item.agent_name): item for item in canonical["top_agents"]}
    agent_names = sorted({scope.agent for scope in store_scopes} | set(allocations))
    rows: list[dict[str, Any]] = []
    for agent_name in agent_names:
        sales, quantity, codes = await _incentive_source_totals(
            conn,
            period=period,
            site_code=site_code,
            agent=_source_agent(agent_name),
        )
        rows.append(
            _incentive_publication_row(
                campaign_id=int(campaign["id"]),
                store=store,
                agent_name=agent_name,
                status=status,
                canonical=canonical,
                allocation=allocations.get(agent_name),
                source_sales=sales,
                source_qty=quantity,
                source_product_codes=codes,
            )
        )
    return rows


async def _campaign_store_rows(
    conn: asyncpg.Connection,
    *,
    repo: CampaignsRepository,
    period: str,
    site_code: str,
    store_scopes: list[_StoreAgent],
    config_error: str | None,
    definitions: list[dict[str, Any]],
    selected_definition: dict[str, Any] | None,
    promotion_error: str | None,
    incentive_campaign: dict[str, Any] | None,
    source_status: PublicationStatus,
) -> list[dict[str, Any]]:
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
    store = store_scopes[0].store
    promo_rows = await _promotion_publication_rows(
        conn,
        period=period,
        site_code=site_code,
        store=store,
        store_scopes=store_scopes,
        context=context,
        source_status=source_status,
    )
    incentive_rows = await _incentive_publication_rows(
        conn,
        repo=repo,
        period=period,
        site_code=site_code,
        store=store,
        store_scopes=store_scopes,
        campaign=incentive_campaign,
        source_status=source_status,
    )
    return [*promo_rows, *incentive_rows]


def _campaign_input_hash(
    *,
    period: str,
    sales: _SalesSource,
    promo_metadata: dict[str, str | None],
    incentive_campaign: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    status: PublicationStatus,
    warnings: list[str],
) -> tuple[str | None, str]:
    incentive_digest = (
        _sha256(incentive_campaign) if incentive_campaign is not None else None
    )
    payload = {
        "contract": "campaign-publication-v2",
        "period": period,
        "sales": asdict(sales),
        "promo": promo_metadata,
        "incentive_campaign_id": (
            int(incentive_campaign["id"])
            if incentive_campaign is not None
            else None
        ),
        "incentive_input_sha256": incentive_digest,
        "rows": rows,
        "status": status,
        "warnings": sorted(set(warnings)),
    }
    return incentive_digest, _sha256(payload)


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
    ) -> CampaignReportingPublication:
        if not requested_by_sub.strip() or not reason.strip():
            raise CampaignReportingError(
                "Publisherul cere actor și motiv explicite."
            )
        async with self.pool.acquire() as conn:
            sales = await _sales_source(conn, period)
            store_agents = await _store_agents(conn, period)
            if not store_agents:
                raise CampaignReportingError(
                    f"Nu exista magazine eligibile pentru {period}."
                )
            promo_metadata, pointer_warnings = _promo_generation_metadata()
            config, config_error = load_special_cards_config()
            definitions, definitions_error = parse_promotion_definitions(
                config,
                period,
            )
            selected, selected_error = parse_promotion_definition(config, period)
            promotion_error = selected_error or definitions_error
            incentive_campaign = await get_incentive_campaign(conn, period)
            rows = await _focus_rows(conn, period, sales.status)
            warnings = [*sales.warnings, *pointer_warnings]
            if config_error:
                warnings.append(config_error)
            if promotion_error:
                warnings.append(promotion_error)
            source_status: PublicationStatus = (
                "partial" if pointer_warnings else sales.status
            )
            repo = CampaignsRepository(self.pool)
            for site_code, store_scopes in _agents_by_store(store_agents).items():
                rows.extend(
                    await _campaign_store_rows(
                        conn,
                        repo=repo,
                        period=period,
                        site_code=site_code,
                        store_scopes=store_scopes,
                        config_error=config_error,
                        definitions=definitions,
                        selected_definition=selected,
                        promotion_error=promotion_error,
                        incentive_campaign=incentive_campaign,
                        source_status=source_status,
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
            final_metadata, final_pointer_warnings = _promo_generation_metadata()
            if final_sales != sales:
                raise CampaignReportingError(
                    "Snapshotul sales s-a schimbat în timpul publicării; reîncearcă."
                )
            if (
                final_metadata != promo_metadata
                or final_pointer_warnings != pointer_warnings
            ):
                raise CampaignReportingError(
                    "Pointerul promo s-a schimbat în timpul publicării; reîncearcă."
                )
            status = _generation_status(rows)
            incentive_digest, input_sha256 = _campaign_input_hash(
                period=period,
                sales=sales,
                promo_metadata=promo_metadata,
                incentive_campaign=incentive_campaign,
                rows=rows,
                status=status,
                warnings=warnings,
            )
            head = await _publish_campaign_generation(
                conn,
                period=period,
                sales=sales,
                promo_metadata=promo_metadata,
                incentive_campaign=incentive_campaign,
                incentive_digest=incentive_digest,
                status=status,
                warnings=warnings,
                input_sha256=input_sha256,
                rows_json=_canonical_bytes(rows).decode("utf-8"),
                requested_by_sub=requested_by_sub,
                reason=reason,
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
