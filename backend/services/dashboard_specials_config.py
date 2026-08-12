from __future__ import annotations

import calendar
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from business_rules import (
    INCENTIVE_FULL_ACHIEVEMENT_RATIO,
    INCENTIVE_FULL_MULTIPLIER,
    INCENTIVE_HALF_ACHIEVEMENT_RATIO,
    INCENTIVE_HALF_MULTIPLIER,
    INCENTIVE_ZERO_MULTIPLIER,
    PROMOTION_DISCOUNT_RATE,
)
from schemas.dashboard import DashboardSpecialCard, DashboardSpecialCardMetric
from services.phone_models import extract_phone_model_keys
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
_promotion_products_cache: dict[tuple[str, float, str, str], tuple[dict[str, Any] | None, str | None]] = {}

_REWARD_COLUMN_ALIASES = {"incentive", "valoare", "reward", "bonus", "incentiv"}
_PROMOTION_RULE_TYPES = {
    "selected_item_copurchase",
    "same_model_screen_camera",
    "trigger_discounted",
}
EMPTY_SPECIAL_CARDS_CONFIG: dict[str, Any] = {"promotions": [], "incentives": []}


def format_currency(value: Decimal | float | int) -> str:
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


def _read_generation_pointer(pointer_path: Path) -> tuple[str, str, list[Any], list[Any]]:
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        relative = str(pointer["config_file"])
        expected_config_sha256 = str(pointer["config_sha256"])
        actuals_manifest = pointer["actuals"]
        actuals_material_manifest = pointer.get("actuals_materials", [])
    except Exception as exc:
        raise ValueError("Pointerul generației promo este invalid.") from exc
    invalid_path = not relative or Path(relative).is_absolute() or ".." in Path(relative).parts
    invalid_manifests = not isinstance(actuals_manifest, list) or not isinstance(
        actuals_material_manifest, list
    )
    if invalid_path or len(expected_config_sha256) != 64 or invalid_manifests:
        raise ValueError("Pointerul generației promo este invalid.")
    return relative, expected_config_sha256, actuals_manifest, actuals_material_manifest


def _expected_files(manifest: list[Any]) -> dict[str, str]:
    return {
        str(entry["file"]): str(entry["sha256"])
        for entry in manifest
        if isinstance(entry, dict)
        and entry.get("file")
        and len(str(entry.get("sha256") or "")) == 64
    }


def _declared_files(config: dict[str, Any], field: str) -> set[str]:
    return {
        str(entry[field])
        for entry in config["promotions"]
        if isinstance(entry, dict) and entry.get(field)
    }


def _parse_generation_sources(
    config_bytes: bytes,
    actuals_manifest: list[Any],
    material_manifest: list[Any],
) -> tuple[dict[str, str], dict[str, str], set[str], set[str]]:
    try:
        config = json.loads(config_bytes)
        return (
            _expected_files(actuals_manifest),
            _expected_files(material_manifest),
            _declared_files(config, "actuals_source_file"),
            _declared_files(config, "actuals_material_file"),
        )
    except Exception as exc:
        raise ValueError("Manifestul surselor promo este invalid.") from exc


def _verify_source_files(files: dict[str, str], *, material: bool) -> None:
    error = (
        "Materializarea actuals promo nu corespunde hashului aprobat."
        if material
        else "Sursa actuals promo nu corespunde hashului aprobat."
    )
    for filename, expected_sha256 in files.items():
        path = resolve_path(filename, get_repo_root())
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError(error)


def _generated_config_path(data_dir: Path) -> Path | None:
    generation_root = data_dir / "promo_generations"
    pointer_path = generation_root / "current.json"
    if not pointer_path.exists():
        return None
    relative, expected_sha, actuals_manifest, material_manifest = _read_generation_pointer(
        pointer_path
    )
    candidate = (generation_root / relative).resolve()
    root = generation_root.resolve()
    if candidate.parent.parent != root or not candidate.is_file():
        raise ValueError("Configul generației promo lipsește.")
    config_bytes = candidate.read_bytes()
    if hashlib.sha256(config_bytes).hexdigest() != expected_sha:
        raise ValueError("Configul generației promo nu corespunde hashului aprobat.")
    expected_sources, expected_materials, declared_sources, declared_materials = (
        _parse_generation_sources(config_bytes, actuals_manifest, material_manifest)
    )
    if len(expected_sources) != len(actuals_manifest) or set(expected_sources) != declared_sources:
        raise ValueError("Manifestul surselor promo nu corespunde configului aprobat.")
    if len(expected_materials) != len(material_manifest) or set(expected_materials) != declared_materials:
        raise ValueError("Manifestul materializărilor promo nu corespunde configului aprobat.")
    _verify_source_files(expected_sources, material=False)
    _verify_source_files(expected_materials, material=True)
    return candidate


def load_special_cards_config() -> tuple[dict[str, Any], str | None]:
    try:
        config_path = get_special_cards_config_path()
    except ValueError as exc:
        return {}, str(exc)
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


def get_special_cards_config_path() -> Path:
    configured_path = os.getenv("UNIHUB_HUB_SPECIALS_CONFIG")
    if configured_path:
        return resolve_path(configured_path, get_repo_root())
    data_dir = get_data_dir()
    return _generated_config_path(data_dir) or data_dir / "hub_specials.json"
