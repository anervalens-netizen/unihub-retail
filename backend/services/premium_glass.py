from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from domain.filter_scope import FilterInput
from schemas.dashboard import (
    DashboardSpecialCard,
    DashboardSpecialCardMetric,
)
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
from services.dashboard.utils import _expand_current_manager_scope
from services.filters import build_scoped_params, scoped_clauses


def _format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _format_pct(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1f}%"


def _premium_scope(
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    surface: Literal["all", "screen", "camera"],
    *,
    current_scope: bool,
    include_closed_stores: bool,
) -> tuple[list[str], list[Any]]:
    params, positions = build_scoped_params(
        [month],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    clauses = scoped_clauses(
        positions,
        site_alias="st",
        store_alias="s",
        agent_alias="st",
        month_alias="st.import_month",
        month_position=1,
        include_cartela_filter=True,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
    if current_scope and not include_closed_stores:
        clauses.append("s.is_active = true")
    clauses.extend(
        [
            "LOWER(TRIM(COALESCE(st.category, ''))) = 'folii sticla'",
            "st.quantity > 0",
            "st.agent NOT ILIKE 'TR%'",
        ]
    )
    if surface == "camera":
        clauses.append("st.item_name ILIKE '%CAMERA%'")
    elif surface == "screen":
        clauses.append("st.item_name NOT ILIKE '%CAMERA%'")
    return clauses, params


def _premium_base_cte(where_sql: str) -> str:
    return f"""
        WITH base_lines AS (
            SELECT
                st.id,
                st.item_code,
                st.item_name,
                st.site_code,
                s.locatie,
                s.firma,
                COALESCE(NULLIF(TRIM(s.regional), ''), NULLIF(TRIM(s.asm), ''), 'Fara manager') AS manager,
                st.agent,
                pgm.is_premium_glass AS is_premium,
                pgm.model_key,
                pgm.model_label,
                st.quantity::INT AS qty,
                st.total_value AS sales
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            JOIN premium_glass_item_models pgm ON pgm.item_code = st.item_code
            WHERE {where_sql}
        ),
        matched_lines AS (
            SELECT *
            FROM base_lines
        ),
        eligible_lines AS (
            SELECT DISTINCT
                id,
                item_code,
                item_name,
                site_code,
                locatie,
                firma,
                manager,
                agent,
                is_premium,
                qty,
                sales
            FROM matched_lines
        )
    """


def _zero_split_bucket() -> dict[str, Any]:
    return {
        "premium_qty": 0,
        "regular_qty": 0,
        "total_qty": 0,
        "premium_sales": Decimal(0),
        "regular_sales": Decimal(0),
        "total_sales": Decimal(0),
    }


def _add_split(bucket: dict[str, Any], qty: int, sales: Decimal, is_premium: bool) -> None:
    bucket["total_qty"] += qty
    bucket["total_sales"] += sales
    if is_premium:
        bucket["premium_qty"] += qty
        bucket["premium_sales"] += sales
    else:
        bucket["regular_qty"] += qty
        bucket["regular_sales"] += sales


def _share_pct(part: int | Decimal, total: int | Decimal) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(part) * Decimal(100) / Decimal(total)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def _surface_for_item(item_name: str) -> tuple[str, str]:
    if "CAMERA" in item_name.upper():
        return "camera", "Camera"
    return "screen", "Ecran"


def _deduplicate_eligible_rows(rows: list[Any]) -> list[Any]:
    return list({
        (
            row["id"],
            row["item_code"],
            row["item_name"],
            row["site_code"],
            row["locatie"],
            row["firma"],
            row["manager"],
            row["agent"],
            row["is_premium"],
            row["qty"],
            row["sales"],
        ): row
        for row in rows
    }.values())


async def get_premium_glass_analysis(
    conn: Any,
    month: str,
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: FilterInput,
    agent: FilterInput,
    surface: Literal["all", "screen", "camera"] = "all",
    *,
    current_scope: bool = True,
    include_closed_stores: bool = False,
) -> PremiumGlassAnalysis:
    clauses, params = _premium_scope(
        month,
        firma,
        regional,
        asm,
        site_code,
        agent,
        surface,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    cte = _premium_base_cte(" AND ".join(clauses))

    matched_rows = await conn.fetch(
        f"""
        {cte}
        SELECT
            id,
            item_code,
            item_name,
            site_code,
            locatie,
            firma,
            manager,
            agent,
            is_premium,
            model_key,
            model_label,
            qty,
            sales
        FROM matched_lines
        """,
        *params,
    )
    target_model_count = int(
        await conn.fetchval(
            "SELECT COUNT(DISTINCT model_key)::INT FROM premium_glass_item_models"
        )
        or 0
    )

    eligible_rows = _deduplicate_eligible_rows(matched_rows)

    summary_bucket = _zero_split_bucket()
    active_stores: set[str] = set()
    active_agents: set[str] = set()
    premium_active_stores: set[str] = set()
    premium_active_agents: set[str] = set()

    model_buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(_zero_split_bucket)
    store_buckets: dict[str, dict[str, Any]] = {}
    surface_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    manager_buckets: dict[str, dict[str, Any]] = {}
    agent_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    product_buckets: dict[str, dict[str, Any]] = {}
    product_models: dict[str, set[str]] = defaultdict(set)

    for row in matched_rows:
        qty = int(row["qty"] or 0)
        sales = row["sales"] or Decimal(0)
        is_premium = bool(row["is_premium"])
        model_key = str(row["model_key"])
        model_label = str(row["model_label"])
        item_code = str(row["item_code"])

        model_bucket = model_buckets[(model_key, model_label)]
        _add_split(model_bucket, qty, sales, is_premium)
        premium_items = model_bucket.setdefault("premium_items", set())
        regular_items = model_bucket.setdefault("regular_items", set())
        if is_premium:
            premium_items.add(item_code)
        else:
            regular_items.add(item_code)
        product_models[item_code].add(model_label)

    for row in eligible_rows:
        qty = int(row["qty"] or 0)
        sales = row["sales"] or Decimal(0)
        is_premium = bool(row["is_premium"])
        site_code = str(row["site_code"])
        agent_name = str(row["agent"])
        manager = str(row["manager"])
        item_code = str(row["item_code"])
        surface_key, surface_label = _surface_for_item(str(row["item_name"]))

        _add_split(summary_bucket, qty, sales, is_premium)
        active_stores.add(site_code)
        active_agents.add(agent_name)
        if is_premium:
            premium_active_stores.add(site_code)
            premium_active_agents.add(agent_name)

        surface_bucket = surface_buckets.setdefault(
            (surface_key, surface_label),
            {
                **_zero_split_bucket(),
                "surface_key": surface_key,
                "surface_label": surface_label,
            },
        )
        _add_split(surface_bucket, qty, sales, is_premium)

        store_bucket = store_buckets.setdefault(
            site_code,
            {
                **_zero_split_bucket(),
                "site_code": site_code,
                "locatie": str(row["locatie"]),
                "firma": str(row["firma"]),
            },
        )
        _add_split(store_bucket, qty, sales, is_premium)

        manager_bucket = manager_buckets.setdefault(
            manager,
            {
                **_zero_split_bucket(),
                "manager": manager,
                "stores": set(),
                "agents": set(),
            },
        )
        _add_split(manager_bucket, qty, sales, is_premium)
        manager_bucket["stores"].add(site_code)
        manager_bucket["agents"].add(agent_name)

        agent_bucket = agent_buckets.setdefault(
            (agent_name, site_code),
            {
                **_zero_split_bucket(),
                "agent": agent_name,
                "site_code": site_code,
                "locatie": str(row["locatie"]),
                "firma": str(row["firma"]),
            },
        )
        _add_split(agent_bucket, qty, sales, is_premium)

        product_bucket = product_buckets.setdefault(
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
        product_bucket["is_premium"] = bool(product_bucket["is_premium"] or is_premium)
        product_bucket["qty"] += qty
        product_bucket["sales"] += sales
        product_bucket["stores"].add(site_code)

    summary = PremiumGlassSummary(
        month=month,
        total_qty=summary_bucket["total_qty"],
        total_sales=summary_bucket["total_sales"],
        premium_qty=summary_bucket["premium_qty"],
        premium_sales=summary_bucket["premium_sales"],
        regular_qty=summary_bucket["regular_qty"],
        regular_sales=summary_bucket["regular_sales"],
        premium_qty_share_pct=_share_pct(
            summary_bucket["premium_qty"], summary_bucket["total_qty"]
        ),
        premium_sales_share_pct=_share_pct(
            summary_bucket["premium_sales"], summary_bucket["total_sales"]
        ),
        active_stores=len(active_stores),
        active_agents=len(active_agents),
        premium_active_stores=len(premium_active_stores),
        premium_active_agents=len(premium_active_agents),
        target_model_count=target_model_count,
    )

    model_rows = [
        {
            **{name: value for name, value in bucket.items() if name not in {"premium_items", "regular_items"}},
            "model_key": key[0],
            "model_label": key[1],
            "premium_qty_share_pct": _share_pct(bucket["premium_qty"], bucket["total_qty"]),
            "premium_item_count": len(bucket.get("premium_items", set())),
            "regular_item_count": len(bucket.get("regular_items", set())),
        }
        for key, bucket in model_buckets.items()
    ]
    store_rows = [
        {
            **{name: value for name, value in bucket.items() if name not in {"stores", "agents"}},
            "premium_qty_share_pct": _share_pct(bucket["premium_qty"], bucket["total_qty"]),
        }
        for bucket in store_buckets.values()
    ]
    surface_rows = [
        {
            **{name: value for name, value in bucket.items() if name != "stores"},
            "premium_qty_share_pct": _share_pct(bucket["premium_qty"], bucket["total_qty"]),
        }
        for bucket in surface_buckets.values()
    ]
    manager_rows = [
        {
            **{name: value for name, value in bucket.items() if name not in {"stores", "agents"}},
            "premium_qty_share_pct": _share_pct(bucket["premium_qty"], bucket["total_qty"]),
            "store_count": len(bucket["stores"]),
            "agent_count": len(bucket["agents"]),
        }
        for bucket in manager_buckets.values()
    ]
    agent_rows = [
        {
            **bucket,
            "premium_qty_share_pct": _share_pct(bucket["premium_qty"], bucket["total_qty"]),
        }
        for bucket in agent_buckets.values()
    ]
    product_rows = [
        {
            **{name: value for name, value in bucket.items() if name != "stores"},
            "model_labels": sorted(product_models[bucket["item_code"]]),
            "store_count": len(bucket["stores"]),
        }
        for bucket in product_buckets.values()
    ]

    model_rows.sort(key=lambda r: (-r["total_qty"], r["model_label"]))
    surface_rows.sort(key=lambda r: (0 if r["surface_key"] == "screen" else 1, r["surface_label"]))
    store_rows.sort(key=lambda r: (-r["premium_qty"], -r["total_qty"], r["locatie"]))
    manager_rows.sort(key=lambda r: (-r["premium_qty"], -r["total_qty"], r["manager"]))
    agent_rows.sort(key=lambda r: (-r["premium_qty"], -r["total_qty"], r["agent"]))
    product_rows.sort(key=lambda r: (-r["qty"], -r["sales"], r["item_name"]))

    return PremiumGlassAnalysis(
        summary=summary,
        models=[PremiumGlassModelStat(**row) for row in model_rows],
        surfaces=[PremiumGlassSurfaceStat(**row) for row in surface_rows],
        managers=[PremiumGlassManagerStat(**row) for row in manager_rows],
        stores=[PremiumGlassStoreStat(**row) for row in store_rows],
        agents=[PremiumGlassAgentStat(**row) for row in agent_rows],
        products=[PremiumGlassProductStat(**row) for row in product_rows[:12]],
    )


def build_premium_glass_card(analysis: PremiumGlassAnalysis) -> DashboardSpecialCard:
    summary = analysis.summary
    has_data = summary.total_qty > 0
    return DashboardSpecialCard(
        key="premium_glass",
        title="Folii Premium",
        subtitle="SAPPHIRE, CERAMIC si CORNING pentru ecran + camera premium din lista operationala",
        status="ready" if has_data else "no_data",
        status_label="Activ" if has_data else "Fara date",
        highlight_value=_format_int(summary.premium_qty),
        description="Compara foliile premium cu restul foliilor de sticla pentru aceleasi modele tinta.",
        coverage_note=(
            "Modele: iPhone 15/16/17 si Samsung S26, cu variantele eligibile din lista operationala."
        ),
        metrics=[
            DashboardSpecialCardMetric(label="Premium", value=_format_int(summary.premium_qty)),
            DashboardSpecialCardMetric(label="Rest", value=_format_int(summary.regular_qty)),
            DashboardSpecialCardMetric(
                label="Share cant.",
                value=_format_pct(summary.premium_qty_share_pct),
            ),
            DashboardSpecialCardMetric(
                label="Magazine premium",
                value=_format_int(summary.premium_active_stores),
            ),
        ],
    )
