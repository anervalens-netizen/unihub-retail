from __future__ import annotations

from datetime import timedelta
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
    PromoTopAgent,
    IncentiveCategory,
    IncentiveTopAgent,
)
from repositories.campaigns import CampaignsRepository
from services.dashboard.queries import _fetch_promo_incentive_summary, _get_store_incentive_multipliers
from services.dashboard_specials import (
    load_promotion_rule_products,
    load_special_cards_config,
    parse_promotion_definitions,
    parse_promotion_definition,
)
from services.incentive_db import get_incentive_campaign
from services.promo_copurchase import (
    PromoCoPurchaseResult,
    compute_promo_actuals_from_report,
    compute_promo_copurchase,
    compute_promo_same_model_pair,
    compute_promo_trigger_discounted,
    merge_promo_results,
    promo_actuals_cutoff_date,
)


def _merge_excluded_units(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, units in source.items():
        target[key] = target.get(key, 0) + units


def _excluded_by_site_item(
    excluded_units: dict[tuple[str, str, str], int],
) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = {}
    for (site_code, _agent, item_code), units in excluded_units.items():
        out[(site_code, item_code)] = out.get((site_code, item_code), 0) + units
    return out


async def _compute_promotion_result(
    conn: asyncpg.Connection,
    *,
    month: str,
    definition: dict[str, Any],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> tuple[PromoCoPurchaseResult | None, list[str], str, str | None]:
    products, products_error = load_promotion_rule_products(definition)
    if products_error is not None or products is None:
        return None, [], definition.get("rule_type") or "selected_item_copurchase", products_error

    rule_type = definition.get("rule_type") or "selected_item_copurchase"
    if rule_type == "same_model_screen_camera":
        promotion_item_codes = list(products["discounted_codes"])
    elif rule_type == "trigger_discounted":
        promotion_item_codes = list(products["discounted_codes"])
    else:
        promotion_item_codes = list(products["item_codes"])

    actual_result = await compute_promo_actuals_from_report(
        conn,
        month=month,
        definition=definition,
        item_codes=promotion_item_codes,
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    if actual_result is not None:
        cutoff_date = promo_actuals_cutoff_date(definition)
        if cutoff_date is None:
            return actual_result, promotion_item_codes, rule_type, None
        tail_start = max(definition["start_date"], cutoff_date + timedelta(days=1))
        if tail_start > definition["end_date"]:
            return actual_result, promotion_item_codes, rule_type, None
        tail_definition = {
            **definition,
            "start_date": tail_start,
            "actuals_source_file": None,
            "actuals_file": None,
        }
        tail_result, _tail_codes, _tail_rule, tail_error = await _compute_promotion_result(
            conn,
            month=month,
            definition=tail_definition,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
        if tail_error is not None:
            return actual_result, promotion_item_codes, rule_type, None
        return merge_promo_results(actual_result, tail_result), promotion_item_codes, rule_type, None

    if rule_type == "same_model_screen_camera":
        return (
            await compute_promo_same_model_pair(
                conn,
                month=month,
                start_date=definition["start_date"],
                end_date=definition["end_date"],
                screen_code_models=products["trigger_code_models"],
                camera_code_models=products["discounted_code_models"],
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
            ),
            promotion_item_codes,
            rule_type,
            None,
        )
    if rule_type == "trigger_discounted":
        return (
            await compute_promo_trigger_discounted(
                conn,
                month=month,
                start_date=definition["start_date"],
                end_date=definition["end_date"],
                trigger_codes=products["trigger_codes"],
                discounted_codes=products["discounted_codes"],
                firma=firma,
                regional=regional,
                asm=asm,
                site_code=site_code,
                agent=agent,
            ),
            promotion_item_codes,
            rule_type,
            None,
        )
    return (
        await compute_promo_copurchase(
            conn,
            month=month,
            start_date=definition["start_date"],
            end_date=definition["end_date"],
            item_codes=promotion_item_codes,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        ),
        promotion_item_codes,
        rule_type,
        None,
    )


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
        data = await self.repo.fetch_overview(
            month,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )

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
        rows = await self.repo.fetch_history(
            month,
            months_back,
            firma=firma,
            regional=regional,
            asm=asm,
            site_code=site_code,
            agent=agent,
        )
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
        promotion_key: str | None = None,
    ) -> dict:
        from datetime import date as date_cls

        start = date_cls.fromisoformat(start_date)
        end = date_cls.fromisoformat(end_date)
        month = start_date[:7]

        config, _ = load_special_cards_config()
        promotion_definitions, promotion_list_error = parse_promotion_definitions(config, month)
        promotion_definition, promotion_error = parse_promotion_definition(
            config,
            month,
            promotion_key=promotion_key,
        )
        if promotion_error is None:
            promotion_error = promotion_list_error
        promotion_options = [
            {
                "key": str(definition.get("key") or ""),
                "label": str(definition.get("title") or "Promotie"),
            }
            for definition in promotion_definitions
        ]

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
            promo_bonuri_by_agent: dict[str, int] = {}
            promo_agent_sites: dict[str, dict[str, int]] = {}
            promotion_item_codes: list[str] = []
            promotion_rule_type = "selected_item_copurchase"
            incentive_excluded_ag: dict[tuple[str, str, str], int] = {}
            if has_active_promotion:
                assert promotion_definition is not None
                promo_cp, promotion_item_codes, promotion_rule_type, products_error = (
                    await _compute_promotion_result(
                        conn,
                        month=month,
                        definition=promotion_definition,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                    )
                )
                if products_error is not None:
                    has_active_promotion = False
                    promotion_error = products_error
                if promo_cp is None:
                    promo_cp = None
                else:
                    promo_excluded_ag = promo_cp.excluded_units
                    promo_excluded_si = promo_cp.excluded_by_site_item()
                    promo_qualifying_bons = promo_cp.qualifying_bons
                    promo_discounted_units = promo_cp.discounted_units
                    promo_active_stores = promo_cp.active_stores
                    promo_active_agents = promo_cp.active_agents
                    for (site, _ag, _item), units in promo_excluded_ag.items():
                        promo_bonuri_by_store[site] = promo_bonuri_by_store.get(site, 0) + units
                        if _ag and _ag != "-":
                            promo_bonuri_by_agent[_ag] = promo_bonuri_by_agent.get(_ag, 0) + units
                            site_weights = promo_agent_sites.setdefault(_ag, {})
                            site_weights[site] = site_weights.get(site, 0) + units
                    _merge_excluded_units(incentive_excluded_ag, promo_excluded_ag)

                selected_key = promotion_definition.get("key")
                for extra_definition in promotion_definitions:
                    if extra_definition.get("key") == selected_key:
                        continue
                    extra_cp, _extra_item_codes, _extra_rule_type, extra_error = (
                        await _compute_promotion_result(
                            conn,
                            month=month,
                            definition=extra_definition,
                            firma=firma,
                            regional=regional,
                            asm=asm,
                            site_code=site_code,
                            agent=agent,
                        )
                    )
                    if extra_error is not None or extra_cp is None:
                        continue
                    _merge_excluded_units(incentive_excluded_ag, extra_cp.excluded_units)

                incentive_excluded_si = _excluded_by_site_item(incentive_excluded_ag)
            else:
                incentive_excluded_si = {}

            if has_active_promotion:
                assert promotion_definition is not None
                promo_month = start_date[:7]
                total_row = await self.repo.fetch_promo_total(
                    start,
                    end,
                    promotion_item_codes,
                    promo_month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )
                if total_row:
                    promo_total_qty = int(total_row["total_qty"] or 0)

                store_rows = await self.repo.fetch_promo_store_rows(
                    start,
                    end,
                    promotion_item_codes,
                    promo_month,
                    firma=firma,
                    regional=regional,
                    asm=asm,
                    site_code=site_code,
                    agent=agent,
                )
                top_stores = [
                    PromoTopStore(
                        store_name=f"{row['site_code']} - {row['locatie']}",
                        qty=0,
                        total_qty=row["total_qty"],
                        category_qty=0,
                        promo_bons=promo_bonuri_by_store.get(row["site_code"], 0),
                        incentive_value=0.0,
                        incentive_potential=0.0,
                        achievement=store_achievements.get(row["site_code"]),
                        firma=row["firma"] or "",
                    )
                    for row in store_rows
                    if (
                        promotion_rule_type == "selected_item_copurchase"
                        or promo_bonuri_by_store.get(row["site_code"], 0) > 0
                    )
                ]
            else:
                top_stores = []

            store_meta = {
                store.store_name.split(" - ")[0]: (store.store_name, store.firma)
                for store in top_stores
            }
            promo_agent_rows: list[PromoTopAgent] = []
            for agent_name, promo_bons in promo_bonuri_by_agent.items():
                primary_site = max(
                    promo_agent_sites[agent_name],
                    key=lambda site: (promo_agent_sites[agent_name][site], site),
                )
                store_name, firma_val = store_meta.get(primary_site, ("", ""))
                promo_agent_rows.append(
                    PromoTopAgent(
                        agent_name=agent_name,
                        store_name=store_name,
                        firma=firma_val,
                        promo_bons=promo_bons,
                    )
                )
            promo_agents = sorted(
                promo_agent_rows,
                key=lambda item: (-item.promo_bons, item.agent_name),
            )

            if incentive_campaign is not None:
                reward_map_for_stores: dict[str, float] | None = incentive_campaign["reward_map"] or None
                if reward_map_for_stores:
                    store_item_rows = await self.repo.fetch_incentive_store_rows(
                        list(reward_map_for_stores.keys()),
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                    )
                    store_inc: dict[str, list] = {}
                    for row in store_item_rows:
                        sc = row["site_code"]
                        loc = row["locatie"]
                        firma_val = row["firma"] or ""
                        excluded = incentive_excluded_si.get((sc, row["item_code"]), 0)
                        qty = max(0, int(row["qty"]) - excluded)
                        potential = qty * reward_map_for_stores.get(row["item_code"], 0)
                        val = potential * store_multipliers.get(sc, 0)
                        if sc not in store_inc:
                            store_inc[sc] = [loc, 0.0, firma_val, 0, 0.0]
                        store_inc[sc][1] += val
                        store_inc[sc][3] += qty
                        store_inc[sc][4] += potential

                    if has_active_promotion:
                        top_stores = [
                            PromoTopStore(
                                store_name=s.store_name,
                                qty=store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, "", 0])[3],
                                total_qty=s.total_qty,
                                category_qty=s.category_qty,
                                promo_bons=s.promo_bons,
                                incentive_value=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, ""])[1], 2),
                                incentive_potential=round(store_inc.get(s.store_name.split(" - ")[0], [None, 0.0, "", 0, 0.0])[4], 2),
                                achievement=s.achievement,
                                firma=s.firma,
                            )
                            for s in top_stores
                        ]
                    else:
                        top_stores = [
                            PromoTopStore(
                                store_name=f"{sc} - {data[0]}",
                                qty=data[3],
                                total_qty=0,
                                category_qty=0,
                                promo_bons=0,
                                incentive_value=round(data[1], 2),
                                incentive_potential=round(data[4], 2),
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
                    agent_item_rows = await self.repo.fetch_incentive_agent_rows(
                        list(reward_map.keys()),
                        month,
                        firma=firma,
                        regional=regional,
                        asm=asm,
                        site_code=site_code,
                        agent=agent,
                    )
                    agent_inc: dict[str, float] = {}
                    agent_potential: dict[str, float] = {}
                    agent_qty: dict[str, int] = {}
                    agent_site_qty: dict[str, dict[str, int]] = {}
                    agent_store_meta: dict[str, tuple[str, str]] = {}
                    for row in agent_item_rows:
                        ag = str(row["agent"])
                        sc = str(row["site_code"])
                        loc = str(row["locatie"] or "")
                        firma_val = str(row["firma"] or "")
                        item_code = str(row["item_code"])
                        excluded = incentive_excluded_ag.get((sc, ag, item_code), 0)
                        adj_net = int(row["qty"]) - excluded
                        q = max(0, adj_net)
                        potential = q * reward_map.get(item_code, 0)
                        val = potential * store_multipliers.get(sc, 0)
                        agent_inc[ag] = agent_inc.get(ag, 0.0) + val
                        agent_potential[ag] = agent_potential.get(ag, 0.0) + potential
                        agent_qty[ag] = agent_qty.get(ag, 0) + adj_net
                        agent_store_meta[sc] = (loc, firma_val)
                        agent_site_qty.setdefault(ag, {})
                        agent_site_qty[ag][sc] = agent_site_qty[ag].get(sc, 0) + q

                    agent_rows: list[IncentiveTopAgent] = []
                    for ag in agent_inc:
                        site_quantities = agent_site_qty.get(ag, {})
                        primary_site = max(
                            site_quantities,
                            key=lambda site: (site_quantities[site], site),
                            default="",
                        )
                        loc, firma_val = agent_store_meta.get(primary_site, ("", ""))
                        store_name = f"{primary_site} - {loc}" if primary_site and loc else primary_site
                        agent_rows.append(
                            IncentiveTopAgent(
                                agent_name=ag,
                                store_name=store_name,
                                firma=firma_val,
                                qty_sold=agent_qty[ag],
                                val_incentive=round(agent_inc[ag], 2),
                                incentive_potential=round(agent_potential[ag], 2),
                                achievement=store_achievements.get(primary_site),
                            )
                        )

                    top_agents = sorted(
                        agent_rows,
                        key=lambda x: x.val_incentive,
                        reverse=True,
                    )

                    tier_qty: dict[str, int] = {}
                    tier_value: dict[str, float] = {}
                    for row in agent_item_rows:
                        reward_val = reward_map.get(row["item_code"], 0)
                        if reward_val <= 0:
                            continue
                        label = f"{int(reward_val)} RON" if reward_val == int(reward_val) else f"{reward_val} RON"
                        excluded = incentive_excluded_ag.get((row["site_code"], row["agent"], row["item_code"]), 0)
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
                "promotions": promotion_options,
                "selected_promotion_key": promotion_definition.get("key", "") if promotion_definition else "",
                "promo_title": promo_title,
                "promo_description": promotion_error or promo_description,
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
                "promo_agents": promo_agents,
                "top_agents": top_agents,
                "incentive_title": incentive_title,
                "incentive_description": incentive_description,
                "incentive_qty": incentive_qty,
                "incentive_value": incentive_value,
                "incentive_product_count": incentive_product_count,
                "incentive_categories": incentive_categories,
            }
