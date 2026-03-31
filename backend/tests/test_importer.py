from __future__ import annotations

from pathlib import Path

from services.importer import detect_month, load_sales_dataframe, load_targets_dataframe


REPO_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR = REPO_DATA_DIR


def test_load_sales_dataframe_detects_month_and_flags() -> None:
    df = load_sales_dataframe(DATA_DIR / "vanzari_2026-02.xlsx")

    assert len(df) == 30846
    assert detect_month(df) == "2026-02"
    assert "is_cartela" in df.columns
    assert "is_return" in df.columns
    assert df["Nr"].map(lambda value: isinstance(value, str) and value != "").all()


def test_load_sales_dataframe_handles_alphanumeric_receipts() -> None:
    df = load_sales_dataframe(DATA_DIR / "vanzari_2025-03.xlsx")

    assert detect_month(df) == "2025-03"
    assert df["Nr"].str.contains(r"[A-Za-z]", regex=True).any()


def test_load_targets_dataframe_extracts_expected_months() -> None:
    targets = load_targets_dataframe(DATA_DIR / "Istoric targete.xlsx")

    assert len(targets) == 1230
    months = sorted({row["import_month"] for row in targets})
    assert months[0] == "2025-01"
    assert months[-1] == "2026-03"
    assert all(row["site_code"] for row in targets)
