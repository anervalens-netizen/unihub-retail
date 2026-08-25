"""Validated immutable promotion actuals material loading."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from services.product_lists import get_repo_root, resolve_path
from services.promo_types import PromoActualsError


PromoActualUnitsLoadResult = tuple[dict[tuple[str, str], int] | None, str | None]
_MONEY_QUANTUM = Decimal("0.01")
_promo_actuals_cache: dict[
    tuple[str, int, str, int, str, str],
    tuple[
        dict[tuple[str, str], int] | None,
        dict[tuple[str, str], Decimal] | None,
        str | None,
    ],
] = {}


def _promo_source_paths(
    definition: dict[str, Any],
) -> tuple[Path | None, Path | None, str, str]:
    source_file = definition.get("actuals_source_file") or definition.get(
        "actuals_file"
    )
    material_file = definition.get("actuals_material_file")
    source_hash = str(definition.get("actuals_source_sha256") or "")
    material_hash = str(definition.get("actuals_material_sha256") or "")
    if not source_file:
        return None, None, source_hash, material_hash
    root = get_repo_root()
    source_path = resolve_path(str(source_file), root)
    material_path = resolve_path(str(material_file), root) if material_file else None
    return source_path, material_path, source_hash, material_hash


def _read_promo_material(
    source_path: Any,
    material_path: Any,
    source_hash: str,
    material_hash: str,
) -> tuple[bytes | None, bytes | None, str | None]:
    if material_path is None or len(source_hash) != 64 or len(material_hash) != 64:
        return None, None, "Generația promo nu are materializarea JSON verificabilă."
    if not source_path.is_file():
        return None, None, f"Raportul promo `{source_path}` nu exista."
    if not material_path.is_file():
        return None, None, f"Materializarea promo `{material_path}` nu exista."
    try:
        source_bytes = source_path.read_bytes()
        material_bytes = material_path.read_bytes()
    except OSError as exc:
        return None, None, f"Generația promo nu poate fi citită: {exc}."
    if hashlib.sha256(source_bytes).hexdigest() != source_hash:
        return None, None, "Sursa originală promo nu corespunde hashului aprobat."
    if hashlib.sha256(material_bytes).hexdigest() != material_hash:
        return None, None, "Materializarea promo nu corespunde hashului aprobat."
    return source_bytes, material_bytes, None


def _parsed_material_rows(
    payload: dict[str, Any],
    *,
    source_hash: str,
    configured_cutoff: str,
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], Decimal]]:
    if (
        payload.get("version") != 1
        or payload.get("source_sha256") != source_hash
        or not isinstance(payload.get("rows"), list)
    ):
        raise ValueError("schema invalidă")
    if configured_cutoff and payload.get("cutoff_date") != configured_cutoff:
        raise ValueError("cutoff diferit de configurația aprobată")
    units: dict[tuple[str, str], int] = {}
    values: dict[tuple[str, str], Decimal] = {}
    for row in payload["rows"]:
        key, quantity, value = _validated_material_row(row)
        if key in units:
            raise ValueError("cheie promo duplicată")
        units[key] = quantity
        values[key] = value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if payload.get("report_rows") != len(units):
        raise ValueError("număr de rânduri inconsistent")
    if payload.get("promo_units") != sum(units.values()):
        raise ValueError("total de unități inconsistent")
    return units, values


def _validated_material_row(
    row: Any,
) -> tuple[tuple[str, str], int, Decimal]:
    if not isinstance(row, dict):
        raise ValueError("rând invalid")
    site_code = str(row.get("site_code") or "").strip()
    item_code = str(row.get("item_code") or "").strip()
    quantity = row.get("quantity")
    invalid_quantity = (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity == 0
    )
    if not site_code or not item_code or invalid_quantity:
        raise ValueError("identitate sau cantitate invalidă")
    value = Decimal(str(row.get("value") or "0"))
    if not value.is_finite():
        raise ValueError("valoare promo nefinita")
    assert isinstance(quantity, int)
    return (site_code, item_code), quantity, value


def _load_promo_actuals_material(
    definition: dict[str, Any],
) -> tuple[
    dict[tuple[str, str], int] | None,
    dict[tuple[str, str], Decimal] | None,
    str | None,
]:
    source_path, material_path, source_hash, material_hash = _promo_source_paths(
        definition
    )
    if source_path is None:
        return None, None, None
    _source, material_bytes, error = _read_promo_material(
        source_path,
        material_path,
        source_hash,
        material_hash,
    )
    if error is not None or material_bytes is None:
        return None, None, error
    assert material_path is not None
    cache_key = (
        str(source_path),
        source_path.stat().st_mtime_ns,
        str(material_path),
        material_path.stat().st_mtime_ns,
        source_hash,
        material_hash,
    )
    if cache_key in _promo_actuals_cache:
        return _promo_actuals_cache[cache_key]
    result: tuple[
        dict[tuple[str, str], int] | None,
        dict[tuple[str, str], Decimal] | None,
        str | None,
    ]
    try:
        payload = json.loads(material_bytes)
        if not isinstance(payload, dict):
            raise ValueError("schema invalidă")
        units, values = _parsed_material_rows(
            payload,
            source_hash=source_hash,
            configured_cutoff=str(definition.get("actuals_cutoff_date") or ""),
        )
        result = (units, values, None)
    except (InvalidOperation, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        result = (
            None,
            None,
            f"Materializarea promo `{material_path.name}` este invalidă: {exc}.",
        )
    _promo_actuals_cache[cache_key] = result
    return result


def load_promo_actual_units(
    definition: dict[str, Any],
    *,
    item_codes: list[str],
) -> PromoActualUnitsLoadResult:
    source_file = definition.get("actuals_source_file") or definition.get(
        "actuals_file"
    )
    if not source_file:
        return None, None
    units, _values, error = _load_promo_actuals_material(definition)
    if units is None or error is not None:
        return units, error
    allowed = {str(code).strip() for code in item_codes if str(code).strip()}
    if not allowed:
        return {}, None
    return {
        key: value
        for key, value in units.items()
        if key[1] in allowed and value > 0
    }, None


def load_promo_actual_values(
    definition: dict[str, Any],
    *,
    item_codes: list[str],
) -> tuple[dict[tuple[str, str], Decimal] | None, str | None]:
    units, error = load_promo_actual_units(definition, item_codes=item_codes)
    if units is None or error is not None:
        return None, error
    _all_units, values, material_error = _load_promo_actuals_material(definition)
    if values is None or material_error is not None:
        return values, material_error
    return {key: values.get(key, Decimal("0")) for key in units}, None


def promo_actuals_cutoff_date(definition: dict[str, Any]) -> date | None:
    source_file = definition.get("actuals_source_file") or definition.get(
        "actuals_file"
    )
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


def filtered_promo_actuals(
    definition: dict[str, Any],
    item_codes: list[str],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], Decimal]] | None:
    units, values, error = _load_promo_actuals_material(definition)
    if units is None:
        if error and (
            definition.get("actuals_source_file") or definition.get("actuals_file")
        ):
            raise PromoActualsError(error)
        return None
    if error is not None:
        raise PromoActualsError(error)
    allowed = {str(code).strip() for code in item_codes if str(code).strip()}
    actual_units = {
        key: value
        for key, value in units.items()
        if key[1] in allowed and value > 0
    }
    actual_values = {
        key: (values or {}).get(key, Decimal("0")) for key in actual_units
    }
    return actual_units, actual_values
