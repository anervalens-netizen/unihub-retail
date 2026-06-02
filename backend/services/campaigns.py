from __future__ import annotations

from decimal import Decimal
from typing import Any

import asyncpg

from models import (
    CampaignOverview,
    CampaignProductStat,
    CampaignSnapshot,
    CampaignStoreStat,
    FocusHistoryResponse,
    FocusHistoryPoint,
    PromoTopStore,
    IncentiveCategory,
    IncentiveTopAgent,
)
from repositories.campaigns import CampaignsRepository
from services.dashboard.queries import _fetch_promo_incentive_summary, _get_store_incentive_multipliers
from services.filters import normalize_filter, scoped_clauses
from services.dashboard_specials import (
    load_special_cards_config,
    parse_promotion_definition,
)
from services.incentive_db import get_incentive_campaign
from services.promo_copurchase import compute_promo_copurchase


def _campaign_clauses(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
    *,
    alias: str,
) -> tuple[list[str], list[Any]]:
    clauses = [f"{alias}.locatie NOT ILIKE 'TR %'", f"{alias}.import_month = $1"]
    params: list[Any] = [month]
    site_scope = normalize_filter(site_code)
    for column, value in [
        (f"{alias}.firma", None if site_scope else normalize_filter(firma)),
        (f"{alias}.regional", None if site_scope else normalize_filter(regional)),
        (f"{alias}.asm", None if site_scope else normalize_filter(asm)),
        (f"{alias}.site_code", site_scope),
        (f"{alias}.agent", normalize_filter(agent)),
    ]:
        if value:
            params.append(value)
            clauses.append(f"{column} = ANY(string_to_array(${len(params)}::TEXT, ','))")
    return clauses, params


class CampaignsService:
    def __init__(self, repo: CampaignsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def get_campaign_overview(
        self,
        month: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> CampaignSnapshot:
        focus_clauses, focus_params = _campaign_clauses(
            month, firma, regional, asm, site_code, agent, alias="agg"
        )
        totals_clauses, totals_params = _campaign_clauses(
            month, firma, regional, asm, site_code, agent, alias="tot"
        )
        focus_where_sql = " AND ".join(focus_clauses)
        totals_where_sql = " AND ".join(totals_clauses)

        data = await self.repo.fetch_overview(focus_where_sql, totals_where_sql, focus_params)

        overview = (
            CampaignOverview(**dict(data["overview"]))
            if data["overview"]
            else CampaignOverview(
                month=month,
                total_focus_sales=Decimal(0),
                total_focus_qty=0,
                focus_share_pct=None,
                active_focus_products=0,
                active_focus_stores=0,
            )
        )
        return CampaignSnapshot(
            overview=overview,
            products=[CampaignProductStat(**dict(row)) for row in data["products"]],
            stores=[CampaignStoreStat(**dict(row)) for row in data["stores"]],
        )

    async def get_focus_history(
        self,
        month: str,
        months_back: int,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> FocusHistoryResponse:
        params: list[Any] = [month, months_back]
        positions: dict[str, int] = {}
        for key, value in [
            ("firma", normalize_filter(firma)),
            ("regional", normalize_filter(regional)),
            ("asm", normalize_filter(asm)),
            ("site_code", normalize_filter(site_code)),
            ("agent", normalize_filter(agent)),
        ]:
            if value is not None:
                params.append(value)
                positions[key] = len(params)

        focus_clauses = ["agg.import_month IN (SELECT import_month FROM recent_months)"]
        totals_clauses = ["tot.import_month IN (SELECT import_month FROM recent_months)"]
        for key, focus_column, totals_column in [
            ("firma", "agg.firma", "tot.firma"),
            ("regional", "agg.regional", "tot.regional"),
            ("asm", "agg.asm", "tot.asm"),
            ("site_code", "agg.site_code", "tot.site_code"),
            ("agent", "agg.agent", "tot.agent"),
        ]:
            if key in positions:
                focus_clauses.append(f"{focus_column} = ${positions[key]}")
                totals_clauses.append(f"{totals_column} = ${positions[key]}")

        rows = await self.repo.fetch_history(focus_clauses, totals_clauses, params)
        return FocusHistoryResponse(
            history=[FocusHistoryPoint(**dict(row)) for row in rows]
        )

    async def get_promotions_incentives(
        self,
        start_date: str,
        end_date: str,
        firma: str | None,
        regional: str | None,
        asm: str | None,
        site_code: str | None,
        agent: str | None,
    ) -> dict:
        from datetime import date as date_cls

        start = date_cls.fromisoformat(start_date)
        end = date_cls.fromisoformat(end_date)
        month = start_date[:7]

        # Cand site_code e prezent el domina scope-ul: scoped_clauses() ignora
        # firma/regional/asm, deci NU trebuie sa-i adaugam ca parametri (altfel
        # raman parametri orfani -> asyncpg IndeterminateDatatypeError). Mirror
        # exact al logicii din _campaign_clauses.
        site_scope = normalize_filter(site_code)

        config, _ = load_special_cards_config()
        promotion_definition, promotion_error = parse_promotion_definition(config, month)

        async with self.pool.acquire() as conn:
            promo_title = (
                promotion_definition.get("title", "Promotie")
                if promotion_definition
                else ""
            )
            promo_description = (
                promotion_definition.get("description", "") if promotion_definition else ""
            )

            incentive_campaign = await get_incentive_campaign(conn, month)
            incentive_title = incentive_campaign["title"] if incentive_campaign else ""
            incentive_description = incentive_campaign["description"] if incentive_campaign else ""

            summary = await _fetch_promo_incentive_summary(
                conn=conn,
                month=month,
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
            )

            promo_qty = summary.promo_qty
            promo_impact = float(summary.promo_impact)
            incentive_qty = summary.incentive_qty
            incentive_value = float(summary.incentive_value)

            promo_total_qty = 0
            store_multipliers: dict[str, float] = {}
            store_achievements: dict[str, float | None] = {}
            if incentive_campaign is not None:
                store_multipliers, store_achievements = await _get_store_incentive_multipliers(
                    conn, month, firma, regional, asm, site_code
                )

            has_active_promotion = promotion_definition is not None and promotion_error is None

            # Regula co-purchase: unitatile reduse (1 per bon calificat) nu se incentiveaza.
            promo_excluded_ag: dict[tuple[str, str, str], int] = {}
            promo_excluded_si: dict[tuple[str, str], int] = {}
            promo_qualifying_bons = 0
            promo_discounted_units = 0
            promo_active_stores = 0
            promo_active_agents = 0
            promo_bonuri_by_store: dict[str, int] = {}
            if has_active_promotion:
                assert promotion_definition is not None
                promo_cp = await compute_promo_copurchase(
                    conn,
                    month=month,
                    start_date=promotion_definition["start_date"],
                    end_date=promotion_definition["end_date"],
                    item_codes=promotion_definition["item_codes"],
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )
                promo_excluded_ag = promo_cp.excluded_units
                promo_excluded_si = promo_cp.excluded_by_site_item()
                promo_qualifying_bons = promo_cp.qualifying_bons
                promo_discounted_units = promo_cp.discounted_units
                promo_active_stores = promo_cp.active_stores
                promo_active_agents = promo_cp.active_agents
                for (site, _ag, _item), units in promo_excluded_ag.items():
                    promo_bonuri_by_store[site] = promo_bonuri_by_store.get(site, 0) + units
                if incentive_campaign is not None:
                    reward_map_hdr = incentive_campaign["reward_map"]
                    excluded_value = sum(
                        units
                        * reward_map_hdr.get(item, 0)
                        * store_multipliers.get(site, 0)
                        for (site, _ag, item), units in promo_excluded_ag.items()
                    )
                    # Doar unitatile care sunt si produse incentive scad din qty.
                    excluded_inc_units = sum(
                        units
                        for (_site, _ag, item), units in promo_excluded_ag.items()
                        if item in reward_map_hdr
                    )
                    incentive_value = max(0.0, incentive_value - float(excluded_value))
                    incentive_qty = max(0, incentive_qty - excluded_inc_units)

            if has_active_promotion:
                assert promotion_definition is not None
                promo_month = start_date[:7]
                promo_params: list[Any] = [
                    start,
                    end,
                    promotion_definition["item_codes"],
                    promo_month,
                ]
                positions: dict[str, int] = {}
                for key, value in [
                    ("firma", None if site_scope else normalize_filter(firma)),
                    ("regional", None if site_scope else normalize_filter(regional)),
                    ("asm", None if site_scope else normalize_filter(asm)),
                    ("site_code", site_scope),
                    ("agent", normalize_filter(agent)),
                ]:
                    if value is not None:
                        promo_params.append(value)
                        positions[key] = len(promo_params)

                promo_clauses = [
                    "agg.import_month = $4",
                    "agg.sale_date BETWEEN $1 AND $2",
                    "agg.item_code = ANY($3::TEXT[])",
                ]
                promo_query_clauses = scoped_clauses(
                    positions,
                    site_alias="agg",
                    store_alias="agg",
                    agent_alias="agg",
                )
                promo_clauses.extend(promo_query_clauses)

                total_row = await self.repo.fetch_promo_total(promo_clauses, promo_params)
                if total_row:
                    promo_total_qty = int(total_row["total_qty"] or 0)

                store_rows = await self.repo.fetch_promo_store_rows(promo_clauses, promo_params)
                top_stores = [
                    PromoTopStore(
                        # qty = bonuri promo calificate (co-purchase) per magazin, nu cantitate simpla
                        store_name=f"{row['site_code']} - {row['locatie']}",
                        qty=promo_bonuri_by_store.get(row["site_code"], 0),
                        total_qty=row["total_qty"],
                        category_qty=0,
                        incentive_value=0.0,
                        achievement=store_achievements.get(row["site_code"]),
                        firma=row["firma"] or "",
                    )
                    for row in store_rows
                ]
            else:
                top_stores = []

            if incentive_campaign is not None:
                reward_map_for_stores: dict[str, float] | None = incentive_campaign["reward_map"] or None
                if reward_map_for_stores:
                    inc_store_params: list[Any] = [list(reward_map_for_stores.keys()), month]
                    inc_store_positions: dict[str, int] = {}
                    for key, value in [
                        ("firma", None if site_scope else normalize_filter(firma)),
                        ("regional", None if site_scope else normalize_filter(regional)),
                        ("asm", None if site_scope else normalize_filter(asm)),
                        ("site_code", site_scope),
                    ]:
                        if value is not None:
                            inc_store_params.append(value)
                            inc_store_positions[key] = len(inc_store_params)
                    inc_store_clauses = [
                        "agg.item_code = ANY($1::TEXT[])",
                        "agg.import_month = $2",
                    ]
                    inc_store_query_clauses = scoped_clauses(
                        inc_store_positions,
                        site_alias="agg", store_alias="agg", agent_alias="agg",
                    )
                    inc_store_clauses.extend(inc_store_query_clauses)
                    store_item_rows = await self.repo.fetch_incentive_store_rows(inc_store_clauses, inc_store_params)
                    store_inc: dict[str, list] = {}
                    for row in store_item_rows:
                        sc = row["site_code"]
                        loc = row["locatie"]
                        firma_val = row["firma"] or ""
                        excluded = promo_excluded_si.get((sc, row["item_code"]), 0)
                        val = max(0, int(row["qty"]) - excluded) * reward_map_for_stores.get(row["item_code"], 0) * store_multipliers.get(sc, 0)
                        if sc not in store_inc:
                            store_inc[sc] = [loc, 0.0, firma_val]
                        store_inc[sc][1] += val

                    if has_active_promotion:
                        top_stores = [
                            PromoTopStore(
                                store_name=s.store_name,
                                qty=s.qty,
                                total_qty=s.total_qty,
                                category_qty=s.category_qty,
                                incentive_value=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, ""])[1], 2),
                                achievement=s.achievement,
                                firma=s.firma,
                            )
                            for s in top_stores
                        ]
                    else:
                        top_stores = [
                            PromoTopStore(
                                store_name=f"{sc} - {data[0]}",
                                qty=0,
                                total_qty=0,
                                category_qty=0,
                                incentive_value=round(data[1], 2),
                                achievement=store_achievements.get(sc),
                                firma=data[2],
                            )
                            for sc, data in store_inc.items()
                        ]

            top_agents: list[IncentiveTopAgent] = []
            incentive_categories: list[IncentiveCategory] = []
            incentive_product_count = 0

            if incentive_campaign is not None:
                reward_map = incentive_campaign.get("reward_map") or {}
                incentive_product_count = len(reward_map)

                if reward_map:
                    inc_agent_params: list[Any] = [list(reward_map.keys()), month]
                    inc_agent_positions: dict[str, int] = {}
                    for key, value in [
                        ("firma", None if site_scope else normalize_filter(firma)),
                        ("regional", None if site_scope else normalize_filter(regional)),
                        ("asm", None if site_scope else normalize_filter(asm)),
                        ("site_code", site_scope),
                        ("agent", normalize_filter(agent)),
                    ]:
                        if value is not None:
                            inc_agent_params.append(value)
                            inc_agent_positions[key] = len(inc_agent_params)
                    inc_agent_clauses = [
                        "agg.item_code = ANY($1::TEXT[])",
                        "agg.import_month = $2",
                    ]
                    inc_agent_query_clauses = scoped_clauses(
                        inc_agent_positions,
                        site_alias="agg", store_alias="agg", agent_alias="agg",
                    )
                    inc_agent_clauses.extend(inc_agent_query_clauses)
                    agent_item_rows = await conn.fetch(
                        f"""
                        SELECT agg.agent, agg.site_code, agg.item_code,
                               COALESCE(SUM(agg.net_quantity), 0)::INT AS qty
                        FROM reporting_item_month agg
                        WHERE {" AND ".join(inc_agent_clauses)}
                          AND agg.agent IS NOT NULL AND agg.agent != '-'
                        GROUP BY agg.agent, agg.site_code, agg.item_code
                        """,
                        *inc_agent_params,
                    )
                    agent_inc: dict[str, float] = {}
                    agent_qty: dict[str, int] = {}
                    agent_sites: dict[str, str] = {}
                    for row in agent_item_rows:
                        ag = row["agent"]
                        sc = row["site_code"]
                        excluded = promo_excluded_ag.get((sc, ag, row["item_code"]), 0)
                        adj_net = int(row["qty"]) - excluded
                        q = max(0, adj_net)
                        val = q * reward_map.get(row["item_code"], 0) * store_multipliers.get(sc, 0)
                        agent_inc[ag] = agent_inc.get(ag, 0.0) + val
                        agent_qty[ag] = agent_qty.get(ag, 0) + adj_net
                        agent_sites[ag] = sc

                    top_agents = sorted(
                        [
                            IncentiveTopAgent(
                                agent_name=ag,
                                qty_sold=agent_qty[ag],
                                val_incentive=round(agent_inc[ag], 2),
                                achievement=store_achievements.get(agent_sites.get(ag, ""))
                            )
                            for ag in agent_inc
                        ],
                        key=lambda x: x.val_incentive,
                        reverse=True,
                    )[:20]

                    tier_qty: dict[str, int] = {}
                    tier_value: dict[str, float] = {}
                    for row in agent_item_rows:
                        reward_val = reward_map.get(row["item_code"], 0)
                        if reward_val <= 0:
                            continue
                        label = f"{int(reward_val)} RON" if reward_val == int(reward_val) else f"{reward_val} RON"
                        excluded = promo_excluded_ag.get((row["site_code"], row["agent"], row["item_code"]), 0)
                        q = max(0, int(row["qty"]) - excluded)
                        tier_qty[label] = tier_qty.get(label, 0) + q
                        tier_value[label] = tier_value.get(label, 0.0) + q * reward_val
                    incentive_categories = sorted(
                        [
                            IncentiveCategory(label=label, qty=tier_qty[label], value=round(tier_value[label], 2))
                            for label in tier_qty
                        ],
                        key=lambda x: x.value,
                        reverse=True,
                    )

            return {
                "promo_title": promo_title,
                "promo_description": promo_description,
                "promo_total_qty": promo_total_qty,
                "promo_qty": promo_qty,
                "promo_category_qty": None,
                "promo_impact": promo_impact,
                "promo_qualifying_bons": promo_qualifying_bons,
                "promo_discounted_units": promo_discounted_units,
                "promo_active_stores": promo_active_stores,
                "promo_active_agents": promo_active_agents,
                "has_active_promotion": has_active_promotion,
                "top_stores": top_stores,
                "top_agents": top_agents,
                "incentive_title": incentive_title,
                "incentive_description": incentive_description,
                "incentive_qty": incentive_qty,
                "incentive_value": incentive_value,
                "incentive_product_count": incentive_product_count,
                "incentive_categories": incentive_categories,
            }
