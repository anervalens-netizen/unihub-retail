"""Pure aggregation helpers shared by campaign evaluators and responses."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from schemas.campaigns import IncentiveTopAgent
from services.campaigns.money import (
    allocate_currency_targets,
    allocate_integer_target,
    money,
    money_float,
)


def merge_excluded_units(
    target: dict[tuple[str, str, str], int],
    source: dict[tuple[str, str, str], int],
) -> None:
    for key, units in source.items():
        target[key] = target.get(key, 0) + units


def promo_receipt_totals(
    excluded_units: dict[tuple[str, str, str], int],
) -> tuple[dict[str, int], dict[str, int], dict[str, dict[str, int]]]:
    """Aggregate qualifying promo receipts by store and agent."""
    by_store: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    agent_sites: dict[str, dict[str, int]] = {}
    for (site_code, agent, _item_code), units in excluded_units.items():
        by_store[site_code] = by_store.get(site_code, 0) + units
        if not agent or agent == "-":
            continue
        by_agent[agent] = by_agent.get(agent, 0) + units
        site_weights = agent_sites.setdefault(agent, {})
        site_weights[site_code] = site_weights.get(site_code, 0) + units
    return by_store, by_agent, agent_sites


def excluded_by_period_site_item(
    excluded_units: dict[tuple[str, str, str, str, str], int],
) -> dict[tuple[str, str, str, str], int]:
    """Drop the agent dimension from period-scoped promo exclusions."""
    result: dict[tuple[str, str, str, str], int] = {}
    for period_key, units in excluded_units.items():
        period_start, period_end, site_code, _agent, item_code = period_key
        key = (period_start, period_end, site_code, item_code)
        result[key] = result.get(key, 0) + units
    return result


def period_exclusions(
    snapshot: Any,
    excluded_units: dict[tuple[str, str, str], int],
) -> tuple[dict[tuple[str, str, str, str, str], int], list[str], bool]:
    """Resolve promo exclusions against each immutable incentive mechanism."""
    periods = snapshot.incentive_periods
    result: dict[tuple[str, str, str, str, str], int] = {}
    warnings: list[str] = []
    complete = True
    if len(periods) <= 1:
        for period in periods:
            start = period["valid_from"].isoformat()
            end = period["valid_to"].isoformat()
            for (site_code, agent, item_code), units in excluded_units.items():
                result[(start, end, site_code, agent, item_code)] = units
        return result, warnings, complete

    for period in periods:
        for definition in snapshot.promotion_definitions:
            period_start = max(period["valid_from"], definition["start_date"])
            period_end = min(period["valid_to"], definition["end_date"])
            if period_start > period_end:
                continue
            cache_key = snapshot.campaign_context.period_evaluation_key(
                definition,
                period_start,
                period_end,
            )
            evaluation = snapshot.campaign_context.period_evaluations.get(
                cache_key
            )
            if evaluation is None:
                complete = False
                warnings.append(
                    "Evaluarea promo pentru mecanism nu exista in snapshot."
                )
                continue
            if not evaluation.is_complete:
                complete = False
                warnings.append(
                    evaluation.warning
                    or "Excluderile promo nu pot fi alocate complet pe perioade."
                )
            if not evaluation.is_complete or evaluation.result is None:
                continue
            for (site_code, agent, item_code), units in (
                evaluation.result.excluded_units.items()
            ):
                key = (
                    period["valid_from"].isoformat(),
                    period["valid_to"].isoformat(),
                    site_code,
                    agent,
                    item_code,
                )
                result[key] = result.get(key, 0) + units
    return result, warnings, complete


def build_incentive_agent_rows(
    *,
    snapshot: Any,
    campaign: dict[str, Any],
    campaign_periods: list[dict[str, Any]],
    period_excluded_agent: dict[tuple[str, str, str, str, str], int],
    store_eligible_by_item: dict[tuple[str, str, str, str], int],
    store_reward_by_item: dict[tuple[str, str, str, str], Decimal],
    store_incentives: dict[str, list[Any]],
) -> list[IncentiveTopAgent]:
    """Allocate store incentive quantities and exact currency totals to agents."""
    agent_item_quantities: dict[
        tuple[str, str, str, str], dict[str | None, int]
    ] = {}
    agent_item_rewards: dict[tuple[str, str, str, str], Decimal] = {}
    agent_store_meta: dict[str, tuple[str, str]] = {}
    for row in snapshot.incentive_agent_rows:
        agent = str(row["agent"])
        site_code = str(row["site_code"])
        item_code = str(row["item_code"])
        row_start = row.get("valid_from") or campaign_periods[0]["valid_from"]
        row_end = row.get("valid_to") or campaign_periods[0]["valid_to"]
        period_start = row_start.isoformat()
        period_end = row_end.isoformat()
        excluded = period_excluded_agent.get(
            (period_start, period_end, site_code, agent, item_code),
            0,
        )
        eligible_qty = max(0, int(row["qty"]) - excluded)
        item_key = (period_start, period_end, site_code, item_code)
        quantities = agent_item_quantities.setdefault(item_key, {})
        quantities[agent] = quantities.get(agent, 0) + eligible_qty
        agent_item_rewards[item_key] = money(
            row.get("reward_value")
            or campaign.get("reward_map", {}).get(item_code, 0)
        )
        agent_store_meta[site_code] = (
            str(row["locatie"] or ""),
            str(row["firma"] or ""),
        )

    agent_values: dict[tuple[str, str], Decimal] = {}
    agent_potentials: dict[tuple[str, str], Decimal] = {}
    agent_quantities: dict[tuple[str, str], int] = {}
    item_keys = sorted(set(store_eligible_by_item) | set(agent_item_quantities))
    for item_key in item_keys:
        site_code = item_key[2]
        allocated_quantities = allocate_integer_target(
            agent_item_quantities.get(item_key, {}),
            store_eligible_by_item.get(item_key, 0),
        )
        reward = agent_item_rewards.get(
            item_key,
            store_reward_by_item.get(
                item_key,
                money(campaign.get("reward_map", {}).get(item_key[3], 0)),
            ),
        )
        for allocated_agent, allocated_qty in allocated_quantities.items():
            label = allocated_agent or "Neatribuit"
            agent_key = (site_code, label)
            agent_potential = money(allocated_qty * reward)
            agent_value = money(
                agent_potential
                * Decimal(str(snapshot.store_multipliers.get(site_code, 0)))
            )
            agent_quantities[agent_key] = (
                agent_quantities.get(agent_key, 0) + allocated_qty
            )
            agent_potentials[agent_key] = (
                agent_potentials.get(agent_key, Decimal("0")) + agent_potential
            )
            agent_values[agent_key] = (
                agent_values.get(agent_key, Decimal("0")) + agent_value
            )

    allocated_values = allocate_currency_targets(
        agent_values,
        {site_code: data[1] for site_code, data in store_incentives.items()},
    )
    allocated_potentials = allocate_currency_targets(
        agent_potentials,
        {site_code: data[4] for site_code, data in store_incentives.items()},
    )
    rows: list[IncentiveTopAgent] = []
    for agent_key in agent_values:
        site_code, agent = agent_key
        location, company = agent_store_meta.get(
            site_code,
            (
                str(
                    store_incentives.get(
                        site_code,
                        ["", Decimal("0"), ""],
                    )[0]
                ),
                str(
                    store_incentives.get(
                        site_code,
                        ["", Decimal("0"), ""],
                    )[2]
                ),
            ),
        )
        store_name = (
            f"{site_code} - {location}"
            if site_code and location
            else site_code
        )
        rows.append(
            IncentiveTopAgent(
                agent_name=agent,
                store_name=store_name,
                firma=company,
                qty_sold=agent_quantities[agent_key],
                val_incentive=money_float(allocated_values[agent_key]),
                incentive_potential=money_float(
                    allocated_potentials[agent_key]
                ),
                achievement=snapshot.store_achievements.get(site_code),
            )
        )
    return sorted(rows, key=lambda item: item.val_incentive, reverse=True)
