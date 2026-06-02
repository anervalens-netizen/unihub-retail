from __future__ import annotations

from typing import Any

import asyncpg

from models import (
    ContestLeaderboardRow,
    ContestPrizeInfo,
    ContestResponse,
    ContestRuleInfo,
)
from repositories.contests import ContestsRepository
from services.contests_config import ContestDefinition, get_active_contest
from services.dashboard_specials import load_special_cards_config, parse_promotion_definition
from services.promo_copurchase import compute_promo_copurchase

# Prag sentinel cand nu exista regula de pret (nicio unitate nu il depaseste).
_NO_PRICE_THRESHOLD = 10**12


def _scope_clause_for_stores(scope: dict[str, Any]) -> tuple[str, list[Any]]:
    """Clauze pe tabela `stores` (alias s), non-TR inclus."""
    params: list[Any] = []
    clauses = ["s.locatie NOT ILIKE 'TR %'"]
    if scope.get("site_codes"):
        params.append(",".join(str(c) for c in scope["site_codes"]))
        clauses.append(f"s.site_code = ANY(string_to_array(${len(params)}::TEXT, ','))")
    else:
        for key in ("asm", "regional", "firma"):
            if scope.get(key):
                params.append(scope[key])
                clauses.append(f"s.{key} = ${len(params)}")
                break
    return " AND ".join(clauses), params


def _promo_scope_kwargs(scope: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "firma": None,
        "regional": None,
        "asm": None,
        "site_code": None,
        "agent": None,
    }
    if scope.get("site_codes"):
        kwargs["site_code"] = ",".join(str(c) for c in scope["site_codes"])
    elif scope.get("asm"):
        kwargs["asm"] = scope["asm"]
    elif scope.get("regional"):
        kwargs["regional"] = scope["regional"]
    elif scope.get("firma"):
        kwargs["firma"] = scope["firma"]
    return kwargs


class ContestsService:
    def __init__(self, repo: ContestsRepository, pool: asyncpg.Pool):
        self.repo = repo
        self.pool = pool

    async def get_active_contest(
        self, month: str, site_codes_override: list[str] | None = None
    ) -> ContestResponse | None:
        contest, error = get_active_contest(month)
        if contest is None or error:
            return None
        if site_codes_override:
            # Scope per Team Leader (proxy intern FieldOps): leaderboard-ul,
            # numaratoarea de magazine si calculul promo se restrang la aceste
            # site_code-uri. site_codes domina restul cheilor de scope (asm/
            # regional/firma) in tot serviciul de concurs.
            contest.scope = {**contest.scope, "site_codes": list(site_codes_override)}
        return await self._build(contest, month)

    async def _build(self, contest: ContestDefinition, month: str) -> ContestResponse:
        focus_rule = next((r for r in contest.rules if r.type == "focus"), None)
        promo_rule = next((r for r in contest.rules if r.type == "promo"), None)
        price_rule = next((r for r in contest.rules if r.type == "price_above"), None)

        focus_pts = focus_rule.points if focus_rule else 0
        promo_pts = promo_rule.points if promo_rule else 0
        price_pts = price_rule.points if price_rule else 0
        threshold = (
            price_rule.threshold
            if (price_rule and price_rule.threshold is not None)
            else _NO_PRICE_THRESHOLD
        )

        # --- focus + price (per unitate) din sales_transactions ---
        scope_store_sql, scope_store_params = _scope_clause_for_stores(contest.scope)
        params: list[Any] = [month, contest.start_date, contest.end_date, threshold]
        clauses = [
            "st.import_month = $1",
            "st.sale_date BETWEEN $2 AND $3",
            "NOT st.is_cartela",
            "NOT st.is_return",
            "s.locatie NOT ILIKE 'TR %'",
            "st.agent IS NOT NULL",
            "st.agent <> '-'",
        ]
        if contest.scope.get("site_codes"):
            params.append(",".join(str(c) for c in contest.scope["site_codes"]))
            clauses.append(f"st.site_code = ANY(string_to_array(${len(params)}::TEXT, ','))")
        else:
            for key in ("asm", "regional", "firma"):
                if contest.scope.get(key):
                    params.append(contest.scope[key])
                    clauses.append(f"s.{key} = ${len(params)}")
                    break
        agent_rows = await self.repo.fetch_agent_scores(" AND ".join(clauses), params)

        # --- promo: bonuri calificate per agent (co-purchase) ---
        promo_bonuri: dict[str, int] = {}
        if promo_rule is not None:
            promo_config, promo_cfg_err = load_special_cards_config()
            promo_def, promo_def_err = parse_promotion_definition(promo_config, month)
            if promo_def is not None and not promo_def_err and not promo_cfg_err:
                async with self.pool.acquire() as conn:
                    cp = await compute_promo_copurchase(
                        conn,
                        month=month,
                        start_date=promo_def["start_date"],
                        end_date=promo_def["end_date"],
                        item_codes=promo_def["item_codes"],
                        **_promo_scope_kwargs(contest.scope),
                    )
                for (_site, agent, _item), units in cp.excluded_units.items():
                    if agent and agent != "-":
                        promo_bonuri[agent] = promo_bonuri.get(agent, 0) + units

        # --- combinare per agent ---
        focus_units_by_agent = {r["agent"]: int(r["focus_units"]) for r in agent_rows}
        price_units_by_agent = {r["agent"]: int(r["price_units"]) for r in agent_rows}
        all_agents = set(focus_units_by_agent) | set(promo_bonuri)

        scored: list[ContestLeaderboardRow] = []
        for agent in all_agents:
            f_units = focus_units_by_agent.get(agent, 0)
            p_units = price_units_by_agent.get(agent, 0)
            b = promo_bonuri.get(agent, 0)
            f_pts = f_units * focus_pts
            pr_pts = b * promo_pts
            pc_pts = p_units * price_pts
            total = f_pts + pr_pts + pc_pts
            if total <= 0:
                continue
            scored.append(
                ContestLeaderboardRow(
                    rank=0,
                    agent=agent,
                    focus_units=f_units,
                    promo_bonuri=b,
                    price_units=p_units,
                    focus_points=f_pts,
                    promo_points=pr_pts,
                    price_points=pc_pts,
                    total_points=total,
                )
            )

        scored.sort(key=lambda row: (-row.total_points, row.agent))
        for index, row in enumerate(scored):
            row.rank = index + 1
            row.prize = contest.prize_for_rank(row.rank)

        store_count = await self.repo.fetch_scope_store_count(scope_store_sql, scope_store_params)

        return ContestResponse(
            key=contest.key,
            title=contest.title,
            subtitle=contest.subtitle,
            month=month,
            start_date=contest.start_date.isoformat(),
            end_date=contest.end_date.isoformat(),
            store_count=store_count,
            rules=[
                ContestRuleInfo(type=r.type, points=r.points, label=r.label, threshold=r.threshold)
                for r in contest.rules
            ],
            prizes=[
                ContestPrizeInfo(rank_from=p.rank_from, rank_to=p.rank_to, label=p.label)
                for p in contest.prizes
            ],
            leaderboard=scored,
        )
