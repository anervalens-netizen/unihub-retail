from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from services.importer import (
    SALES_COLUMNS,
    detect_month,
    is_month_final,
    load_sales_dataframe,
    load_targets_dataframe,
    normalize_firma,
)


def sales_workbook(rows: list[dict]) -> bytes:
    output = BytesIO()
    pd.DataFrame(rows, columns=SALES_COLUMNS).to_excel(output, index=False)
    return output.getvalue()


def sales_row(**overrides: object) -> dict:
    row: dict[str, object] = {
        "Data": "01.07.2099",
        "SiteCode": " SITE01 ",
        "ItemCode": " ITEM01 ",
        "ItemName": " Produs ",
        "Cantitate": 2,
        "Brand": " Brand ",
        "Pret": 10.125,
        "Valoare": 20.255,
        "Locatie": " Magazin ",
        "Firma": " mobiup ",
        "ASM": " Manager ",
        "Regional": " Regional ",
        "Nr": " BON-A1 ",
        "Categorie": " Accesorii ",
        "SubCategorie": " Test ",
        "Agent": " Agent ",
    }
    row.update(overrides)
    return row


def test_load_sales_dataframe_normalizes_and_flags_rows() -> None:
    content = sales_workbook(
        [
            sales_row(),
            sales_row(
                Data="02.07.2099",
                SiteCode="SITE02",
                Nr="BON2",
                Firma="MOBICELL",
                Cantitate=-1,
                Pret=0,
                Valoare=0,
                Brand=None,
                Categorie=None,
                SubCategorie=None,
            ),
        ]
    )

    frame = load_sales_dataframe(content)

    assert detect_month(frame) == "2099-07"
    assert list(frame["SiteCode"]) == ["SITE01", "SITE02"]
    assert list(frame["Firma"]) == ["Mobiup", "MobiCell"]
    assert list(frame["Nr"]) == ["BON-A1", "BON2"]
    assert list(frame["Pret"]) == [10.125, 0.0]
    assert list(frame["Valoare"]) == [20.255, 0.0]
    assert list(frame["is_cartela"]) == [False, True]
    assert list(frame["is_return"]) == [False, True]
    assert frame.loc[0, "Categorie"] == "Accesorii"
    assert frame.loc[1, "Categorie"] is None


def test_load_sales_dataframe_rejects_missing_columns() -> None:
    output = BytesIO()
    pd.DataFrame([{"Data": "01.07.2099"}]).to_excel(output, index=False)

    with pytest.raises(ValueError, match="Lipsesc coloane obligatorii"):
        load_sales_dataframe(output.getvalue())


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("Pret", None, "Pret"),
        ("Valoare", "invalid", "Valoare"),
        ("Cantitate", 1.5, "Cantitate"),
    ],
)
def test_load_sales_dataframe_rejects_invalid_numeric_values(
    column: str,
    value: object,
    message: str,
) -> None:
    content = sales_workbook([sales_row(**{column: value})])

    with pytest.raises(ValueError, match=message):
        load_sales_dataframe(content)


def test_load_sales_dataframe_rejects_duplicate_rows() -> None:
    row = sales_row()

    with pytest.raises(ValueError, match="duplicate"):
        load_sales_dataframe(sales_workbook([row, row]))


def test_load_sales_dataframe_rejects_missing_required_identifier() -> None:
    with pytest.raises(ValueError, match="identificatori obligatorii"):
        load_sales_dataframe(sales_workbook([sales_row(Agent=None)]))


def test_load_sales_dataframe_rejects_conflicting_store_metadata() -> None:
    with pytest.raises(ValueError, match="contradictorii"):
        load_sales_dataframe(
            sales_workbook(
                [sales_row(), sales_row(Nr="BON2", Locatie="Alt magazin")]
            )
        )


def test_detect_month_rejects_mixed_months() -> None:
    frame = pd.DataFrame({"Data": [date(2099, 7, 1), date(2099, 8, 1)]})

    with pytest.raises(ValueError, match="mai multe luni"):
        detect_month(frame)


def test_company_normalization_and_month_finality() -> None:
    assert normalize_firma(" MOBIUP ") == "Mobiup"
    assert normalize_firma("mobicell") == "MobiCell"
    assert normalize_firma("Alta Firma") == "Alta Firma"
    assert is_month_final("2000-01") is True
    assert is_month_final("9999-12") is False


def write_targets_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["", 2098, None, None, 2099])
    sheet.append(["SiteCode", "TG L01", "TG L02", "TG invalid", "TG L03"])
    sheet.append(["SITE01", 100.125, 200, 999, 300])
    sheet.append(["", 400, 500, 999, 600])
    sheet.append(["SITE02", None, 250.555, 999, None])
    workbook.save(path)


def test_load_targets_dataframe_extracts_years_and_skips_empty_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "targets.xlsx"
    write_targets_workbook(source)

    targets = load_targets_dataframe(source)

    assert targets == [
        {
            "site_code": "SITE01",
            "import_month": "2098-01",
            "target_value": Decimal("100.12"),
        },
        {
            "site_code": "SITE01",
            "import_month": "2098-02",
            "target_value": Decimal("200.00"),
        },
        {
            "site_code": "SITE01",
            "import_month": "2099-03",
            "target_value": Decimal("300.00"),
        },
        {
            "site_code": "SITE02",
            "import_month": "2098-02",
            "target_value": Decimal("250.56"),
        },
    ]
