from __future__ import annotations

import calendar
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Literal

from models import DashboardSpecialCard, DashboardSpecialCardMetric
from services.product_lists import (
    get_data_dir,
    get_repo_root,
    load_product_code_rows,
    normalize_column_name,
    resolve_path,
    _read_excel_with_auto_header,
)

# Cache: (filepath, mtime) -> parsed result, auto-invalidates on file change
_special_config_cache: dict[tuple[str, float], tuple[dict[str, Any], str | None]] = {}
_special_codes_cache: dict[tuple[str, float], tuple[list[str] | None, str | None]] = {}
_reward_map_cache: dict[tuple[str, float], tuple[dict[str, float] | None, str | None]] = {}

_REWARD_COLUMN_ALIASES = {"incentive", "valoare", "reward", "bonus", "incentiv"}
EMPTY_SPECIAL_CARDS_CONFIG: dict[str, Any] = {"promotions": [], "incentives": []}


def format_currency(value: float | int) -> str:
    rounded = round(float(value))
    grouped = f"{rounded:,}".replace(",", ".")
    return f"{grouped} RON"


def format_int(value: float | int) -> str:
    rounded = round(float(value))
    return f"{rounded:,}".replace(",", ".")


def format_percent(value: float | int | None) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def month_overlaps_period(month: str, start_date: date, end_date: date) -> bool:
    try:
        year, month_number = month.split("-", maxsplit=1)
        month_start = date(int(year), int(month_number), 1)
    except ValueError:
        return False
    month_end = date(
        month_start.year,
        month_start.month,
        calendar.monthrange(month_start.year, month_start.month)[1],
    )
    return not (month_end < start_date or month_start > end_date)


def load_special_cards_config() -> tuple[dict[str, Any], str | None]:
    configured_path = os.getenv("UNIHUB_HUB_SPECIALS_CONFIG")
    config_path = (
        resolve_path(configured_path, get_repo_root())
        if configured_path
        else get_data_dir() / "hub_specials.json"
    )
    if not config_path.exists():
        return EMPTY_SPECIAL_CARDS_CONFIG.copy(), None

    mtime = config_path.stat().st_mtime
    cache_key = (str(config_path), mtime)
    if cache_key in _special_config_cache:
        return _special_config_cache[cache_key]

    result: tuple[dict[str, Any] | None, str | None]
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        result = {}, f"Config invalid in {config_path.name}: {exc}"
        _special_config_cache[cache_key] = result
        return result

    if not isinstance(payload, dict):
        result = {}, f"Config invalid in {config_path.name}: root must be a JSON object."
        _special_config_cache[cache_key] = result
        return result  # type: ignore[return-value]
    result = payload, None
    _special_config_cache[cache_key] = result
    return result


def _parse_single_promotion(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    item_codes = [
        str(code).strip()
        for code in raw.get("item_codes", [])
        if str(code).strip()
    ]
    if not item_codes:
        return None, "Intrarea `promotions` trebuie sa contina `item_codes`."

    try:
        start_date = date.fromisoformat(str(raw["start_date"]))
        end_date = date.fromisoformat(str(raw["end_date"]))
    except Exception:
        return (
            None,
            "Intrarea `promotions` trebuie sa contina `start_date` si `end_date` in format `YYYY-MM-DD`.",
        )

    if end_date < start_date:
        return (
            None,
            "Intrarea `promotions` are o perioada invalida: `end_date` este inainte de `start_date`.",
        )

    return (
        {
            "title": str(raw.get("title") or "Promotie speciala"),
            "subtitle": str(raw.get("subtitle") or "Coduri fixe urmarite direct in Hub"),
            "description": str(raw.get("description") or ""),
            "coverage_note": raw.get("coverage_note"),
            "item_codes": item_codes,
            "start_date": start_date,
            "end_date": end_date,
        },
        None,
    )


def parse_promotion_definition(
    config: dict[str, Any],
    month: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Find promotion config whose date range overlaps the given month."""
    entries = config.get("promotions")
    if entries is not None:
        if not isinstance(entries, list):
            return None, "Sectiunea `promotions` trebuie sa fie un array JSON."
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                start = date.fromisoformat(str(entry.get("start_date", "")))
                end = date.fromisoformat(str(entry.get("end_date", "")))
            except ValueError:
                continue
            if month_overlaps_period(month, start, end):
                return _parse_single_promotion(entry)
        return None, None

    # Backward compat: old single-object `promotion` key
    raw = config.get("promotion")
    if raw is None or not isinstance(raw, dict):
        return None, None
    try:
        start = date.fromisoformat(str(raw.get("start_date", "")))
        end = date.fromisoformat(str(raw.get("end_date", "")))
    except ValueError:
        return None, None
    if not month_overlaps_period(month, start, end):
        return None, None
    return _parse_single_promotion(raw)


def _parse_single_incentive(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    source_file = raw.get("source_file") or os.getenv("UNIHUB_INCENTIVE_FILE")
    if not source_file:
        return None, "Intrarea `incentives` trebuie sa contina `source_file` sau `UNIHUB_INCENTIVE_FILE`."

    month_value = raw.get("month")
    if not month_value:
        return None, "Intrarea `incentives` trebuie sa contina `month`."

    raw_reward = raw.get("reward_per_unit")
    reward_per_unit_value: float | None = None
    if raw_reward is not None:
        try:
            reward_per_unit_value = float(raw_reward)
        except (TypeError, ValueError):
            return None, "Intrarea `incentives` trebuie sa contina un `reward_per_unit` numeric sau null."

    return (
        {
            "title": str(raw.get("title") or "Incentive special"),
            "subtitle": str(raw.get("subtitle") or "Bonus calculat direct din codurile eligibile"),
            "description": str(raw.get("description") or ""),
            "source_file": str(source_file),
            "month": str(month_value),
            "reward_per_unit": reward_per_unit_value,  # None = per-produs
        },
        None,
    )


def parse_incentive_definition(
    config: dict[str, Any],
    month: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Find incentive config for the given month."""
    entries = config.get("incentives")
    if entries is not None:
        if not isinstance(entries, list):
            return None, "Sectiunea `incentives` trebuie sa fie un array JSON."
        for entry in entries:
            if isinstance(entry, dict) and entry.get("month") == month:
                return _parse_single_incentive(entry)
        return None, None

    # Backward compat: old single-object `incentive` key
    raw = config.get("incentive")
    if raw is None or not isinstance(raw, dict):
        return None, None
    if raw.get("month") != month:
        return None, None
    return _parse_single_incentive(raw)


def load_incentive_codes(
    definition: dict[str, Any],
) -> tuple[list[str] | None, str | None]:
    source_path = resolve_path(definition["source_file"], get_data_dir())
    if not source_path.exists():
        return None, f"Fisierul extern `{source_path.name}` nu exista in data/."

    mtime = source_path.stat().st_mtime
    cache_key = (str(source_path), mtime)
    if cache_key in _special_codes_cache:
        return _special_codes_cache[cache_key]

    try:
        rows = load_product_code_rows(source_path)
    except Exception as exc:
        result = None, f"Fisierul `{source_path.name}` nu a putut fi citit: {exc}"
        _special_codes_cache[cache_key] = result
        return result

    codes = [str(row["item_code"]) for row in rows if row.get("item_code")]
    codes_result: tuple[list[str] | None, str | None]
    if not codes:
        codes_result = None, f"Fisierul `{source_path.name}` nu contine coduri eligibile."
        _special_codes_cache[cache_key] = codes_result
        return codes_result  # type: ignore[return-value]
    codes_result = codes, None
    _special_codes_cache[cache_key] = codes_result
    return codes_result  # type: ignore[return-value]


def load_incentive_reward_map(
    definition: dict[str, Any],
) -> tuple[dict[str, float] | None, str | None]:
    """Returns {item_code: reward_value} from the source file's reward column.
    Falls back to reward_per_unit if no reward column is found in the file.
    """
    source_path = resolve_path(definition["source_file"], get_data_dir())
    if not source_path.exists():
        return None, f"Fisierul extern `{source_path.name}` nu exista in data/."

    mtime = source_path.stat().st_mtime
    cache_key = (str(source_path), mtime)
    if cache_key in _reward_map_cache:
        return _reward_map_cache[cache_key]

    try:
        df = _read_excel_with_auto_header(source_path)
    except Exception as exc:
        result: tuple[dict[str, float] | None, str | None] = (
            None,
            f"Fisierul `{source_path.name}` nu a putut fi citit: {exc}",
        )
        _reward_map_cache[cache_key] = result
        return result

    # Find reward column
    normalized_cols = {normalize_column_name(c): c for c in df.columns}
    reward_col = next(
        (normalized_cols[alias] for alias in _REWARD_COLUMN_ALIASES if alias in normalized_cols),
        None,
    )

    # Find code column
    from services.product_lists import CODE_COLUMN_ALIASES
    code_col = next(
        (normalized_cols[alias] for alias in CODE_COLUMN_ALIASES if alias in normalized_cols),
        None,
    )

    if code_col is None:
        result = None, f"Fisierul `{source_path.name}` nu contine o coloana de cod produs."
        _reward_map_cache[cache_key] = result
        return result

    reward_map: dict[str, float] = {}
    flat_reward = definition.get("reward_per_unit")

    for record in df.to_dict(orient="records"):
        code = str(record.get(code_col, "")).strip()
        if not code or code.lower() == "nan":
            continue
        if reward_col is not None:
            raw_val = record.get(reward_col)
            try:
                reward = float(raw_val)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        elif flat_reward is not None:
            reward = float(flat_reward)
        else:
            continue
        reward_map[code] = reward

    if not reward_map:
        result = None, f"Fisierul `{source_path.name}` nu contine coduri cu valori de incentive."
        _reward_map_cache[cache_key] = result
        return result

    result = reward_map, None
    _reward_map_cache[cache_key] = result
    return result


def incentive_multiplier(achievement: float) -> float:
    """Map store target achievement ratio to incentive multiplier (0.0, 0.5, or 1.0)."""
    if achievement >= 0.99:
        return 1.0
    if achievement >= 0.89:
        return 0.5
    return 0.0


def prewarm_special_cards_cache() -> None:
    """Warm up caches for all configured months at startup."""
    config, _ = load_special_cards_config()
    for entry in config.get("incentives", []):
        if isinstance(entry, dict):
            month = entry.get("month", "")
            incentive_definition, incentive_error = parse_incentive_definition(config, month)
            if incentive_definition is not None and incentive_error is None:
                load_incentive_codes(incentive_definition)


def build_promotion_card(
    month: str,
    definition: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    *,
    config_error: str | None = None,
    definition_error: str | None = None,
) -> DashboardSpecialCard:
    if config_error:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config invalid",
            highlight_value="-",
            description=config_error,
        )

    if definition_error:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config incomplet",
            highlight_value="-",
            description=definition_error,
        )

    if definition is None:
        return DashboardSpecialCard(
            key="promotion",
            title="Promotie speciala",
            subtitle="Card promo cu coduri fixe",
            status="missing_config",
            status_label="Config lipsa",
            highlight_value="-",
            description="Lipseste definitia `promotion` din `hub_specials.json`.",
        )

    start_date = definition["start_date"]
    end_date = definition["end_date"]
    if not month_overlaps_period(month, start_date, end_date):
        return DashboardSpecialCard(
            key="promotion",
            title=definition["title"],
            subtitle=definition["subtitle"],
            status="inactive",
            status_label="In afara perioadei",
            highlight_value=f"{start_date.isoformat()} - {end_date.isoformat()}",
            description=definition["description"]
            or f"Promotia este definita pe {format_int(len(definition['item_codes']))} coduri fixe.",
            coverage_note=definition.get("coverage_note"),
            metrics=[
                DashboardSpecialCardMetric(
                    label="Coduri", value=format_int(len(definition["item_codes"]))
                )
            ],
        )

    normalized_stats = stats or {}
    qualifying_bons = int(normalized_stats.get("qualifying_bons") or 0)
    discounted_units = int(normalized_stats.get("discounted_units") or 0)
    active_stores = int(normalized_stats.get("active_stores") or 0)
    active_agents = int(normalized_stats.get("active_agents") or 0)
    status: Literal["ready", "no_data"] = "ready" if qualifying_bons > 0 else "no_data"

    return DashboardSpecialCard(
        key="promotion",
        title=definition["title"],
        subtitle=definition["subtitle"],
        status=status,
        status_label="Bonuri calificate" if status == "ready" else "Fara bonuri calificate",
        highlight_value=format_int(qualifying_bons),
        description=definition["description"]
        or f"Perioada {start_date.isoformat()} - {end_date.isoformat()} pentru {format_int(len(definition['item_codes']))} coduri.",
        coverage_note=definition.get("coverage_note"),
        metrics=[
            DashboardSpecialCardMetric(
                label="Produse reduse", value=format_int(discounted_units)
            ),
            DashboardSpecialCardMetric(
                label="Magazine", value=format_int(active_stores)
            ),
            DashboardSpecialCardMetric(label="Agenti", value=format_int(active_agents)),
        ],
    )


def build_incentive_card(
    month: str,
    definition: dict[str, Any] | None,
    stats: dict[str, Any] | None,
    *,
    config_error: str | None = None,
    definition_error: str | None = None,
    codes_error: str | None = None,
) -> DashboardSpecialCard:
    if config_error:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config invalid",
            highlight_value="-",
            description=config_error,
        )

    if definition_error:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config incomplet",
            highlight_value="-",
            description=definition_error,
        )

    if definition is None:
        return DashboardSpecialCard(
            key="incentive",
            title="Incentive special",
            subtitle="Bonus pe coduri eligibile",
            status="missing_config",
            status_label="Config lipsa",
            highlight_value="-",
            description="Lipseste definitia `incentive` din `hub_specials.json`.",
        )

    if codes_error:
        return DashboardSpecialCard(
            key="incentive",
            title=definition["title"],
            subtitle=definition["subtitle"],
            status="missing_source",
            status_label="Fisier lipsa",
            highlight_value=Path(definition["source_file"]).name,
            description=codes_error,
        )

    reward_per_unit = definition.get("reward_per_unit")
    per_product_mode = reward_per_unit is None

    if month != definition["month"]:
        inactive_metrics = []
        if not per_product_mode and reward_per_unit is not None:
            inactive_metrics = [
                DashboardSpecialCardMetric(
                    label="Bonus / buc", value=format_currency(reward_per_unit)
                )
            ]
        return DashboardSpecialCard(
            key="incentive",
            title=definition["title"],
            subtitle=definition["subtitle"],
            status="inactive",
            status_label="Alta luna",
            highlight_value=definition["month"],
            description=definition["description"]
            or f"Incentive-ul este configurat pentru luna {definition['month']}.",
            metrics=inactive_metrics,
        )

    normalized_stats = stats or {}
    net_quantity = int(normalized_stats.get("net_quantity") or 0)
    positive_quantity = int(normalized_stats.get("positive_quantity") or 0)
    return_quantity = abs(int(normalized_stats.get("return_quantity") or 0))
    active_stores = int(normalized_stats.get("active_stores") or 0)
    active_agents = int(normalized_stats.get("active_agents") or 0)
    active_codes = int(normalized_stats.get("active_codes") or 0)
    status: Literal["ready", "no_data"] = "ready" if positive_quantity > 0 or return_quantity > 0 else "no_data"

    if per_product_mode:
        # incentive_value pre-calculated in stats as weighted sum
        estimated_bonus = float(normalized_stats.get("incentive_value") or 0)
        coverage = (
            f"Magazine active: {format_int(active_stores)}. "
            "Bonusul este calculat pe cantitate vanduta x valoarea incentive per cod."
        )
        description = definition["description"] or "Bonusul variaza per cod de produs."
    else:
        estimated_bonus = net_quantity * float(reward_per_unit)  # type: ignore[arg-type]
        rpu = float(reward_per_unit)  # type: ignore[arg-type]
        coverage = (
            f"Magazine active: {format_int(active_stores)}. "
            f"Bonusul este calculat pe cantitate neta (retururile scad cate "
            f"{format_currency(rpu)} per unitate)."
        )
        description = definition["description"] or (
            f"Fiecare unitate neta eligibila aduce {format_currency(rpu)} agentului."
        )

    if per_product_mode:
        metrics = [
            DashboardSpecialCardMetric(
                label="Unitati nete", value=format_int(net_quantity)
            ),
            DashboardSpecialCardMetric(
                label="Retururi", value=format_int(return_quantity)
            ),
            DashboardSpecialCardMetric(
                label="Coduri active", value=format_int(active_codes)
            ),
            DashboardSpecialCardMetric(label="Agenti", value=format_int(active_agents)),
        ]
    else:
        metrics = [
            DashboardSpecialCardMetric(
                label="Unitati nete", value=format_int(net_quantity)
            ),
            DashboardSpecialCardMetric(
                label="Retururi", value=format_int(return_quantity)
            ),
            DashboardSpecialCardMetric(
                label="Coduri active", value=format_int(active_codes)
            ),
            DashboardSpecialCardMetric(label="Agenti", value=format_int(active_agents)),
        ]

    return DashboardSpecialCard(
        key="incentive",
        title=definition["title"],
        subtitle=definition["subtitle"],
        status=status,
        status_label="Calcul net" if status == "ready" else "Fara vanzari",
        highlight_value=format_currency(estimated_bonus),
        description=description,
        metrics=metrics,
        coverage_note=coverage,
    )
