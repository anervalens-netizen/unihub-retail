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


def _generated_config_path(data_dir: Path) -> Path | None:
    generation_root = data_dir / "promo_generations"
    pointer_path = generation_root / "current.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        relative = str(pointer["config_file"])
        expected_config_sha256 = str(pointer["config_sha256"])
        actuals_manifest = pointer["actuals"]
    except Exception as exc:
        raise ValueError("Pointerul generației promo este invalid.") from exc
    if (
        not relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or len(expected_config_sha256) != 64
        or not isinstance(actuals_manifest, list)
    ):
        raise ValueError("Pointerul generației promo este invalid.")
    candidate = (generation_root / relative).resolve()
    root = generation_root.resolve()
    if candidate.parent.parent != root or not candidate.is_file():
        raise ValueError("Configul generației promo lipsește.")
    config_bytes = candidate.read_bytes()
    actual_config_sha256 = hashlib.sha256(config_bytes).hexdigest()
    if actual_config_sha256 != expected_config_sha256:
        raise ValueError("Configul generației promo nu corespunde hashului aprobat.")

    try:
        config = json.loads(config_bytes)
        declared_sources = {
            str(entry["actuals_source_file"])
            for entry in config["promotions"]
            if isinstance(entry, dict) and entry.get("actuals_source_file")
        }
        expected_sources = {
            str(entry["file"]): str(entry["sha256"])
            for entry in actuals_manifest
            if (
                isinstance(entry, dict)
                and entry.get("file")
                and len(str(entry.get("sha256") or "")) == 64
            )
        }
    except Exception as exc:
        raise ValueError("Manifestul surselor promo este invalid.") from exc
    if (
        len(expected_sources) != len(actuals_manifest)
        or set(expected_sources) != declared_sources
    ):
        raise ValueError("Manifestul surselor promo nu corespunde configului aprobat.")
    for source_file, expected_sha256 in expected_sources.items():
        source_path = resolve_path(source_file, get_repo_root())
        if (
            not source_path.is_file()
            or hashlib.sha256(source_path.read_bytes()).hexdigest() != expected_sha256
        ):
            raise ValueError("Sursa actuals promo nu corespunde hashului aprobat.")
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


def _parse_single_promotion(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rule_type = str(raw.get("rule_type") or "selected_item_copurchase")
    if rule_type not in _PROMOTION_RULE_TYPES:
        return None, f"Intrarea `promotions` are `rule_type` necunoscut: {rule_type}."

    item_codes = [
        str(code).strip()
        for code in raw.get("item_codes", [])
        if str(code).strip()
    ]
    if rule_type == "selected_item_copurchase" and not item_codes:
        return None, "Intrarea `promotions` trebuie sa contina `item_codes`."

    source_file = raw.get("source_file")
    trigger_sheet = raw.get("trigger_sheet")
    discounted_sheet = raw.get("discounted_sheet")
    if rule_type != "selected_item_copurchase":
        if not source_file:
            return None, "Intrarea `promotions` trebuie sa contina `source_file` pentru regula selectata."
        if not trigger_sheet or not discounted_sheet:
            return None, "Intrarea `promotions` trebuie sa contina `trigger_sheet` si `discounted_sheet`."

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

    try:
        discount_rate = Decimal(str(raw.get("discount_rate", PROMOTION_DISCOUNT_RATE)))
    except Exception:
        return None, "Intrarea `promotions` are un `discount_rate` invalid."
    if discount_rate < 0 or discount_rate > 1:
        return None, "Intrarea `promotions` trebuie sa aiba `discount_rate` intre 0 si 1."

    return (
        {
            "key": str(raw.get("key") or _promotion_key(raw.get("title") or "promotie-speciala")),
            "title": str(raw.get("title") or "Promotie speciala"),
            "subtitle": str(raw.get("subtitle") or "Coduri fixe urmarite direct in Hub"),
            "description": str(raw.get("description") or ""),
            "coverage_note": raw.get("coverage_note"),
            "rule_type": rule_type,
            "item_codes": item_codes,
            "source_file": str(source_file) if source_file else None,
            "trigger_sheet": str(trigger_sheet) if trigger_sheet else None,
            "discounted_sheet": str(discounted_sheet) if discounted_sheet else None,
            "actuals_source_file": (
                str(raw.get("actuals_source_file") or raw.get("actuals_file"))
                if (raw.get("actuals_source_file") or raw.get("actuals_file"))
                else None
            ),
            "actuals_sheet": str(raw.get("actuals_sheet") or "AccesoriPromoLunar"),
            "discount_rate": discount_rate,
            "actuals_cutoff_date": (
                str(raw.get("actuals_cutoff_date"))
                if raw.get("actuals_cutoff_date")
                else None
            ),
            "start_date": start_date,
            "end_date": end_date,
        },
        None,
    )


def _promotion_key(value: Any) -> str:
    normalized = normalize_column_name(value)
    return normalized or "promotie-speciala"


def parse_promotion_definitions(
    config: dict[str, Any],
    month: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return all promotion configs whose date range overlaps the given month."""
    entries = config.get("promotions")
    if entries is not None:
        if not isinstance(entries, list):
            return [], "Sectiunea `promotions` trebuie sa fie un array JSON."
        definitions: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                start = date.fromisoformat(str(entry.get("start_date", "")))
                end = date.fromisoformat(str(entry.get("end_date", "")))
            except ValueError:
                continue
            if not month_overlaps_period(month, start, end):
                continue
            definition, error = _parse_single_promotion(entry)
            if error:
                return [], error
            if definition is not None:
                definitions.append(definition)
        return definitions, None

    # Backward compat: old single-object `promotion` key
    raw = config.get("promotion")
    if raw is None or not isinstance(raw, dict):
        return [], None
    try:
        start = date.fromisoformat(str(raw.get("start_date", "")))
        end = date.fromisoformat(str(raw.get("end_date", "")))
    except ValueError:
        return [], None
    if not month_overlaps_period(month, start, end):
        return [], None
    definition, error = _parse_single_promotion(raw)
    return ([definition] if definition is not None else []), error


def parse_promotion_definition(
    config: dict[str, Any],
    month: str,
    promotion_key: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Find promotion config whose date range overlaps the given month."""
    definitions, error = parse_promotion_definitions(config, month)
    if error:
        return None, error
    if not definitions:
        return None, None
    if promotion_key:
        for definition in definitions:
            if definition.get("key") == promotion_key:
                return definition, None
        return None, None
    return definitions[0], None


def load_promotion_rule_products(
    definition: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rule_type = definition.get("rule_type") or "selected_item_copurchase"
    if rule_type == "selected_item_copurchase":
        return {"item_codes": definition.get("item_codes", [])}, None

    source_file = definition.get("source_file")
    trigger_sheet = definition.get("trigger_sheet")
    discounted_sheet = definition.get("discounted_sheet")
    if not source_file or not trigger_sheet or not discounted_sheet:
        return None, "Promotia nu are fisierul si sheet-urile configurate complet."

    source_path = resolve_path(str(source_file), get_repo_root())
    if not source_path.exists():
        return None, f"Fisierul extern `{source_path.name}` nu exista."

    mtime = source_path.stat().st_mtime
    cache_key = (str(source_path), mtime, str(trigger_sheet), str(discounted_sheet))
    if cache_key in _promotion_products_cache:
        return _promotion_products_cache[cache_key]

    try:
        trigger_rows = load_product_code_rows(source_path, sheet_name=str(trigger_sheet))
        discounted_rows = load_product_code_rows(source_path, sheet_name=str(discounted_sheet))
    except Exception as exc:
        result: tuple[dict[str, Any] | None, str | None] = (
            None,
            f"Fisierul `{source_path.name}` nu a putut fi citit: {exc}",
        )
        _promotion_products_cache[cache_key] = result
        return result

    trigger_codes = [str(row["item_code"]) for row in trigger_rows if row.get("item_code")]
    discounted_codes = [str(row["item_code"]) for row in discounted_rows if row.get("item_code")]
    if not trigger_codes or not discounted_codes:
        result = None, f"Fisierul `{source_path.name}` nu contine codurile necesare pentru promotie."
        _promotion_products_cache[cache_key] = result
        return result

    payload: dict[str, Any] = {
        "trigger_codes": trigger_codes,
        "discounted_codes": discounted_codes,
    }
    if rule_type == "same_model_screen_camera":
        payload["trigger_code_models"] = _product_code_models(trigger_rows)
        payload["discounted_code_models"] = _product_code_models(discounted_rows)

    result = payload, None
    _promotion_products_cache[cache_key] = result
    return result


def _materialized_codes(products: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key, value in products.items():
        if key.endswith("_codes") or key == "item_codes":
            if isinstance(value, list):
                codes.update(str(item).strip() for item in value if str(item).strip())
        elif key.endswith("_code_models") and isinstance(value, dict):
            codes.update(str(item).strip() for item in value if str(item).strip())
    return codes


def validate_special_cards_config(
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Validate and materialize every promo before an atomic generation switch."""
    entries = config.get("promotions")
    if not isinstance(entries, list):
        raise ValueError("Secțiunea promotions trebuie să fie un array JSON.")
    definitions: list[dict[str, Any]] = []
    materialized: list[tuple[dict[str, Any], set[str]]] = []
    seen_keys: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Promoția #{index + 1} trebuie să fie un obiect JSON.")
        definition, error = _parse_single_promotion(entry)
        if error or definition is None:
            raise ValueError(error or f"Promoția #{index + 1} este invalidă.")
        key = str(definition["key"]).strip()
        if key in seen_keys:
            raise ValueError(f"Cheia promo duplicată: {key}.")
        seen_keys.add(key)
        cutoff_raw = definition.get("actuals_cutoff_date")
        if cutoff_raw:
            try:
                cutoff = date.fromisoformat(str(cutoff_raw))
            except ValueError as exc:
                raise ValueError(f"Cutoff invalid pentru promoția {key}.") from exc
            if not definition["start_date"] <= cutoff <= definition["end_date"]:
                raise ValueError(f"Cutoff în afara perioadei pentru promoția {key}.")
            if not definition.get("actuals_source_file"):
                raise ValueError(f"Cutoff fără sursă actuals pentru promoția {key}.")
        products, products_error = load_promotion_rule_products(definition)
        if products is None or products_error is not None:
            raise ValueError(products_error or f"Masterul promoției {key} este invalid.")
        codes = _materialized_codes(products)
        if not codes:
            raise ValueError(f"Masterul promoției {key} nu conține produse.")
        definitions.append(definition)
        materialized.append((definition, codes))

    for index, (left, left_codes) in enumerate(materialized):
        for right, right_codes in materialized[index + 1 :]:
            overlaps = not (
                left["end_date"] < right["start_date"]
                or right["end_date"] < left["start_date"]
            )
            if overlaps and left_codes.intersection(right_codes):
                raise ValueError(
                    "Promoțiile suprapuse nu pot conține aceleași produse: "
                    f"{left['key']} / {right['key']}."
                )

    material_payload = [
        {
            "key": definition["key"],
            "start_date": definition["start_date"].isoformat(),
            "end_date": definition["end_date"].isoformat(),
            "codes": sorted(codes),
        }
        for definition, codes in materialized
    ]
    material_sha256 = hashlib.sha256(
        json.dumps(
            material_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return definitions, material_sha256


def _product_code_models(rows: list[dict[str, str | None]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in rows:
        code = row.get("item_code")
        if not code:
            continue
        models = extract_phone_model_keys(row.get("item_name") or "")
        if models:
            out[str(code)] = models
    return out


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
    discount_value = Decimal(normalized_stats.get("discount_value") or 0)
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
                label="Valoare discount", value=format_currency(discount_value)
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
