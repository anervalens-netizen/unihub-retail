"""Contest configuration loader + parser (config-driven, reusable).

Concursurile sunt definite in `data/contests.json` (gitignored, live config, ca
`hub_specials.json`). Fiecare concurs are: perioada, scope (zona), reguli de
punctaj si premii. Punctajul este la nivel de agent.

Reguli suportate (per regula: `points`, optional `threshold`):
  - `focus`        -> +points / unitate vanduta din `focus_products`
  - `promo`        -> +points / bon promo calificat (co-purchase, vezi promo_copurchase)
  - `price_above`  -> +points / unitate cu unit_price > `threshold`

Scope suportat: `{"asm": "..."}`, `{"regional": "..."}`, `{"firma": "..."}`,
sau `{"site_codes": [...]}`. Locatiile de distributie (TR %) sunt mereu excluse.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from services.dashboard_specials import month_overlaps_period
from services.product_lists import get_data_dir, get_repo_root, resolve_path

RuleType = Literal["focus", "promo", "price_above"]
_VALID_RULE_TYPES = {"focus", "promo", "price_above"}

_config_cache: dict[tuple[str, float], tuple[dict[str, Any], str | None]] = {}


@dataclass
class ContestRule:
    type: RuleType
    points: int
    label: str
    threshold: float | None = None


@dataclass
class ContestPrize:
    rank_from: int
    rank_to: int
    label: str


@dataclass
class ContestDefinition:
    key: str
    title: str
    subtitle: str
    start_date: date
    end_date: date
    scope: dict[str, Any]
    rules: list[ContestRule] = field(default_factory=list)
    prizes: list[ContestPrize] = field(default_factory=list)

    def prize_for_rank(self, rank: int) -> str | None:
        for prize in self.prizes:
            if prize.rank_from <= rank <= prize.rank_to:
                return prize.label
        return None


def _config_path():
    configured = os.getenv("UNIHUB_CONTESTS_CONFIG")
    return (
        resolve_path(configured, get_repo_root())
        if configured
        else get_data_dir() / "contests.json"
    )


def load_contests_config() -> tuple[dict[str, Any], str | None]:
    config_path = _config_path()
    if not config_path.exists():
        return {"contests": []}, None

    mtime = config_path.stat().st_mtime
    cache_key = (str(config_path), mtime)
    if cache_key in _config_cache:
        return _config_cache[cache_key]

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        result: tuple[dict[str, Any], str | None] = (
            {"contests": []},
            f"Config invalid in {config_path.name}: {exc}",
        )
        _config_cache[cache_key] = result
        return result

    if not isinstance(payload, dict):
        result = {"contests": []}, f"Config invalid in {config_path.name}: root must be a JSON object."
        _config_cache[cache_key] = result
        return result

    result = payload, None
    _config_cache[cache_key] = result
    return result


def _parse_rule(raw: dict[str, Any]) -> ContestRule | None:
    rule_type = str(raw.get("type", "")).strip()
    if rule_type not in _VALID_RULE_TYPES:
        return None
    try:
        points = int(raw.get("points", 1))
    except (TypeError, ValueError):
        points = 1
    threshold: float | None = None
    if rule_type == "price_above":
        try:
            threshold = float(raw["threshold"])
        except (KeyError, TypeError, ValueError):
            return None
    label = str(raw.get("label") or rule_type)
    return ContestRule(type=rule_type, points=points, label=label, threshold=threshold)  # type: ignore[arg-type]


def _parse_prize(raw: dict[str, Any]) -> ContestPrize | None:
    try:
        rank_from = int(raw["rank_from"])
        rank_to = int(raw["rank_to"])
    except (KeyError, TypeError, ValueError):
        return None
    if rank_to < rank_from:
        return None
    return ContestPrize(rank_from=rank_from, rank_to=rank_to, label=str(raw.get("label") or ""))


def _parse_contest(raw: dict[str, Any]) -> ContestDefinition | None:
    key = str(raw.get("key") or "").strip()
    if not key:
        return None
    try:
        start_date = date.fromisoformat(str(raw["start_date"]))
        end_date = date.fromisoformat(str(raw["end_date"]))
    except (KeyError, ValueError):
        return None
    if end_date < start_date:
        return None

    scope = raw.get("scope")
    if not isinstance(scope, dict):
        scope = {}

    rules = [
        rule_parsed
        for entry in raw.get("rules", [])
        if isinstance(entry, dict) and (rule_parsed := _parse_rule(entry)) is not None
    ]
    prizes = sorted(
        [
            prize_parsed
            for entry in raw.get("prizes", [])
            if isinstance(entry, dict) and (prize_parsed := _parse_prize(entry)) is not None
        ],
        key=lambda p: p.rank_from,
    )

    return ContestDefinition(
        key=key,
        title=str(raw.get("title") or "Concurs"),
        subtitle=str(raw.get("subtitle") or ""),
        start_date=start_date,
        end_date=end_date,
        scope=scope,
        rules=rules,
        prizes=prizes,
    )


def parse_contests(config: dict[str, Any]) -> list[ContestDefinition]:
    entries = config.get("contests")
    if not isinstance(entries, list):
        return []
    return [
        parsed
        for entry in entries
        if isinstance(entry, dict) and (parsed := _parse_contest(entry)) is not None
    ]


def get_active_contests(month: str) -> tuple[list[ContestDefinition], str | None]:
    """Returneaza toate concursurile a caror perioada se suprapune cu luna data."""
    config, error = load_contests_config()
    if error:
        return [], error
    return [
        contest
        for contest in parse_contests(config)
        if month_overlaps_period(month, contest.start_date, contest.end_date)
    ], None


def get_active_contest(month: str) -> tuple[ContestDefinition | None, str | None]:
    """Returneaza primul concurs a carui perioada se suprapune cu luna data."""
    contests, error = get_active_contests(month)
    if error:
        return None, error
    return (contests[0], None) if contests else (None, None)
