"""Pure aggregation for premium-glass reporting rows."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from schemas.premium_glass import (
    PremiumGlassAgentStat,
    PremiumGlassAnalysis,
    PremiumGlassManagerStat,
    PremiumGlassModelStat,
    PremiumGlassProductStat,
    PremiumGlassStoreStat,
    PremiumGlassSummary,
    PremiumGlassSurfaceStat,
)


Bucket = dict[str, Any]
AddSplit = Callable[[Bucket, int, Decimal, bool], None]
Share = Callable[[int | Decimal, int | Decimal], Decimal | None]
Surface = Callable[[str], tuple[str, str]]


@dataclass
class AggregationState:
    summary: Bucket
    active_stores: set[str] = field(default_factory=set)
    active_agents: set[str] = field(default_factory=set)
    premium_active_stores: set[str] = field(default_factory=set)
    premium_active_agents: set[str] = field(default_factory=set)
    models: dict[tuple[str, str], Bucket] = field(default_factory=dict)
    stores: dict[str, Bucket] = field(default_factory=dict)
    surfaces: dict[tuple[str, str], Bucket] = field(default_factory=dict)
    managers: dict[str, Bucket] = field(default_factory=dict)
    agents: dict[tuple[str, str], Bucket] = field(default_factory=dict)
    products: dict[str, Bucket] = field(default_factory=dict)
    product_models: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))


def build_analysis(
    rows: list[Any],
    eligible_rows: list[Any],
    *,
    month: str,
    target_model_count: int,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    share_pct: Share,
    surface_for_item: Surface,
) -> PremiumGlassAnalysis:
    state = AggregationState(summary=zero_bucket())
    _aggregate_models(rows, state, zero_bucket, add_split)
    for row in eligible_rows:
        _aggregate_eligible(row, state, zero_bucket, add_split, surface_for_item)
    return _build_analysis(state, month, target_model_count, share_pct)


def _aggregate_models(
    rows: list[Any],
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
) -> None:
    for row in rows:
        model_key = (str(row["model_key"]), str(row["model_label"]))
        bucket = state.models.setdefault(model_key, zero_bucket())
        item_code = str(row["item_code"])
        is_premium = bool(row["is_premium"])
        add_split(bucket, int(row["qty"] or 0), row["sales"] or Decimal(0), is_premium)
        collection = "premium_items" if is_premium else "regular_items"
        bucket.setdefault(collection, set()).add(item_code)
        state.product_models[item_code].add(model_key[1])


def _aggregate_eligible(
    row: Any,
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    surface_for_item: Surface,
) -> None:
    qty = int(row["qty"] or 0)
    sales = row["sales"] or Decimal(0)
    premium = bool(row["is_premium"])
    site = str(row["site_code"])
    agent = str(row["agent"])
    manager = str(row["manager"])
    item_code = str(row["item_code"])
    add_split(state.summary, qty, sales, premium)
    state.active_stores.add(site)
    state.active_agents.add(agent)
    if premium:
        state.premium_active_stores.add(site)
        state.premium_active_agents.add(agent)
    _surface_bucket(row, state, zero_bucket, add_split, surface_for_item, qty, sales, premium)
    _store_bucket(row, state, zero_bucket, add_split, site, qty, sales, premium)
    _manager_bucket(state, zero_bucket, add_split, manager, site, agent, qty, sales, premium)
    _agent_bucket(row, state, zero_bucket, add_split, agent, site, qty, sales, premium)
    _product_bucket(row, state, item_code, site, qty, sales, premium)


def _surface_bucket(
    row: Any,
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    surface_for_item: Surface,
    qty: int,
    sales: Decimal,
    premium: bool,
) -> None:
    key, label = surface_for_item(str(row["item_name"]))
    bucket = state.surfaces.setdefault(
        (key, label),
        {**zero_bucket(), "surface_key": key, "surface_label": label},
    )
    add_split(bucket, qty, sales, premium)


def _store_bucket(
    row: Any,
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    site: str,
    qty: int,
    sales: Decimal,
    premium: bool,
) -> None:
    bucket = state.stores.setdefault(
        site,
        {
            **zero_bucket(),
            "site_code": site,
            "locatie": str(row["locatie"]),
            "firma": str(row["firma"]),
        },
    )
    add_split(bucket, qty, sales, premium)


def _manager_bucket(
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    manager: str,
    site: str,
    agent: str,
    qty: int,
    sales: Decimal,
    premium: bool,
) -> None:
    bucket = state.managers.setdefault(
        manager,
        {**zero_bucket(), "manager": manager, "stores": set(), "agents": set()},
    )
    add_split(bucket, qty, sales, premium)
    bucket["stores"].add(site)
    bucket["agents"].add(agent)


def _agent_bucket(
    row: Any,
    state: AggregationState,
    zero_bucket: Callable[[], Bucket],
    add_split: AddSplit,
    agent: str,
    site: str,
    qty: int,
    sales: Decimal,
    premium: bool,
) -> None:
    bucket = state.agents.setdefault(
        (agent, site),
        {
            **zero_bucket(),
            "agent": agent,
            "site_code": site,
            "locatie": str(row["locatie"]),
            "firma": str(row["firma"]),
        },
    )
    add_split(bucket, qty, sales, premium)


def _product_bucket(
    row: Any,
    state: AggregationState,
    item_code: str,
    site: str,
    qty: int,
    sales: Decimal,
    premium: bool,
) -> None:
    bucket = state.products.setdefault(
        item_code,
        {
            "item_code": item_code,
            "item_name": str(row["item_name"]),
            "is_premium": False,
            "qty": 0,
            "sales": Decimal(0),
            "stores": set(),
        },
    )
    bucket["is_premium"] = bool(bucket["is_premium"] or premium)
    bucket["qty"] += qty
    bucket["sales"] += sales
    bucket["stores"].add(site)


def _build_analysis(
    state: AggregationState,
    month: str,
    target_model_count: int,
    share_pct: Share,
) -> PremiumGlassAnalysis:
    summary = _summary(state, month, target_model_count, share_pct)
    model_rows = _model_rows(state, share_pct)
    surface_rows = _split_rows(state.surfaces.values(), share_pct)
    store_rows = _split_rows(state.stores.values(), share_pct)
    manager_rows = _manager_rows(state, share_pct)
    agent_rows = _split_rows(state.agents.values(), share_pct)
    product_rows = _product_rows(state)
    model_rows.sort(key=lambda row: (-row["total_qty"], row["model_label"]))
    surface_rows.sort(key=lambda row: (row["surface_key"] != "screen", row["surface_label"]))
    store_rows.sort(key=lambda row: (-row["premium_qty"], -row["total_qty"], row["locatie"]))
    manager_rows.sort(key=lambda row: (-row["premium_qty"], -row["total_qty"], row["manager"]))
    agent_rows.sort(key=lambda row: (-row["premium_qty"], -row["total_qty"], row["agent"]))
    product_rows.sort(key=lambda row: (-row["qty"], -row["sales"], row["item_name"]))
    return PremiumGlassAnalysis(
        summary=summary,
        models=[PremiumGlassModelStat(**row) for row in model_rows],
        surfaces=[PremiumGlassSurfaceStat(**row) for row in surface_rows],
        managers=[PremiumGlassManagerStat(**row) for row in manager_rows],
        stores=[PremiumGlassStoreStat(**row) for row in store_rows],
        agents=[PremiumGlassAgentStat(**row) for row in agent_rows],
        products=[PremiumGlassProductStat(**row) for row in product_rows[:12]],
    )


def _summary(
    state: AggregationState,
    month: str,
    target_model_count: int,
    share_pct: Share,
) -> PremiumGlassSummary:
    bucket = state.summary
    return PremiumGlassSummary(
        month=month,
        total_qty=bucket["total_qty"],
        total_sales=bucket["total_sales"],
        premium_qty=bucket["premium_qty"],
        premium_sales=bucket["premium_sales"],
        regular_qty=bucket["regular_qty"],
        regular_sales=bucket["regular_sales"],
        premium_qty_share_pct=share_pct(bucket["premium_qty"], bucket["total_qty"]),
        premium_sales_share_pct=share_pct(bucket["premium_sales"], bucket["total_sales"]),
        active_stores=len(state.active_stores),
        active_agents=len(state.active_agents),
        premium_active_stores=len(state.premium_active_stores),
        premium_active_agents=len(state.premium_active_agents),
        target_model_count=target_model_count,
    )


def _model_rows(state: AggregationState, share_pct: Share) -> list[Bucket]:
    rows: list[Bucket] = []
    for key, bucket in state.models.items():
        rows.append(
            {
                **_without(bucket, {"premium_items", "regular_items"}),
                "model_key": key[0],
                "model_label": key[1],
                "premium_qty_share_pct": share_pct(bucket["premium_qty"], bucket["total_qty"]),
                "premium_item_count": len(bucket.get("premium_items", set())),
                "regular_item_count": len(bucket.get("regular_items", set())),
            }
        )
    return rows


def _split_rows(buckets: Any, share_pct: Share) -> list[Bucket]:
    return [
        {
            **_without(bucket, {"stores", "agents"}),
            "premium_qty_share_pct": share_pct(bucket["premium_qty"], bucket["total_qty"]),
        }
        for bucket in buckets
    ]


def _manager_rows(state: AggregationState, share_pct: Share) -> list[Bucket]:
    return [
        {
            **_without(bucket, {"stores", "agents"}),
            "premium_qty_share_pct": share_pct(bucket["premium_qty"], bucket["total_qty"]),
            "store_count": len(bucket["stores"]),
            "agent_count": len(bucket["agents"]),
        }
        for bucket in state.managers.values()
    ]


def _product_rows(state: AggregationState) -> list[Bucket]:
    return [
        {
            **_without(bucket, {"stores"}),
            "model_labels": sorted(state.product_models[bucket["item_code"]]),
            "store_count": len(bucket["stores"]),
        }
        for bucket in state.products.values()
    ]


def _without(bucket: Bucket, names: set[str]) -> Bucket:
    return {name: value for name, value in bucket.items() if name not in names}
