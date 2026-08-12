from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any

from business_rules import PROMOTION_DISCOUNT_RATE
from services.dashboard_specials_config import (
    _PROMOTION_RULE_TYPES,
    _promotion_products_cache,
    month_overlaps_period,
)
from services.phone_models import extract_phone_model_keys
from services.product_lists import (
    get_repo_root,
    load_product_code_rows,
    normalize_column_name,
    resolve_path,
)

def _promotion_product_fields(
    raw: dict[str, Any], rule_type: str
) -> tuple[list[str], Any, Any, Any, str | None]:
    rule_type = str(raw.get("rule_type") or "selected_item_copurchase")
    if rule_type not in _PROMOTION_RULE_TYPES:
        return [], None, None, None, f"Intrarea `promotions` are `rule_type` necunoscut: {rule_type}."

    item_codes = [
        str(code).strip()
        for code in raw.get("item_codes", [])
        if str(code).strip()
    ]
    if rule_type == "selected_item_copurchase" and not item_codes:
        return [], None, None, None, "Intrarea `promotions` trebuie sa contina `item_codes`."

    source_file = raw.get("source_file")
    trigger_sheet = raw.get("trigger_sheet")
    discounted_sheet = raw.get("discounted_sheet")
    if rule_type != "selected_item_copurchase":
        if not source_file:
            return [], None, None, None, "Intrarea `promotions` trebuie sa contina `source_file` pentru regula selectata."
        if not trigger_sheet or not discounted_sheet:
            return [], None, None, None, "Intrarea `promotions` trebuie sa contina `trigger_sheet` si `discounted_sheet`."
    return item_codes, source_file, trigger_sheet, discounted_sheet, None


def _promotion_dates(raw: dict[str, Any]) -> tuple[date | None, date | None, str | None]:

    try:
        start_date = date.fromisoformat(str(raw["start_date"]))
        end_date = date.fromisoformat(str(raw["end_date"]))
    except Exception:
        return (None, None,
            "Intrarea `promotions` trebuie sa contina `start_date` si `end_date` in format `YYYY-MM-DD`.",
        )

    if end_date < start_date:
        return (None, None,
            "Intrarea `promotions` are o perioada invalida: `end_date` este inainte de `start_date`.",
        )
    return start_date, end_date, None


def _promotion_discount(raw: dict[str, Any]) -> tuple[Decimal | None, str | None]:

    try:
        discount_rate = Decimal(str(raw.get("discount_rate", PROMOTION_DISCOUNT_RATE)))
    except Exception:
        return None, "Intrarea `promotions` are un `discount_rate` invalid."
    if discount_rate < 0 or discount_rate > 1:
        return None, "Intrarea `promotions` trebuie sa aiba `discount_rate` intre 0 si 1."
    return discount_rate, None


def _optional_text(raw: dict[str, Any], key: str, fallback: str | None = None) -> str | None:
    value = raw.get(key) or (raw.get(fallback) if fallback else None)
    return str(value) if value else None


def _parse_single_promotion(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    rule_type = str(raw.get("rule_type") or "selected_item_copurchase")
    item_codes, source_file, trigger_sheet, discounted_sheet, error = (
        _promotion_product_fields(raw, rule_type)
    )
    if error:
        return None, error
    start_date, end_date, error = _promotion_dates(raw)
    if error or start_date is None or end_date is None:
        return None, error
    discount_rate, error = _promotion_discount(raw)
    if error or discount_rate is None:
        return None, error

    return (
        {
            "key": str(raw.get("key") or _promotion_key(raw.get("title") or "promotie-speciala")),
            "title": str(raw.get("title") or "Promotie speciala"),
            "subtitle": str(raw.get("subtitle") or "Coduri fixe urmarite direct in Hub"),
            "description": str(raw.get("description") or ""),
            "coverage_note": raw.get("coverage_note"),
            "rule_type": rule_type,
            "item_codes": item_codes,
            "source_file": _optional_text({"value": source_file}, "value"),
            "trigger_sheet": _optional_text({"value": trigger_sheet}, "value"),
            "discounted_sheet": _optional_text({"value": discounted_sheet}, "value"),
            "actuals_source_file": _optional_text(raw, "actuals_source_file", "actuals_file"),
            "actuals_source_sha256": _optional_text(raw, "actuals_source_sha256"),
            "actuals_material_file": _optional_text(raw, "actuals_material_file"),
            "actuals_material_sha256": _optional_text(raw, "actuals_material_sha256"),
            "actuals_sheet": str(raw.get("actuals_sheet") or "AccesoriPromoLunar"),
            "discount_rate": discount_rate,
            "actuals_cutoff_date": _optional_text(raw, "actuals_cutoff_date"),
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


def _validate_cutoff(definition: dict[str, Any]) -> None:
    cutoff_raw = definition.get("actuals_cutoff_date")
    if not cutoff_raw:
        return
    key = str(definition["key"])
    try:
        cutoff = date.fromisoformat(str(cutoff_raw))
    except ValueError as exc:
        raise ValueError(f"Cutoff invalid pentru promoția {key}.") from exc
    if not definition["start_date"] <= cutoff <= definition["end_date"]:
        raise ValueError(f"Cutoff în afara perioadei pentru promoția {key}.")
    if not definition.get("actuals_source_file"):
        raise ValueError(f"Cutoff fără sursă actuals pentru promoția {key}.")


def _materialize_promotion_entry(
    entry: Any, index: int, seen_keys: set[str]
) -> tuple[dict[str, Any], set[str]]:
    if not isinstance(entry, dict):
        raise ValueError(f"Promoția #{index + 1} trebuie să fie un obiect JSON.")
    definition, error = _parse_single_promotion(entry)
    if error or definition is None:
        raise ValueError(error or f"Promoția #{index + 1} este invalidă.")
    key = str(definition["key"]).strip()
    if key in seen_keys:
        raise ValueError(f"Cheia promo duplicată: {key}.")
    seen_keys.add(key)
    _validate_cutoff(definition)
    products, products_error = load_promotion_rule_products(definition)
    if products is None or products_error is not None:
        raise ValueError(products_error or f"Masterul promoției {key} este invalid.")
    codes = _materialized_codes(products)
    if not codes:
        raise ValueError(f"Masterul promoției {key} nu conține produse.")
    return definition, codes


def _validate_promotion_overlaps(
    materialized: list[tuple[dict[str, Any], set[str]]],
) -> None:

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


def _promotion_material_hash(
    materialized: list[tuple[dict[str, Any], set[str]]],
) -> str:

    material_payload = [
        {
            "key": definition["key"],
            "start_date": definition["start_date"].isoformat(),
            "end_date": definition["end_date"].isoformat(),
            "codes": sorted(codes),
        }
        for definition, codes in materialized
    ]
    return hashlib.sha256(
        json.dumps(
            material_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_special_cards_config(
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Validate and materialize every promo before an atomic generation switch."""
    entries = config.get("promotions")
    if not isinstance(entries, list):
        raise ValueError("Secțiunea promotions trebuie să fie un array JSON.")
    seen_keys: set[str] = set()
    materialized = [
        _materialize_promotion_entry(entry, index, seen_keys)
        for index, entry in enumerate(entries)
    ]
    _validate_promotion_overlaps(materialized)
    return [definition for definition, _ in materialized], _promotion_material_hash(
        materialized
    )


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
