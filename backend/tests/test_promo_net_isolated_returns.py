"""Tests for issue #194: preserve isolated negative return rows in promo
actuals materialization while keeping the report-level fail-closed behavior.

Bug: ``_positive_promo_rows()`` dropped every non-positive net key, so an
isolated -1 return on its own (site, item) was silently dropped. This made a
real regression of gross 244 with two isolated -1 returns look like 244 in
``promo_units``. The fix materializes every non-zero net key and lets the
Incentive layer keep filtering quantity > 0 so negative rows can never grant
or inflate agent incentive.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from fastapi import HTTPException
from openpyxl import Workbook

import services.imports as imports_module
from services.imports import (
    ImportsService,
    PromoActualsParseResult,
    _promo_actuals_material_bytes,
    _publish_promo_generation,
)
from services.promo_actuals import (
    filtered_promo_actuals,
    load_promo_actual_units,
    load_promo_actual_values,
)
from services.promo_actuals_parser import validate_promo_actuals_report
from services.promo_allocation import allocate_units_to_agents
from services.promo_copurchase import compute_promo_actuals_from_report
from services.product_lists import normalize_column_name


# --- helpers --------------------------------------------------------------


def _workbook_bytes(rows: list[tuple]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AccesoriPromoLunar"
    sheet.append(
        ["SiteCode", "Cod", "Promo Luna Curenta", "PromoValoare Luna Curenta"]
    )
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _fake_reader(dataframe: pd.DataFrame):
    def _reader(*_args, **_kwargs):
        return dataframe
    return _reader


def _reader_limits():
    return type(
        "L",
        (),
        {
            "max_rows": 10_000,
            "max_columns": 32,
            "max_cell_chars": 64,
            "max_total_cells": 1_000_000,
            "max_file_bytes": 32 * 1024 * 1024,
        },
    )()


def _parse(dataframe: pd.DataFrame) -> PromoActualsParseResult:
    return validate_promo_actuals_report(
        b"data",
        reader=_fake_reader(dataframe),
        reader_limits=_reader_limits(),
    )


# --- Parser-level tests ---------------------------------------------------


def test_parser_preserves_isolated_return_so_244_minus_1_minus_1_is_242() -> None:
    """Real regression: 244 - 1 - 1 must record promo_units == 242.

    S1/I1 carries the gross 244 sales. S2/I2 and S3/I3 each record an
    isolated -1 return. Under the old positive-only filter the two isolated
    returns were dropped and the report claimed 244. After the fix the
    material preserves the signed net of every key, so the sum is 242.
    """
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S2", "S3"],
            "Cod": ["I1", "I2", "I3"],
            "Promo Luna Curenta": [244, -1, -1],
            "PromoValoare Luna Curenta": [24400.00, -100.00, -100.00],
        }
    )
    parsed = _parse(dataframe)
    assert isinstance(parsed, PromoActualsParseResult)
    assert parsed.report_rows == 3
    assert parsed.promo_units == 242
    keys = {
        (row["site_code"], row["item_code"]): int(row["quantity"])
        for row in parsed.rows
    }
    assert keys == {("S1", "I1"): 244, ("S2", "I2"): -1, ("S3", "I3"): -1}
    assert parsed.promo_units == sum(int(row["quantity"]) for row in parsed.rows)


def test_parser_same_key_positive_minus_two_is_eight() -> None:
    """+10 / -2 same key nets to a single +8 row."""
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S1"],
            "Cod": ["I1", "I1"],
            "Promo Luna Curenta": [10, -2],
            "PromoValoare Luna Curenta": [100.00, -20.00],
        }
    )
    parsed = _parse(dataframe)
    assert parsed.report_rows == 1
    assert parsed.promo_units == 8
    assert parsed.rows[0]["quantity"] == 8
    assert parsed.rows[0]["value"] == "80.00"


def test_parser_same_key_positive_minus_two_omits_zero_net_key() -> None:
    """+2 / -2 nets to zero; key is dropped and the report fails closed."""
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S1"],
            "Cod": ["I1", "I1"],
            "Promo Luna Curenta": [2, -2],
            "PromoValoare Luna Curenta": [20.00, -20.00],
        }
    )
    with pytest.raises(HTTPException) as exc:
        _parse(dataframe)
    assert exc.value.status_code == 400
    assert "pozitive" in str(exc.value.detail).casefold()


def test_parser_mixed_keys_promo_units_equals_signed_sum_of_rows() -> None:
    """Mixed site/item: sum(rows.quantity) must equal promo_units invariant."""
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S1", "S2", "S2", "S3", "S4"],
            "Cod": ["I1", "I2", "I3", "I4", "I5", "I6"],
            "Promo Luna Curenta": [5, -2, 7, 1, -1, -3],
            "PromoValoare Luna Curenta": [
                "50.00",
                "-20.00",
                "70.00",
                "10.00",
                "-10.00",
                "-30.00",
            ],
        }
    )
    parsed = _parse(dataframe)
    # S1/I1=5, S1/I2=-2, S2/I3=7, S2/I4=1, S3/I5=-1, S4/I6=-3 => signed sum 7
    assert parsed.report_rows == 6
    assert parsed.promo_units == 7
    assert parsed.promo_units == sum(int(row["quantity"]) for row in parsed.rows)


def test_parser_all_returns_report_remains_fail_closed() -> None:
    """A report with only isolated returns must still be rejected.

    Negatives being materializable in a mixed report must not flip the
    fail-closed check. An all-returns report has no positive net key.
    """
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S2", "S3"],
            "Cod": ["I1", "I2", "I3"],
            "Promo Luna Curenta": [-1, -2, -3],
            "PromoValoare Luna Curenta": ["-10.00", "-20.00", "-30.00"],
        }
    )
    with pytest.raises(HTTPException) as exc:
        _parse(dataframe)
    assert exc.value.status_code == 400
    assert "pozitive" in str(exc.value.detail).casefold()


# --- Material-bytes invariant --------------------------------------------


def test_material_bytes_preserve_signed_promo_units_and_signed_rows() -> None:
    """The material JSON must round-trip the signed rows and the signed sum."""
    dataframe = pd.DataFrame(
        {
            "SiteCode": ["S1", "S2", "S3"],
            "Cod": ["I1", "I2", "I3"],
            "Promo Luna Curenta": [244, -1, -1],
            "PromoValoare Luna Curenta": [24400.00, -100.00, -100.00],
        }
    )
    parsed = _parse(dataframe)
    source_sha256 = hashlib.sha256(b"source").hexdigest()
    material = _promo_actuals_material_bytes(
        parsed,
        source_sha256=source_sha256,
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )
    payload = json.loads(material)
    assert payload["promo_units"] == 242
    assert payload["report_rows"] == 3
    material_rows = {
        (row["site_code"], row["item_code"]): row["quantity"]
        for row in payload["rows"]
    }
    assert material_rows == {("S1", "I1"): 244, ("S2", "I2"): -1, ("S3", "I3"): -1}
    assert payload["promo_units"] == sum(r["quantity"] for r in payload["rows"])


# --- Material loader round-trip ------------------------------------------


def test_material_loader_returns_positive_only_for_incentive(
    tmp_path: Path,
) -> None:
    """Material round-trip: isolated negative rows survive bytes; the
    consumer filter keeps only quantity > 0 for Incentive allocation.
    """
    source_bytes = _workbook_bytes(
        [
            ("S1", "I1", 244, 24400.0),
            ("S2", "I2", -1, -100.0),
            ("S3", "I3", -1, -100.0),
        ]
    )
    source = tmp_path / "promo.xlsx"
    source.write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    parsed = ImportsService._validate_promo_actuals_report(source_bytes)
    material = _promo_actuals_material_bytes(
        parsed,
        source_sha256=source_sha,
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )
    material_path = tmp_path / "promo.json"
    material_path.write_bytes(material)
    material_sha = hashlib.sha256(material).hexdigest()
    definition = {
        "actuals_source_file": str(source),
        "actuals_source_sha256": source_sha,
        "actuals_material_file": str(material_path),
        "actuals_material_sha256": material_sha,
        "actuals_cutoff_date": "2026-06-15",
    }
    # Material itself contains the negative rows...
    payload = json.loads(material_path.read_text())
    assert payload["promo_units"] == 242
    assert any(row["quantity"] < 0 for row in payload["rows"])
    # ...but the Incentive filter strips them.
    units, units_error = load_promo_actual_units(
        definition, item_codes=["I1", "I2", "I3"]
    )
    assert units_error is None
    assert units == {("S1", "I1"): 244}
    values, values_error = load_promo_actual_values(
        definition, item_codes=["I1", "I2", "I3"]
    )
    assert values_error is None
    assert values == {("S1", "I1"): Decimal("24400.00")}
    # filtered_promo_actuals must also strip negatives for the copurchase
    # consumer.
    filtered = filtered_promo_actuals(definition, ["I1", "I2", "I3"])
    assert filtered is not None
    filtered_units, _filtered_values = filtered
    assert filtered_units == {("S1", "I1"): 244}


# --- End-to-end generation / materialization -----------------------------


def test_end_to_end_generation_materializes_isolated_returns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Flow-level: import -> generation -> on-disk material -> loader.

    The generation pointer, material file, and on-disk JSON must all carry
    the signed 242 units and the three non-zero rows.
    """
    config_path = tmp_path / "hub_specials.json"
    config_path.write_text(
        json.dumps(
            {
                "promotions": [
                    {
                        "key": "active",
                        "start_date": "2026-06-01",
                        "end_date": "2026-06-30",
                        "item_codes": ["I1", "I2", "I3"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        imports_module, "get_special_cards_config_path", lambda: config_path
    )
    data_dir = tmp_path / "data"
    monkeypatch.setattr(imports_module, "get_data_dir", lambda: data_dir)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "AccesoriPromoLunar"
    sheet.append(
        ["SiteCode", "Cod", "Promo Luna Curenta", "PromoValoare Luna Curenta"]
    )
    sheet.append(["S1", "I1", 244, 24400.0])
    sheet.append(["S2", "I2", -1, -100.0])
    sheet.append(["S3", "I3", -1, -100.0])
    stream = BytesIO()
    workbook.save(stream)
    content = stream.getvalue()

    parsed = validate_promo_actuals_report(
        content,
        reader=imports_module.read_spreadsheet_frame,
        reader_limits=imports_module.PROMO_ACTUALS_SPREADSHEET_LIMITS,
    )
    actuals_material = _promo_actuals_material_bytes(
        parsed,
        source_sha256=hashlib.sha256(content).hexdigest(),
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )
    config = imports_module.load_promo_config(
        data_dir=data_dir,
        expected_pointer_sha256=None,
        config_path=config_path,
        pointer_sha256=imports_module._promo_pointer_sha256,
    )
    imports_module.update_promo_config(
        config,
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
        sheet_name=imports_module.PROMO_REPORT_SHEET,
    )
    _generation_id, _cfg_sha, source_sha, material_sha = imports_module.publish_promo_config(
        data_dir=data_dir,
        config=config,
        content=content,
        suffix=".xlsx",
        actuals_material=actuals_material,
        parser_resources={"rows": 3},
        expected_pointer_sha256=None,
        validate_config=imports_module.validate_special_cards_config,
        publisher=_publish_promo_generation,
    )
    pointer = json.loads(
        (data_dir / "promo_generations" / "current.json").read_text()
    )
    assert pointer["actuals_sha256"] == source_sha
    assert pointer["material_sha256"] == material_sha
    material_file = pointer["actuals_materials"][0]["file"]
    payload = json.loads(Path(material_file).read_text())
    assert payload["promo_units"] == 242
    assert payload["report_rows"] == 3
    material_rows = {
        (row["site_code"], row["item_code"]): row["quantity"]
        for row in payload["rows"]
    }
    assert material_rows == {("S1", "I1"): 244, ("S2", "I2"): -1, ("S3", "I3"): -1}


# --- Incentive safety ----------------------------------------------------


def test_incentive_allocation_clamps_negative_promo_units() -> None:
    """The allocator must never produce negative agent rows."""
    allocations = allocate_units_to_agents(
        244,
        [("Agent1", 60), ("Agent2", 30)],
    )
    total_allocated = sum(units for _agent, units in allocations)
    assert total_allocated == 244
    assert all(units >= 0 for _agent, units in allocations)

    # Negative input must clamp to zero and return no allocations.
    assert allocate_units_to_agents(-1, [("Agent1", 5)]) == []
    # Zero input also returns nothing.
    assert allocate_units_to_agents(0, [("Agent1", 5)]) == []


def test_incentive_compute_path_filters_negatives_before_unnest(
    tmp_path: Path,
) -> None:
    """End-to-end Incentive safety: isolated negative rows in the material
    must not enter the SQL UNNEST vectors, must not produce extra agents,
    and must not flip sign to increase incentive.
    """
    source_bytes = _workbook_bytes(
        [
            ("S1", "I1", 244, 24400.0),
            ("S2", "I2", -1, -100.0),
            ("S3", "I3", -1, -100.0),
        ]
    )
    source = tmp_path / "promo.xlsx"
    source.write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    parsed = ImportsService._validate_promo_actuals_report(source_bytes)
    material = _promo_actuals_material_bytes(
        parsed,
        source_sha256=source_sha,
        import_month="2026-06",
        cutoff_date=date(2026, 6, 15),
    )
    material_path = tmp_path / "promo.json"
    material_path.write_bytes(material)
    material_sha = hashlib.sha256(material).hexdigest()

    definition = {
        "actuals_source_file": str(source),
        "actuals_source_sha256": source_sha,
        "actuals_material_file": str(material_path),
        "actuals_material_sha256": material_sha,
        "actuals_cutoff_date": "2026-06-15",
        "start_date": date(2026, 6, 1),
        "end_date": date(2026, 6, 30),
    }

    conn = AsyncMock()
    # The copurchase SQL is expected to receive UNNEST vectors that contain
    # only the single positive key (S1, I1, 244). Provide a single matched
    # reporting row so the test exercises the full path.

    class FakeRow(dict):
        def __getattr__(self, name):
            return self[name]

        def __init__(self, **kw):
            super().__init__(**kw)

    conn.fetch = AsyncMock(
        return_value=[
            FakeRow(
                site_code="S1",
                item_code="I1",
                promo_units=244,
                agent="Agent1",
                positive_qty=60,
            ),
            FakeRow(
                site_code="S1",
                item_code="I1",
                promo_units=244,
                agent="Agent2",
                positive_qty=30,
            ),
        ]
    )

    result = asyncio.run(
        compute_promo_actuals_from_report(
            conn,
            month="2026-06",
            definition=definition,
            item_codes=["I1", "I2", "I3"],
            firma=None,
            regional=None,
            asm=None,
            site_code=None,
            agent=None,
        )
    )

    # UNNEST vectors must contain only the positive (S1, I1, 244) triple.
    call_args = conn.fetch.await_args.args
    sql = call_args[0]
    assert "UNNEST($2::TEXT[], $3::TEXT[], $4::INT[])" in sql
    sites = call_args[2]
    codes = call_args[3]
    units = call_args[4]
    assert sites == ["S1"]
    assert codes == ["I1"]
    assert units == [244]

    # The result must reflect only the positive 244 unit allocation, split
    # between the two positive candidates by positive sales share.
    assert result is not None
    assert result.discounted_units == 244
    # No negative agent entries, no inflated incentive from the isolated -1
    # returns, and no extra agents beyond the candidates and the standard
    # "-" remainder bucket (caller responsibility, unrelated to this fix).
    assert all(value >= 0 for value in result.excluded_units.values())
    assert all(value >= 0 for value in result.excluded_discount_values.values())
    assert set(result.excluded_units).issubset(
        {("S1", "Agent1", "I1"), ("S1", "Agent2", "I1"), ("S1", "-", "I1")}
    )
    # The "-" bucket, if present, must be the leftover from the positive
    # 244 figure minus the share the two candidates cover; it must NOT be
    # derived from the isolated -1 returns.
    total_allocated = sum(result.excluded_units.values())
    assert total_allocated == 244
