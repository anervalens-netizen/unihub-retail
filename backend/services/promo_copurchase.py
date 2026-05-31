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

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import asyncpg

from services.dashboard.utils import _build_scoped_params
from services.filters import scoped_clauses


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

    def excluded_by_site_item(self) -> dict[tuple[str, str], int]:
        """Agregare pe (site_code, item_code) — pentru cardul Hub si top_stores."""
        out: dict[tuple[str, str], int] = {}
        for (site_code, _agent, item_code), units in self.excluded_units.items():
            out[(site_code, item_code)] = out.get((site_code, item_code), 0) + units
        return out


async def compute_promo_copurchase(
    conn: asyncpg.Connection,
    *,
    month: str,
    start_date: date,
    end_date: date,
    item_codes: list[str],
    firma: str | None,
    regional: str | None,
    asm: str | None,
    site_code: str | None,
    agent: str | None,
) -> PromoCoPurchaseResult:
    """Calculeaza bonurile calificate + unitatile reduse pentru promotia co-purchase.

    Returneaza un PromoCoPurchaseResult gol daca nu exista coduri sau date.
    """
    if not item_codes:
        return PromoCoPurchaseResult()

    params, positions = _build_scoped_params(
        [month, start_date, end_date, item_codes],
        firma=firma,
        regional=regional,
        asm=asm,
        site_code=site_code,
        agent=agent,
    )
    # scoped_clauses adauga: TR% exclude, NOT st.is_cartela, si clauzele de scope.
    scope = scoped_clauses(
        positions,
        site_alias="st",
        store_alias="s",
        agent_alias="st",
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
              AND NOT st.is_return{scope_sql}
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
                l.site_code, l.agent, l.item_code
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
        SELECT site_code, agent, item_code, COUNT(*)::INT AS units
        FROM discounted
        GROUP BY site_code, agent, item_code
        """,
        *params,
    )

    excluded_units: dict[tuple[str, str, str], int] = {}
    stores: set[str] = set()
    agents: set[str] = set()
    total = 0
    for row in rows:
        units = int(row["units"])
        site_val = row["site_code"]
        agent_val = row["agent"]
        excluded_units[(site_val, agent_val, row["item_code"])] = units
        total += units
        stores.add(site_val)
        if agent_val and agent_val != "-":
            agents.add(agent_val)

    return PromoCoPurchaseResult(
        qualifying_bons=total,
        discounted_units=total,
        active_stores=len(stores),
        active_agents=len(agents),
        excluded_units=excluded_units,
    )
