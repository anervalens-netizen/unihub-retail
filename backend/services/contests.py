from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import asyncpg

from schemas.contests import (
    ContestLeaderboardRow,
    ContestPrizeInfo,
    ContestResponse,
    ContestRuleInfo,
)
from retail_filters import cartela_exclusion_clause, distribution_location_clause
from repositories.contests import ContestsRepository
from services.contests_config import ContestDefinition, get_active_contest, get_active_contests
from services.dashboard_specials import (
    load_promotion_rule_products,
    load_special_cards_config,
    parse_promotion_definition,
)
from services.promo_copurchase import (
    PromoCoPurchaseResult,
    compute_promo_actuals_from_report,
    compute_promo_copurchase,
    compute_promo_same_model_pair,
    compute_promo_trigger_discounted,
    merge_promo_results,
    promo_actuals_cutoff_date,
)

# Prag sentinel cand nu exista regula de pret (nicio unitate nu il depaseste).
_NO_PRICE_THRESHOLD = 10**12


@dataclass(frozen=True, slots=True)
class _ContestPoints:
    focus: int
    promo: int
    price: int
    threshold: Any


def _contest_points(contest: ContestDefinition) -> _ContestPoints:
    by_type = {rule.type: rule for rule in contest.rules}
    price_rule = by_type.get("price_above")
    threshold = (
        price_rule.threshold
        if price_rule is not None and price_rule.threshold is not None
        else _NO_PRICE_THRESHOLD
    )
    return _ContestPoints(
        focus=by_type["focus"].points if "focus" in by_type else 0,
        promo=by_type["promo"].points if "promo" in by_type else 0,
        price=price_rule.points if price_rule is not None else 0,
        threshold=threshold,
    )


def _scope_clause_for_stores(scope: dict[str, Any]) -> tuple[str, list[Any]]:
    """Clauze pe tabela `stores` (alias s), non-TR inclus."""
    params: list[Any] = []
    clauses = [distribution_location_clause("s")]
    if scope.get("site_codes"):
        params.append([str(code) for code in scope["site_codes"]])
        clauses.append(f"s.site_code = ANY(${len(params)}::TEXT[])")
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
        kwargs["site_code"] = [str(code) for code in scope["site_codes"]]
    elif scope.get("asm"):
        kwargs["asm"] = scope["asm"]
    elif scope.get("regional"):
        kwargs["regional"] = scope["regional"]
    elif scope.get("firma"):
        kwargs["firma"] = scope["firma"]
    return kwargs


def _scope_label(scope: dict[str, Any]) -> str:
    for key in ("asm", "regional", "firma"):
        if scope.get(key):
            return str(scope[key])
    if scope.get("site_codes"):
        return "Magazine selectate"
    return ""


def _agent_score_scope(
    contest: ContestDefinition,
    month: str,
    threshold: Any,
) -> tuple[list[str], list[Any]]:
    params: list[Any] = [month, contest.start_date, contest.end_date, threshold]
    clauses = [
        "st.import_month = $1",
        "st.sale_date BETWEEN $2 AND $3",
        cartela_exclusion_clause("st"),
        "NOT st.is_return",
        distribution_location_clause("s"),
        "st.agent IS NOT NULL",
        "st.agent <> '-'",
    ]
    if contest.scope.get("site_codes"):
        params.append([str(code) for code in contest.scope["site_codes"]])
        clauses.append(f"st.site_code = ANY(${len(params)}::TEXT[])")
    else:
        for key in ("asm", "regional", "firma"):
            if contest.scope.get(key):
                params.append(contest.scope[key])
                clauses.append(f"s.{key} = ${len(params)}")
                break
    return clauses, params


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

    async def get_active_contests(
        self, month: str, site_codes_override: list[str] | None = None
    ) -> list[ContestResponse]:
        contests, error = get_active_contests(month)
        if error:
            return []
        responses: list[ContestResponse] = []
        for contest in contests:
            if site_codes_override:
                contest.scope = {**contest.scope, "site_codes": list(site_codes_override)}
            responses.append(await self._build(contest, month))
        return responses

    @staticmethod
    def _promo_codes(
        definition: dict[str, Any],
        products: dict[str, Any],
    ) -> tuple[str, list[str]]:
        rule_type = definition.get("rule_type") or "selected_item_copurchase"
        key = (
            "discounted_codes"
            if rule_type in {"same_model_screen_camera", "trigger_discounted"}
            else "item_codes"
        )
        return str(rule_type), list(products[key])

    async def _rule_promo_result(
        self,
        conn: asyncpg.Connection,
        *,
        month: str,
        definition: dict[str, Any],
        products: dict[str, Any],
        rule_type: str,
        item_codes: list[str],
        scope_kwargs: dict[str, Any],
    ) -> PromoCoPurchaseResult:
        common = {
            "month": month,
            "start_date": definition["start_date"],
            "end_date": definition["end_date"],
            **scope_kwargs,
        }
        if rule_type == "same_model_screen_camera":
            return await compute_promo_same_model_pair(
                conn,
                screen_code_models=products["trigger_code_models"],
                camera_code_models=products["discounted_code_models"],
                **common,
            )
        if rule_type == "trigger_discounted":
            return await compute_promo_trigger_discounted(
                conn,
                trigger_codes=products["trigger_codes"],
                discounted_codes=products["discounted_codes"],
                **common,
            )
        return await compute_promo_copurchase(
            conn,
            item_codes=item_codes,
            **common,
        )

    async def _actuals_promo_result(
        self,
        conn: asyncpg.Connection,
        *,
        month: str,
        definition: dict[str, Any],
        item_codes: list[str],
        scope_kwargs: dict[str, Any],
    ) -> PromoCoPurchaseResult | None:
        return await compute_promo_actuals_from_report(
            conn,
            month=month,
            definition=definition,
            item_codes=item_codes,
            **scope_kwargs,
        )

    async def _promo_with_tail(
        self,
        conn: asyncpg.Connection,
        *,
        month: str,
        definition: dict[str, Any],
        products: dict[str, Any],
        rule_type: str,
        item_codes: list[str],
        scope_kwargs: dict[str, Any],
    ) -> PromoCoPurchaseResult:
        result = await self._actuals_promo_result(
            conn,
            month=month,
            definition=definition,
            item_codes=item_codes,
            scope_kwargs=scope_kwargs,
        )
        cutoff = promo_actuals_cutoff_date(definition)
        if result is None or cutoff is None:
            return result or await self._rule_promo_result(
                conn,
                month=month,
                definition=definition,
                products=products,
                rule_type=rule_type,
                item_codes=item_codes,
                scope_kwargs=scope_kwargs,
            )
        tail_start = max(definition["start_date"], cutoff + timedelta(days=1))
        if tail_start > definition["end_date"]:
            return result
        tail_definition = {
            **definition,
            "start_date": tail_start,
            "actuals_source_file": None,
            "actuals_file": None,
        }
        tail = await self._rule_promo_result(
            conn,
            month=month,
            definition=tail_definition,
            products=products,
            rule_type=rule_type,
            item_codes=item_codes,
            scope_kwargs=scope_kwargs,
        )
        return merge_promo_results(result, tail)

    async def _contest_promo_units(
        self,
        contest: ContestDefinition,
        month: str,
        *,
        enabled: bool,
    ) -> dict[tuple[str, str], int]:
        if not enabled:
            return {}
        config, config_error = load_special_cards_config()
        if config_error:
            raise RuntimeError("Configurația promo pentru concurs nu poate fi validată.")
        definition, definition_error = parse_promotion_definition(config, month)
        if definition_error:
            raise RuntimeError("Configurația promo pentru concurs nu poate fi validată.")
        if definition is None:
            return {}
        products, products_error = load_promotion_rule_products(definition)
        if products_error is not None or products is None:
            raise RuntimeError("Masterul promo pentru concurs nu poate fi validat.")
        rule_type, item_codes = self._promo_codes(definition, products)
        async with self.pool.acquire() as conn:
            result = await self._promo_with_tail(
                conn,
                month=month,
                definition=definition,
                products=products,
                rule_type=rule_type,
                item_codes=item_codes,
                scope_kwargs=_promo_scope_kwargs(contest.scope),
            )
        promo_units: dict[tuple[str, str], int] = {}
        for (site_code, agent, _item), units in result.excluded_units.items():
            if agent and agent != "-":
                pair = (site_code, agent)
                promo_units[pair] = promo_units.get(pair, 0) + units
        return promo_units

    async def _contest_person_ids(
        self,
        contest: ContestDefinition,
        month: str,
        agent_rows: list[Any],
        promo_units: dict[tuple[str, str], int],
    ) -> dict[tuple[str, str], str]:
        person_by_pair = {
            (str(row["site_code"]), str(row["agent"])): str(row["person_id"])
            for row in agent_rows
            if row.get("person_id")
        }
        if contest.identity_policy != "person_id":
            return person_by_pair
        missing = sorted(set(promo_units).difference(person_by_pair))
        person_by_pair.update(
            await self.repo.fetch_person_ids(month=month, identities=missing)
        )
        return person_by_pair

    @staticmethod
    def _identity_key(
        contest: ContestDefinition,
        person_by_pair: dict[tuple[str, str], str],
        pair: tuple[str, str],
    ) -> object:
        if contest.identity_policy == "site_agent":
            return pair
        person_id = person_by_pair.get(pair)
        if not person_id:
            raise RuntimeError(
                "Concursul person_id are o identitate de agent neconfirmată."
            )
        return person_id

    def _contest_stats(
        self,
        contest: ContestDefinition,
        agent_rows: list[Any],
        promo_units: dict[tuple[str, str], int],
        person_by_pair: dict[tuple[str, str], str],
    ) -> dict[object, dict[str, Any]]:
        stats: dict[object, dict[str, Any]] = defaultdict(
            lambda: {
                "focus_units": 0,
                "price_units": 0,
                "promo_bonuri": 0,
                "representative": None,
            }
        )
        for row in agent_rows:
            pair = (str(row["site_code"]), str(row["agent"]))
            target = stats[self._identity_key(contest, person_by_pair, pair)]
            target["focus_units"] += int(row["focus_units"])
            target["price_units"] += int(row["price_units"])
            self._select_contest_representative(target, pair, row)
        for pair, units in promo_units.items():
            target = stats[self._identity_key(contest, person_by_pair, pair)]
            target["promo_bonuri"] += units
            if target["representative"] is None:
                target["representative"] = {
                    "agent": pair[1],
                    "site_code": pair[0],
                    "store_name": None,
                    "firma": None,
                }
        return stats

    @staticmethod
    def _select_contest_representative(
        target: dict[str, Any],
        pair: tuple[str, str],
        row: Any,
    ) -> None:
        representative = {
            "agent": pair[1],
            "site_code": pair[0],
            "store_name": row["store_name"],
            "firma": row["firma"],
        }
        current = target["representative"]
        order = (pair[0], pair[1].casefold(), pair[1])
        current_order = (
            (current["site_code"], current["agent"].casefold(), current["agent"])
            if current is not None
            else None
        )
        if current_order is None or order < current_order:
            target["representative"] = representative

    @staticmethod
    def _contest_leaderboard(
        contest: ContestDefinition,
        points: _ContestPoints,
        stats: dict[object, dict[str, Any]],
    ) -> list[ContestLeaderboardRow]:
        scored: list[ContestLeaderboardRow] = []
        for values in stats.values():
            focus_units = int(values["focus_units"])
            promo_units = int(values["promo_bonuri"])
            price_units = int(values["price_units"])
            point_values = (
                focus_units * points.focus,
                promo_units * points.promo,
                price_units * points.price,
            )
            total = sum(point_values)
            if total <= 0:
                continue
            representative = values["representative"]
            scored.append(
                ContestLeaderboardRow(
                    rank=0,
                    agent=str(representative["agent"]),
                    site_code=representative.get("site_code"),
                    store_name=representative.get("store_name"),
                    firma=representative.get("firma"),
                    focus_units=focus_units,
                    promo_bonuri=promo_units,
                    price_units=price_units,
                    focus_points=point_values[0],
                    promo_points=point_values[1],
                    price_points=point_values[2],
                    total_points=total,
                )
            )
        scored.sort(
            key=lambda row: (
                -row.total_points,
                row.agent.casefold(),
                row.site_code or "",
            )
        )
        for index, row in enumerate(scored):
            row.rank = index + 1
            row.prize = contest.prize_for_rank(row.rank)
        return scored

    @staticmethod
    def _contest_response(
        contest: ContestDefinition,
        month: str,
        store_count: int,
        leaderboard: list[ContestLeaderboardRow],
    ) -> ContestResponse:
        return ContestResponse(
            identity_policy=contest.identity_policy,
            key=contest.key,
            title=contest.title,
            subtitle=contest.subtitle,
            scope_label=_scope_label(contest.scope),
            month=month,
            start_date=contest.start_date.isoformat(),
            end_date=contest.end_date.isoformat(),
            store_count=store_count,
            rules=[
                ContestRuleInfo(
                    type=rule.type,
                    points=rule.points,
                    label=rule.label,
                    threshold=rule.threshold,
                )
                for rule in contest.rules
            ],
            prizes=[
                ContestPrizeInfo(
                    rank_from=prize.rank_from,
                    rank_to=prize.rank_to,
                    label=prize.label,
                )
                for prize in contest.prizes
            ],
            leaderboard=leaderboard,
        )

    async def _build(
        self,
        contest: ContestDefinition,
        month: str,
    ) -> ContestResponse:
        points = _contest_points(contest)
        scope_sql, scope_params = _scope_clause_for_stores(contest.scope)
        clauses, params = _agent_score_scope(contest, month, points.threshold)
        agent_rows = await self.repo.fetch_agent_scores(
            " AND ".join(clauses),
            params,
        )
        promo_units = await self._contest_promo_units(
            contest,
            month,
            enabled=points.promo > 0,
        )
        person_ids = await self._contest_person_ids(
            contest,
            month,
            agent_rows,
            promo_units,
        )
        stats = self._contest_stats(
            contest,
            agent_rows,
            promo_units,
            person_ids,
        )
        leaderboard = self._contest_leaderboard(contest, points, stats)
        store_count = await self.repo.fetch_scope_store_count(
            scope_sql,
            scope_params,
        )
        return self._contest_response(
            contest,
            month,
            store_count,
            leaderboard,
        )
