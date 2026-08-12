"""Co-purchase promotion logic — shared by Hub special card and Focus tab.

Business rule (campania iunie 2026):
  "Cumpara orice accesoriu si beneficiezi de 20% reducere la produsele selectate."
  - La achizitia oricarui accesoriu (non-cartela), clientul primeste -20% la UN
    accesoriu din lista selectata, pe acelasi bon.
  - Reducerea se aplica unui singur produs din lista per bon: cel cu valoarea
    (unit_price) cea mai mica.

Definitia bonului si excluderile sunt identice cu reporting_refresh.py:
  - cheia bonului = (sale_date, site_code, agent, bon_nr)
  - se exclud cartelele (NOT is_cartela) si locatiile de distributie (TR %)
  - se numara doar cantitatile pozitive (vanzari, nu retururi)

Bon calificat = bon cu >=1 produs din lista selectata SI >=2 unitati totale
(a doua unitate poate fi orice alt accesoriu non-cartela, inclusiv a doua bucata
din acelasi produs din lista).

Unitatea redusa (1 per bon calificat) = produsul din lista cu cel mai mic
unit_price pe bon. Aceasta unitate NU se incentiveaza (vezi services/dashboard).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import asyncpg

from business_rules import PROMOTION_DISCOUNT_RATE
from services.dashboard.utils import _expand_current_manager_scope
from domain.filter_scope import FilterInput
from services.filters import build_scoped_params, normalize_filter_values, scoped_clauses
from services.promo_actuals import (
    _load_promo_actuals_material,
    filtered_promo_actuals as _filtered_promo_actuals,
    load_promo_actual_units,
    load_promo_actual_values,
    promo_actuals_cutoff_date,
)
from services.promo_allocation import (
    allocate_units_to_agents as _allocate_units_to_agents,
    allocate_value_to_agents as _allocate_value_to_agents,
)
from services.promo_types import (
    PromoActualsError,
    PromoCoPurchaseResult,
    merge_promo_results,
    result_from_metrics as _result_from_metrics,
)
from services.promo_same_model import (
    same_model_discounted_rows as _same_model_discounted_rows,
    same_model_receipts as _same_model_receipts,
)


def _promo_scope_clauses(
    positions: dict[str, int],
    *,
    site_alias: str,
    agent_alias: str | None,
    current_scope: bool,
    include_closed_stores: bool,
    include_cartela_filter: bool = False,
) -> list[str]:
    clauses = scoped_clauses(
        positions,
        site_alias=site_alias,
        store_alias="s",
        agent_alias=agent_alias,
        include_cartela_filter=include_cartela_filter,
    )
    if current_scope:
        clauses = _expand_current_manager_scope(clauses, positions)
        if not include_closed_stores:
            clauses.append("s.is_active = true")
    return clauses


def _agent_filter_values(agent: FilterInput) -> set[str] | None:
    normalized = normalize_filter_values(agent)
    return set(normalized) if normalized else None


def _actual_source_vectors(
    actual_units: dict[tuple[str, str], int],
) -> tuple[list[str], list[str], list[int]]:
    sites: list[str] = []
    codes: list[str] = []
    units: list[int] = []
    for (site_code, item_code), quantity in sorted(actual_units.items()):
        sites.append(site_code)
        codes.append(item_code)
        units.append(int(quantity))
    return sites, codes, units


def _actual_candidate_rows(
    rows: list[Any],
    actual_values: dict[tuple[str, str], Decimal],
) -> tuple[
    dict[tuple[str, str], int],
    dict[tuple[str, str], Decimal],
    dict[tuple[str, str], list[tuple[str, int]]],
]:
    scoped_units: dict[tuple[str, str], int] = {}
    scoped_values: dict[tuple[str, str], Decimal] = {}
    candidates: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for row in rows:
        key = (str(row["site_code"]), str(row["item_code"]))
        scoped_units[key] = int(row["promo_units"] or 0)
        scoped_values[key] = actual_values.get(key, Decimal("0"))
        agent_name = row["agent"]
        positive_qty = int(row["positive_qty"] or 0)
        if agent_name and positive_qty > 0:
            candidates.setdefault(key, []).append((str(agent_name), positive_qty))
    return scoped_units, scoped_values, candidates


def _allocated_actual_result(
    *,
    scoped_units: dict[tuple[str, str], int],
    scoped_values: dict[tuple[str, str], Decimal],
    candidates: dict[tuple[str, str], list[tuple[str, int]]],
    allowed_agents: set[str] | None,
    discount_rate: Decimal,
) -> PromoCoPurchaseResult:
    excluded_units: dict[tuple[str, str, str], int] = {}
    excluded_values: dict[tuple[str, str, str], Decimal] = {}
    for (site, item), units in scoped_units.items():
        allocations = _allocate_units_to_agents(
            units,
            candidates.get((site, item), []),
        )
        allocated_values = _allocate_value_to_agents(
            scoped_values.get((site, item), Decimal("0")) * discount_rate,
            allocations,
        )
        for agent_name, allocated_units in allocations:
            if allowed_agents is not None and agent_name not in allowed_agents:
                continue
            key = (site, agent_name, item)
            excluded_units[key] = excluded_units.get(key, 0) + allocated_units
            excluded_values[key] = (
                excluded_values.get(key, Decimal("0"))
                + allocated_values.get(agent_name, Decimal("0"))
            )
    return _result_from_metrics(excluded_units, excluded_values)


async def compute_promo_actuals_from_report(
    conn: asyncpg.Connection,
    *,
    month: str,
    definition: dict[str, Any],
    item_codes: list[str],
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    discount_rate: Decimal = PROMOTION_DISCOUNT_RATE,
) -> PromoCoPurchaseResult | None:
    """Return POS-confirmed promo units from report, or None when not configured.

    `None` means callers should fall back to the rule-based bon calculator.
    An empty result means a configured source report explicitly has no promo
    units for this promotion and scope.
    """
    material = _filtered_promo_actuals(definition, item_codes)
    if material is None:
        return None
    actual_units, actual_values = material
    if not actual_units:
        return PromoCoPurchaseResult()

    source_sites, source_codes, source_units = _actual_source_vectors(actual_units)
    start_date = definition["start_date"]
    end_date = definition["end_date"]
    cutoff_date = promo_actuals_cutoff_date(definition)
    if cutoff_date is None:
        cutoff_date = end_date
    cutoff_date = min(cutoff_date, end_date)
    if cutoff_date < start_date:
        return PromoCoPurchaseResult()

    params, positions = build_scoped_params(
        [month, source_sites, source_codes, source_units, start_date, cutoff_date],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=None,
    )
    scope = _promo_scope_clauses(
        positions,
        site_alias="a",
        agent_alias=None,
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
    )
    scoped_where = " AND ".join(scope)
    rows = await conn.fetch(
        f"""
        WITH actuals AS (
            SELECT site_code, item_code, promo_units
            FROM UNNEST($2::TEXT[], $3::TEXT[], $4::INT[])
                AS t(site_code, item_code, promo_units)
        ),
        scoped_actuals AS (
            SELECT a.site_code, a.item_code, a.promo_units
            FROM actuals a
            JOIN stores s ON s.site_code = a.site_code
            WHERE {scoped_where}
        )
        SELECT
            sa.site_code,
            sa.item_code,
            sa.promo_units,
            agg.agent,
            COALESCE(SUM(agg.positive_quantity), 0)::INT AS positive_qty
        FROM scoped_actuals sa
        LEFT JOIN reporting_item_day agg
          ON agg.import_month = $1
         AND agg.site_code = sa.site_code
         AND agg.item_code = sa.item_code
         AND agg.sale_date BETWEEN $5 AND $6
        GROUP BY sa.site_code, sa.item_code, sa.promo_units, agg.agent
        """,
        *params,
    )

    scoped_units, scoped_values, candidates = _actual_candidate_rows(
        rows,
        actual_values,
    )
    return _allocated_actual_result(
        scoped_units=scoped_units,
        scoped_values=scoped_values,
        candidates=candidates,
        allowed_agents=_agent_filter_values(agent),
        discount_rate=discount_rate,
    )


async def compute_promo_copurchase(
    conn: asyncpg.Connection,
    *,
    month: str,
    start_date: date,
    end_date: date,
    item_codes: list[str],
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    discount_rate: Decimal = PROMOTION_DISCOUNT_RATE,
) -> PromoCoPurchaseResult:
    """Calculeaza bonurile calificate + unitatile reduse pentru promotia co-purchase.

    Returneaza un PromoCoPurchaseResult gol daca nu exista coduri sau date.
    """
    if not item_codes:
        return PromoCoPurchaseResult()

    params, positions = build_scoped_params(
        [month, start_date, end_date, item_codes],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    # scoped_clauses adauga: TR% exclude, NOT st.is_cartela, si clauzele de scope.
    scope = _promo_scope_clauses(
        positions,
        site_alias="st",
        agent_alias="st",
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        include_cartela_filter=True,
    )
    scope_sql = "".join(f"\n              AND {clause}" for clause in scope)

    rows = await conn.fetch(
        f"""
        WITH lines AS (
            SELECT
                st.sale_date,
                st.site_code,
                st.agent,
                st.bon_nr,
                st.id,
                st.item_code,
                st.unit_price,
                CASE WHEN st.quantity > 0 THEN st.quantity ELSE 0 END AS pos_qty,
                (st.item_code = ANY($4::TEXT[])) AS is_selected
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            WHERE st.import_month = $1
              AND st.sale_date BETWEEN $2 AND $3
              AND NOT st.is_return
              {scope_sql}
        ),
        bon_totals AS (
            SELECT
                sale_date, site_code, agent, bon_nr,
                SUM(pos_qty) AS total_units,
                SUM(pos_qty) FILTER (WHERE is_selected) AS selected_units
            FROM lines
            GROUP BY sale_date, site_code, agent, bon_nr
        ),
        qualifying AS (
            SELECT sale_date, site_code, agent, bon_nr
            FROM bon_totals
            WHERE selected_units >= 1 AND total_units >= 2
        ),
        discounted AS (
            SELECT DISTINCT ON (l.sale_date, l.site_code, l.agent, l.bon_nr)
                l.site_code, l.agent, l.item_code, l.unit_price
            FROM lines l
            JOIN qualifying q
              ON q.sale_date = l.sale_date
             AND q.site_code = l.site_code
             AND q.agent = l.agent
             AND q.bon_nr = l.bon_nr
            WHERE l.is_selected AND l.pos_qty > 0
            ORDER BY
                l.sale_date, l.site_code, l.agent, l.bon_nr,
                l.unit_price ASC, l.item_code ASC, l.id ASC
        )
        SELECT
            site_code,
            agent,
            item_code,
            COUNT(*)::INT AS units,
            COALESCE(SUM(unit_price), 0) AS gross_value
        FROM discounted
        GROUP BY site_code, agent, item_code
        """,
        *params,
    )

    return _result_from_discounted_rows(rows, discount_rate=discount_rate)


async def compute_promo_trigger_discounted(
    conn: asyncpg.Connection,
    *,
    month: str,
    start_date: date,
    end_date: date,
    trigger_codes: list[str],
    discounted_codes: list[str],
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    discount_rate: Decimal = PROMOTION_DISCOUNT_RATE,
) -> PromoCoPurchaseResult:
    """Calculeaza bonuri cu produs declansator + produs redus pe acelasi bon.

    Folosit pentru campanii de tip capac Cellara + husa universala Cellara.
    Unitatea redusa este cel mai ieftin produs din lista redusa, maxim una per bon.
    """
    if not trigger_codes or not discounted_codes:
        return PromoCoPurchaseResult()

    params, positions = build_scoped_params(
        [month, start_date, end_date, trigger_codes, discounted_codes],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    scope = _promo_scope_clauses(
        positions,
        site_alias="st",
        agent_alias="st",
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        include_cartela_filter=True,
    )
    scope_sql = "".join(f"\n              AND {clause}" for clause in scope)

    rows = await conn.fetch(
        f"""
        WITH lines AS (
            SELECT
                st.sale_date,
                st.site_code,
                st.agent,
                st.bon_nr,
                st.id,
                st.item_code,
                st.unit_price,
                CASE WHEN st.quantity > 0 THEN st.quantity ELSE 0 END AS pos_qty,
                (st.item_code = ANY($4::TEXT[])) AS is_trigger,
                (st.item_code = ANY($5::TEXT[])) AS is_discounted
            FROM sales_transactions st
            JOIN stores s ON s.site_code = st.site_code
            WHERE st.import_month = $1
              AND st.sale_date BETWEEN $2 AND $3
              AND NOT st.is_return
              AND (
                st.item_code = ANY($4::TEXT[])
                OR st.item_code = ANY($5::TEXT[])
              ){scope_sql}
        ),
        bon_totals AS (
            SELECT
                sale_date, site_code, agent, bon_nr,
                SUM(pos_qty) FILTER (WHERE is_trigger) AS trigger_units,
                SUM(pos_qty) FILTER (WHERE is_discounted) AS discounted_units
            FROM lines
            GROUP BY sale_date, site_code, agent, bon_nr
        ),
        qualifying AS (
            SELECT sale_date, site_code, agent, bon_nr
            FROM bon_totals
            WHERE trigger_units >= 1 AND discounted_units >= 1
        ),
        discounted AS (
            SELECT DISTINCT ON (l.sale_date, l.site_code, l.agent, l.bon_nr)
                l.site_code, l.agent, l.item_code, l.unit_price
            FROM lines l
            JOIN qualifying q
              ON q.sale_date = l.sale_date
             AND q.site_code = l.site_code
             AND q.agent = l.agent
             AND q.bon_nr = l.bon_nr
            WHERE l.is_discounted AND l.pos_qty > 0
            ORDER BY
                l.sale_date, l.site_code, l.agent, l.bon_nr,
                l.unit_price ASC, l.item_code ASC, l.id ASC
        )
        SELECT
            site_code,
            agent,
            item_code,
            COUNT(*)::INT AS units,
            COALESCE(SUM(unit_price), 0) AS gross_value
        FROM discounted
        GROUP BY site_code, agent, item_code
        """,
        *params,
    )

    return _result_from_discounted_rows(rows, discount_rate=discount_rate)


async def compute_promo_same_model_pair(
    conn: asyncpg.Connection,
    *,
    month: str,
    start_date: date,
    end_date: date,
    screen_code_models: dict[str, set[str]],
    camera_code_models: dict[str, set[str]],
    firma: FilterInput,
    regional: FilterInput,
    asm: FilterInput,
    site_code: FilterInput,
    agent: FilterInput,
    current_scope: bool = False,
    include_closed_stores: bool = False,
    discount_rate: Decimal = PROMOTION_DISCOUNT_RATE,
) -> PromoCoPurchaseResult:
    """Calculeaza bonuri cu folie ecran + folie camera pentru acelasi model.

    Un cod poate participa la mai multe modele compatibile. Bonul se califica
    daca exista cel putin o intersectie de model intre produsele de ecran si
    cele de camera de pe bon.
    """
    screen_pairs = [
        (code, model)
        for code, models in screen_code_models.items()
        for model in sorted(models)
    ]
    camera_pairs = [
        (code, model)
        for code, models in camera_code_models.items()
        for model in sorted(models)
    ]
    if not screen_pairs or not camera_pairs:
        return PromoCoPurchaseResult()

    screen_codes = sorted(screen_code_models)
    camera_codes = sorted(camera_code_models)

    params, positions = build_scoped_params(
        [month, start_date, end_date, screen_codes, camera_codes],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    scope = _promo_scope_clauses(
        positions,
        site_alias="st",
        agent_alias="st",
        current_scope=current_scope,
        include_closed_stores=include_closed_stores,
        include_cartela_filter=True,
    )
    scope_sql = "".join(f"\n              AND {clause}" for clause in scope)

    rows = await conn.fetch(
        f"""
        SELECT
            st.sale_date,
            st.site_code,
            st.agent,
            st.bon_nr,
            st.id,
            st.item_code,
            st.unit_price,
            st.quantity
        FROM sales_transactions st
        JOIN stores s ON s.site_code = st.site_code
        WHERE st.import_month = $1
          AND st.sale_date BETWEEN $2 AND $3
          AND NOT st.is_return
          AND (
            st.item_code = ANY($4::TEXT[])
            OR st.item_code = ANY($5::TEXT[])
          ){scope_sql}
        """,
        *params,
    )

    receipts = _same_model_receipts(
        rows,
        screen_code_models,
        camera_code_models,
    )
    discounted_rows = _same_model_discounted_rows(receipts)
    return _result_from_discounted_rows(
        discounted_rows,
        discount_rate=discount_rate,
    )


def _result_from_discounted_rows(
    rows: list[Any],
    *,
    discount_rate: Decimal = PROMOTION_DISCOUNT_RATE,
) -> PromoCoPurchaseResult:
    excluded_units: dict[tuple[str, str, str], int] = {}
    excluded_discount_values: dict[tuple[str, str, str], Decimal] = {}
    for row in rows:
        units = int(row["units"])
        key = (str(row["site_code"]), str(row["agent"]), str(row["item_code"]))
        excluded_units[key] = units
        gross_value = Decimal(str(row.get("gross_value") or 0))
        excluded_discount_values[key] = (gross_value * discount_rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    return _result_from_metrics(
        excluded_units,
        excluded_discount_values,
    )
