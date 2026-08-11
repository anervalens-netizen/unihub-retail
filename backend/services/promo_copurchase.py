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

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

import asyncpg

from business_rules import PROMOTION_DISCOUNT_RATE
from services.dashboard.utils import _expand_current_manager_scope
from domain.filter_scope import FilterInput
from services.filters import build_scoped_params, normalize_filter_values, scoped_clauses
from services.product_lists import get_repo_root, resolve_path


PromoActualUnitsLoadResult = tuple[dict[tuple[str, str], int] | None, str | None]

_promo_actuals_cache: dict[
    tuple[str, int, str, int, str, str],
    tuple[
        dict[tuple[str, str], int] | None,
        dict[tuple[str, str], Decimal] | None,
        str | None,
    ],
] = {}
_MONEY_QUANTUM = Decimal("0.01")


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


class PromoActualsError(RuntimeError):
    """Raised when a configured POS actuals report exists but cannot be used."""


@dataclass
class PromoCoPurchaseResult:
    """Rezultat agregat al regulii co-purchase pentru o luna/perioada/scope dat."""

    qualifying_bons: int = 0
    discounted_units: int = 0  # 1 unitate redusa per bon calificat
    active_stores: int = 0
    active_agents: int = 0
    # (site_code, agent, item_code) -> nr unitati reduse (= nr bonuri unde acel
    # produs a fost cel redus). Folosit pentru excluderea din incentive.
    excluded_units: dict[tuple[str, str, str], int] = field(default_factory=dict)
    # Valoarea efectiva a discountului, alocata pe aceleasi chei ca unitatile.
    excluded_discount_values: dict[tuple[str, str, str], Decimal] = field(
        default_factory=dict
    )

    def excluded_by_site_item(self) -> dict[tuple[str, str], int]:
        """Agregare pe (site_code, item_code) — pentru cardul Hub si top_stores."""
        out: dict[tuple[str, str], int] = {}
        for (site_code, _agent, item_code), units in self.excluded_units.items():
            out[(site_code, item_code)] = out.get((site_code, item_code), 0) + units
        return out

    @property
    def discount_value(self) -> Decimal:
        return sum(self.excluded_discount_values.values(), Decimal("0"))


def _load_promo_actuals_material(
    definition: dict[str, Any],
) -> tuple[
    dict[tuple[str, str], int] | None,
    dict[tuple[str, str], Decimal] | None,
    str | None,
]:
    source_file = definition.get("actuals_source_file") or definition.get("actuals_file")
    if not source_file:
        return None, None, None
    material_file = definition.get("actuals_material_file")
    expected_source_sha256 = str(definition.get("actuals_source_sha256") or "")
    expected_material_sha256 = str(definition.get("actuals_material_sha256") or "")
    if (
        not material_file
        or len(expected_source_sha256) != 64
        or len(expected_material_sha256) != 64
    ):
        return None, None, "Generația promo nu are materializarea JSON verificabilă."

    source_path = resolve_path(str(source_file), get_repo_root())
    material_path = resolve_path(str(material_file), get_repo_root())
    if not source_path.is_file():
        return None, None, f"Raportul promo `{source_path}` nu exista."
    if not material_path.is_file():
        return None, None, f"Materializarea promo `{material_path}` nu exista."

    try:
        source_bytes = source_path.read_bytes()
        material_bytes = material_path.read_bytes()
    except OSError as exc:
        return None, None, f"Generația promo nu poate fi citită: {exc}."
    if hashlib.sha256(source_bytes).hexdigest() != expected_source_sha256:
        return None, None, "Sursa originală promo nu corespunde hashului aprobat."
    if hashlib.sha256(material_bytes).hexdigest() != expected_material_sha256:
        return None, None, "Materializarea promo nu corespunde hashului aprobat."

    cache_key = (
        str(source_path),
        source_path.stat().st_mtime_ns,
        str(material_path),
        material_path.stat().st_mtime_ns,
        expected_source_sha256,
        expected_material_sha256,
    )
    if cache_key in _promo_actuals_cache:
        return _promo_actuals_cache[cache_key]

    try:
        payload = json.loads(material_bytes)
        if (
            not isinstance(payload, dict)
            or payload.get("version") != 1
            or payload.get("source_sha256") != expected_source_sha256
            or not isinstance(payload.get("rows"), list)
        ):
            raise ValueError("schema invalidă")
        configured_cutoff = str(definition.get("actuals_cutoff_date") or "")
        if configured_cutoff and payload.get("cutoff_date") != configured_cutoff:
            raise ValueError("cutoff diferit de configurația aprobată")

        raw_units: dict[tuple[str, str], int] = {}
        raw_values: dict[tuple[str, str], Decimal] = {}
        for row in payload["rows"]:
            if not isinstance(row, dict):
                raise ValueError("rând invalid")
            site_code = str(row.get("site_code") or "").strip()
            item_code = str(row.get("item_code") or "").strip()
            quantity = row.get("quantity")
            if (
                not site_code
                or not item_code
                or isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
            ):
                raise ValueError("identitate sau cantitate invalidă")
            value = Decimal(str(row.get("value") or "0"))
            if not value.is_finite():
                raise ValueError("valoare promo nefinita")
            key = (site_code, item_code)
            if key in raw_units:
                raise ValueError("cheie promo duplicată")
            raw_units[key] = quantity
            raw_values[key] = value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if payload.get("report_rows") != len(raw_units):
            raise ValueError("număr de rânduri inconsistent")
        if payload.get("promo_units") != sum(raw_units.values()):
            raise ValueError("total de unități inconsistent")
    except (InvalidOperation, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        error = f"Materializarea promo `{material_path.name}` este invalidă: {exc}."
        result: tuple[
            dict[tuple[str, str], int] | None,
            dict[tuple[str, str], Decimal] | None,
            str | None,
        ] = (None, None, error)
        _promo_actuals_cache[cache_key] = result
        return result

    result = (raw_units, raw_values, None)
    _promo_actuals_cache[cache_key] = result
    return result


def load_promo_actual_units(
    definition: dict[str, Any],
    *,
    item_codes: list[str],
) -> PromoActualUnitsLoadResult:
    """Load weekly POS-confirmed promo units from an optional source report.

    The report is intentionally optional. If a promotion has no
    `actuals_source_file`, callers should keep using the rule-based calculator.
    If the source file exists, zero promo units in that file are treated as the
    source of truth for the configured promotion products.
    """
    source_file = definition.get("actuals_source_file") or definition.get("actuals_file")
    if not source_file:
        return None, None

    cached_units, _cached_values, cached_error = _load_promo_actuals_material(definition)

    if cached_units is None or cached_error is not None:
        return cached_units, cached_error

    allowed_codes = {str(code).strip() for code in item_codes if str(code).strip()}
    if not allowed_codes:
        return {}, None
    return {
        (site_code, item_code): units
        for (site_code, item_code), units in cached_units.items()
        if item_code in allowed_codes and units > 0
    }, None


def load_promo_actual_values(
    definition: dict[str, Any],
    *,
    item_codes: list[str],
) -> tuple[dict[tuple[str, str], Decimal] | None, str | None]:
    """Load POS full-price value for the confirmed promo units."""
    units, error = load_promo_actual_units(definition, item_codes=item_codes)
    if units is None or error is not None:
        return None, error

    _cached_units, cached_values, cached_error = _load_promo_actuals_material(definition)
    if cached_values is None or cached_error is not None:
        return cached_values, cached_error
    return {
        key: cached_values.get(key, Decimal("0"))
        for key in units
    }, None


def promo_actuals_cutoff_date(definition: dict[str, Any]) -> date | None:
    source_file = definition.get("actuals_source_file") or definition.get("actuals_file")
    if not source_file:
        return None

    raw_cutoff = definition.get("actuals_cutoff_date")
    if raw_cutoff:
        try:
            return date.fromisoformat(str(raw_cutoff))
        except ValueError:
            return None

    source_path = resolve_path(str(source_file), get_repo_root())
    if not source_path.exists():
        return None
    return date.fromtimestamp(source_path.stat().st_mtime) - timedelta(days=1)


def merge_promo_results(*results: PromoCoPurchaseResult | None) -> PromoCoPurchaseResult:
    excluded_units: dict[tuple[str, str, str], int] = {}
    excluded_discount_values: dict[tuple[str, str, str], Decimal] = {}
    for result in results:
        if result is None:
            continue
        for key, units in result.excluded_units.items():
            excluded_units[key] = excluded_units.get(key, 0) + units
        for key, value in result.excluded_discount_values.items():
            excluded_discount_values[key] = (
                excluded_discount_values.get(key, Decimal("0")) + value
            )
    return _result_from_metrics(excluded_units, excluded_discount_values)


def _agent_filter_values(agent: FilterInput) -> set[str] | None:
    normalized = normalize_filter_values(agent)
    return set(normalized) if normalized else None


def _filtered_promo_actuals(
    definition: dict[str, Any],
    item_codes: list[str],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], Decimal]] | None:
    all_units, all_values, error = _load_promo_actuals_material(definition)
    if all_units is None:
        if error and (definition.get("actuals_source_file") or definition.get("actuals_file")):
            raise PromoActualsError(error)
        return None
    if error is not None:
        raise PromoActualsError(error)
    allowed_codes = {str(code).strip() for code in item_codes if str(code).strip()}
    actual_units = {key: units for key, units in all_units.items() if key[1] in allowed_codes and units > 0}
    actual_values = {key: (all_values or {}).get(key, Decimal("0")) for key in actual_units}
    return actual_units, actual_values


def _allocate_units_to_agents(
    promo_units: int,
    candidates: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """Allocate site+item actual promo units to agents using sales share.

    The source report is store+item granular. Agent-level views and incentive
    exclusion still need agent keys, so allocation is proportional to positive
    sales for the same store+item. Any impossible remainder is kept under "-",
    preserving store-level totals without inventing agent sales.
    """
    promo_units = max(0, int(promo_units))
    if promo_units <= 0:
        return []

    normalized_candidates = [
        (agent, max(0, int(positive_qty)))
        for agent, positive_qty in candidates
        if agent and agent != "-" and int(positive_qty) > 0
    ]
    total_positive = sum(positive_qty for _agent, positive_qty in normalized_candidates)
    if total_positive <= 0:
        return [("-", promo_units)]

    distributable = min(promo_units, total_positive)
    allocations: list[dict[str, Any]] = []
    base_total = 0
    for agent, positive_qty in normalized_candidates:
        numerator = distributable * positive_qty
        base_units = min(positive_qty, numerator // total_positive)
        allocations.append(
            {
                "agent": agent,
                "positive_qty": positive_qty,
                "units": base_units,
                "remainder": numerator % total_positive,
            }
        )
        base_total += base_units

    remaining = distributable - base_total
    for allocation in sorted(
        allocations,
        key=lambda item: (-int(item["remainder"]), -int(item["positive_qty"]), str(item["agent"])),
    ):
        if remaining <= 0:
            break
        if int(allocation["units"]) >= int(allocation["positive_qty"]):
            continue
        allocation["units"] = int(allocation["units"]) + 1
        remaining -= 1

    rows = [
        (str(allocation["agent"]), int(allocation["units"]))
        for allocation in allocations
        if int(allocation["units"]) > 0
    ]
    if promo_units > total_positive:
        rows.append(("-", promo_units - total_positive))
    return rows


def _allocate_value_to_agents(
    total_value: Decimal,
    allocations: list[tuple[str, int]],
) -> dict[str, Decimal]:
    """Allocate an exact POS value using the already-determined unit split."""
    total_units = sum(units for _agent, units in allocations)
    if total_units <= 0:
        return {}

    total_cents = int(
        (total_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    parts: list[dict[str, Any]] = []
    assigned_cents = 0
    for agent_name, units in allocations:
        exact = Decimal(total_cents * units) / Decimal(total_units)
        cents = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        parts.append(
            {
                "agent": agent_name,
                "cents": cents,
                "remainder": exact - cents,
            }
        )
        assigned_cents += cents

    for part in sorted(
        parts,
        key=lambda item: (-item["remainder"], str(item["agent"])),
    ):
        if assigned_cents >= total_cents:
            break
        part["cents"] += 1
        assigned_cents += 1

    return {
        str(part["agent"]): Decimal(int(part["cents"])) / Decimal(100)
        for part in parts
    }


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

    source_sites: list[str] = []
    source_codes: list[str] = []
    source_units: list[int] = []
    for (source_site, source_code), units in sorted(actual_units.items()):
        source_sites.append(source_site)
        source_codes.append(source_code)
        source_units.append(int(units))

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

    allowed_agents = _agent_filter_values(agent)
    excluded_units: dict[tuple[str, str, str], int] = {}
    excluded_discount_values: dict[tuple[str, str, str], Decimal] = {}
    for key, units in scoped_units.items():
        site, item = key
        allocations = _allocate_units_to_agents(
            units,
            candidates.get(key, []),
        )
        allocated_values = _allocate_value_to_agents(
            scoped_values.get(key, Decimal("0")) * discount_rate,
            allocations,
        )
        for agent_name, allocated_units in allocations:
            if allowed_agents is not None and agent_name not in allowed_agents:
                continue
            result_key = (site, agent_name, item)
            excluded_units[result_key] = (
                excluded_units.get(result_key, 0) + allocated_units
            )
            excluded_discount_values[result_key] = (
                excluded_discount_values.get(result_key, Decimal("0"))
                + allocated_values.get(agent_name, Decimal("0"))
            )

    return _result_from_metrics(excluded_units, excluded_discount_values)


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

    receipts: dict[
        tuple[date, str, str, str],
        dict[str, Any],
    ] = {}
    for row in rows:
        if int(row["quantity"] or 0) <= 0:
            continue
        receipt_key = (
            row["sale_date"],
            str(row["site_code"]),
            str(row["agent"]),
            str(row["bon_nr"]),
        )
        receipt = receipts.setdefault(
            receipt_key,
            {"screen_models": set(), "camera_lines": []},
        )
        item_code = str(row["item_code"])
        receipt["screen_models"].update(screen_code_models.get(item_code, ()))
        camera_model_keys = camera_code_models.get(item_code)
        if camera_model_keys:
            receipt["camera_lines"].append(
                (
                    row["unit_price"],
                    item_code,
                    int(row["id"]),
                    frozenset(camera_model_keys),
                )
            )

    aggregated: dict[tuple[str, str, str], tuple[int, Decimal]] = {}
    for (_sale_date, site, receipt_agent, _bon_nr), receipt in receipts.items():
        screen_model_keys = receipt["screen_models"]
        candidates = [
            line
            for line in receipt["camera_lines"]
            if screen_model_keys.intersection(line[3])
        ]
        if not candidates:
            continue
        unit_price, item_code, _row_id, _model_keys = min(
            candidates,
            key=lambda line: (line[0], line[1], line[2]),
        )
        key = (site, receipt_agent, item_code)
        units, gross_value = aggregated.get(key, (0, Decimal("0")))
        aggregated[key] = (units + 1, gross_value + Decimal(str(unit_price)))

    discounted_rows = [
        {
            "site_code": site,
            "agent": receipt_agent,
            "item_code": item_code,
            "units": units,
            "gross_value": gross_value,
        }
        for (site, receipt_agent, item_code), (units, gross_value) in aggregated.items()
    ]
    return _result_from_discounted_rows(
        discounted_rows,
        discount_rate=discount_rate,
    )


def _result_from_metrics(
    excluded_units: dict[tuple[str, str, str], int],
    excluded_discount_values: dict[tuple[str, str, str], Decimal],
) -> PromoCoPurchaseResult:
    stores = {site for site, _agent, _item in excluded_units}
    agents = {
        agent
        for _site, agent, _item in excluded_units
        if agent and agent != "-"
    }
    total = sum(excluded_units.values())
    return PromoCoPurchaseResult(
        qualifying_bons=total,
        discounted_units=total,
        active_stores=len(stores),
        active_agents=len(agents),
        excluded_units=excluded_units,
        excluded_discount_values=excluded_discount_values,
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
