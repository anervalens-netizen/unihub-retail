from __future__ import annotations

import os
from typing import Any

from business_rules import (
    INCENTIVE_FULL_ACHIEVEMENT_RATIO,
    INCENTIVE_FULL_MULTIPLIER,
    INCENTIVE_HALF_ACHIEVEMENT_RATIO,
    INCENTIVE_HALF_MULTIPLIER,
    INCENTIVE_ZERO_MULTIPLIER,
)
from services.dashboard_specials_config import (
    _REWARD_COLUMN_ALIASES,
    _reward_map_cache,
    _special_codes_cache,
    load_special_cards_config,
)
from services.product_lists import (
    _read_excel_with_auto_header,
    get_data_dir,
    load_product_code_rows,
    normalize_column_name,
    resolve_path,
)

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
    if achievement >= INCENTIVE_FULL_ACHIEVEMENT_RATIO:
        return INCENTIVE_FULL_MULTIPLIER
    if achievement >= INCENTIVE_HALF_ACHIEVEMENT_RATIO:
        return INCENTIVE_HALF_MULTIPLIER
    return INCENTIVE_ZERO_MULTIPLIER


def prewarm_special_cards_cache() -> None:
    """Warm up caches for all configured months at startup."""
    config, _ = load_special_cards_config()
    for entry in config.get("incentives", []):
        if isinstance(entry, dict):
            month = entry.get("month", "")
            incentive_definition, incentive_error = parse_incentive_definition(config, month)
            if incentive_definition is not None and incentive_error is None:
                load_incentive_codes(incentive_definition)
