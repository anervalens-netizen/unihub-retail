#!/usr/bin/env python3
"""Validate legacy sales workbooks without touching the database.

Legacy workbooks predate the current sales-import contract and do not contain
``Agent``, ``Categorie`` or ``SubCategorie``.  This tool only normalizes those
files in memory for strict offline validation and reporting.  It never creates
a canonical workbook and never promises that the source can be reimported.
Any future reimport requires a separately approved converter that expresses
``is_cartela`` explicitly.

Examples::

    python scripts/import_historical.py
    python scripts/import_historical.py --input-dir /path/to/historical
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from io import BytesIO
import json
import math
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.spreadsheet_safety import (  # noqa: E402
    HISTORY_SPREADSHEET_LIMITS,
    SpreadsheetParserMeasurement,
    SpreadsheetUploadError,
    validate_spreadsheet_upload,
)


BASE = Path(__file__).resolve().parent.parent.parent / "data" / "vanzari 2022, 2023 si 2024"

OLD_COLUMNS = [
    "Data",
    "SiteCode",
    "ItemCode",
    "ItemName",
    "Cantitate",
    "Brand",
    "Pret",
    "Valoare",
    "Locatie",
    "Firma",
    "ASM",
    "Regional",
    "Nr",
]

MAX_QUANTITY = 2_147_483_647
MAX_MONEY = 99_999_999.99


@dataclass(frozen=True, slots=True)
class HistoricalFileReport:
    """Validation result for one source workbook."""

    source: Path
    import_month: str
    rows_in_file: int
    rows_without_valid_asm: int
    stores: int
    parser_resources: dict[str, int | float | str | None]


def _normalize_firma(value: object) -> str:
    cleaned = str(value or "").strip()
    if cleaned.lower() == "mobiup":
        return "Mobiup"
    if cleaned.lower() == "mobicell":
        return "MobiCell"
    return cleaned


def _validate_numeric_column(
    df: pd.DataFrame,
    column: str,
    *,
    integer: bool = False,
) -> pd.Series:
    values = pd.to_numeric(df[column], errors="coerce")
    invalid = values.isna() | ~values.map(lambda value: math.isfinite(float(value)))
    if integer:
        invalid = invalid | ~values.map(
            lambda value: bool(pd.isna(value)) or float(value).is_integer()
        )
        invalid = invalid | (values.abs() > MAX_QUANTITY)
    else:
        invalid = invalid | (values.abs() > MAX_MONEY)
    if bool(invalid.any()):
        label = "Cantitate" if integer else column
        raise ValueError(f"Coloana {label} conține valori invalide.")
    return values.astype("int64") if integer else values


def _validate_identifiers(df: pd.DataFrame) -> None:
    # Rows without an ASM are intentionally ignored by the canonical Retail
    # import (TR locations / unallocated agents), so they remain valid source
    # rows for this offline validator.
    importable = df[~df["ASM"].fillna("").astype(str).str.strip().isin(["", "-"])]
    required = ("SiteCode", "ItemCode", "ItemName", "Locatie", "Firma", "Regional", "Nr")
    missing = [
        column
        for column in required
        if importable[column]
        .map(lambda value: bool(pd.isna(value)) or not str(value).strip())
        .any()
    ]
    if missing:
        raise ValueError(
            "Fișierul conține identificatori obligatorii lipsă: " + ", ".join(missing)
        )

    metadata_columns = ["Locatie", "Firma", "Regional", "ASM"]
    if not importable.empty:
        grouped = importable.groupby("SiteCode", dropna=False)[metadata_columns]
        conflicting = int((grouped.nunique(dropna=False) > 1).any(axis=1).sum())
        if conflicting:
            raise ValueError(
                f"Fișierul conține metadate contradictorii pentru {conflicting} magazine."
            )


def load_historical_df(path: Path | str) -> pd.DataFrame:
    """Load and strictly validate one legacy workbook.

    The returned frame contains only source columns.  Missing canonical fields
    are deliberately not synthesized: doing so would make a later workbook
    import ambiguous, especially for ``is_cartela``.
    """

    source = Path(path)
    content = source.read_bytes()
    measurement = SpreadsheetParserMeasurement("historical_sales")
    with measurement:
        try:
            preflight = validate_spreadsheet_upload(
                content,
                source.suffix,
                limits=HISTORY_SPREADSHEET_LIMITS,
            )
        except SpreadsheetUploadError as exc:
            raise ValueError(str(exc)) from exc
        measurement.set_preflight(preflight)
        with pd.ExcelFile(BytesIO(content)) as workbook:
            df = workbook.parse(sheet_name="MobiUp_MobiCell")
        df = df.rename(columns=lambda value: str(value).strip())

        missing = [column for column in OLD_COLUMNS if column not in df.columns]
        if missing:
            raise ValueError(f"Lipsesc coloane obligatorii: {', '.join(missing)}")

        df = df[OLD_COLUMNS].copy()
        try:
            df["Data"] = pd.to_datetime(
                df["Data"], format="%d.%m.%Y", errors="raise"
            ).dt.date
        except (TypeError, ValueError) as exc:
            raise ValueError("Coloana Data conține valori invalide.") from exc

        df["Cantitate"] = _validate_numeric_column(df, "Cantitate", integer=True)
        df["Pret"] = _validate_numeric_column(df, "Pret")
        df["Valoare"] = _validate_numeric_column(df, "Valoare")

        df["Nr"] = df["Nr"].fillna("").map(lambda value: str(value).strip())
        for column in ["SiteCode", "ItemCode", "ItemName", "Locatie", "Firma", "ASM", "Regional"]:
            df[column] = df[column].fillna("").map(lambda value: str(value).strip())
        df["Firma"] = df["Firma"].map(_normalize_firma)
        df["Brand"] = df["Brand"].where(pd.notna(df["Brand"]), None)
        df["Brand"] = df["Brand"].map(lambda value: str(value).strip() if isinstance(value, str) else value)

        _validate_identifiers(df)
        measurement.set_rows(len(df))
    result = df[OLD_COLUMNS].copy()
    result.attrs["parser_resource_stats"] = measurement.as_dict()
    return result


def detect_month(df: pd.DataFrame) -> str:
    """Return the single business month represented by a validated frame."""

    months = sorted({value.strftime("%Y-%m") for value in df["Data"]})
    if len(months) != 1:
        raise ValueError(f"Fișierul conține mai multe luni: {months}")
    return months[0]


def collect_files(base_dir: Path | str = BASE) -> list[Path]:
    """Collect legacy workbooks from the historical 2023 and 2024 folders."""

    root = Path(base_dir)
    files: list[Path] = []
    for year in ("2023", "2024"):
        year_dir = root / year
        if year_dir.exists():
            files.extend(sorted(year_dir.glob("*.xlsx")))
    return files


def validate_historical_file(path: Path | str) -> HistoricalFileReport:
    """Validate a workbook and return metadata without writing any file."""

    source = Path(path)
    df = load_historical_df(source)
    valid_asm = ~df["ASM"].fillna("").astype(str).str.strip().isin(["", "-"])
    return HistoricalFileReport(
        source=source,
        import_month=detect_month(df),
        rows_in_file=len(df),
        rows_without_valid_asm=int((~valid_asm).sum()),
        stores=int(df.loc[valid_asm, "SiteCode"].nunique()),
        parser_resources=dict(df.attrs["parser_resource_stats"]),
    )


def process_files(input_dir: Path | str = BASE) -> list[HistoricalFileReport]:
    """Validate all historical sources and return their offline reports."""

    return [validate_historical_file(path) for path in collect_files(input_dir)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validează offline fișierele istorice de vânzări"
    )
    parser.add_argument("--input-dir", type=Path, default=BASE)
    return parser


def main(input_dir: Path = BASE) -> int:
    try:
        reports = process_files(input_dir)
    except (OSError, ValueError, ImportError) as exc:
        print(f"EROARE — {exc}")
        return 1

    print(f"VALIDATED: {len(reports)} fișiere; fără conexiune sau mutații DB")
    for report in reports:
        print(
            f"  {report.source.name}: {report.import_month} | "
            f"{report.rows_in_file:,} rânduri | "
            f"{report.rows_without_valid_asm:,} fără ASM valid | "
            f"{report.stores:,} magazine"
        )
        print(
            "    parser_resources="
            + json.dumps(
                report.parser_resources,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__":
    args = build_parser().parse_args()
    raise SystemExit(main(args.input_dir))
