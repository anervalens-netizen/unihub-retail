from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import asyncpg
import pandas as pd


CODE_COLUMN_ALIASES = ("cod", "item_code", "cod_produse_focus", "cod_produs")
ITEM_NAME_COLUMN_ALIASES = ("itemname", "item_name", "denumire", "produs")


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_path(raw_path: str, base_dir: Path) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def get_data_dir() -> Path:
    configured = os.getenv("UNIHUB_DATA_DIR")
    if configured:
        return resolve_path(configured, get_repo_root())

    local_data_dir = get_repo_root() / "data"
    return local_data_dir


def normalize_column_name(value: Any) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", str(value))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


def _read_excel_with_auto_header(
    source: str | Path, sheet_name: str | int = 0
) -> pd.DataFrame:
    raw_df = pd.read_excel(source, header=None, sheet_name=sheet_name)
    header_row_index = 0
    for idx in range(min(len(raw_df.index), 10)):
        normalized_values = {
            normalize_column_name(value)
            for value in raw_df.iloc[idx].tolist()
            if str(value).strip() and str(value).strip().lower() != "nan"
        }
        if normalized_values.intersection(CODE_COLUMN_ALIASES):
            header_row_index = idx
            break

    header_row = raw_df.iloc[header_row_index].tolist()
    headers: list[str] = []
    for idx, value in enumerate(header_row):
        cleaned = str(value).strip()
        headers.append(cleaned or f"Unnamed: {idx}")

    data_df = raw_df.iloc[header_row_index + 1 :].copy()
    data_df.columns = headers
    data_df = data_df.dropna(how="all")
    return data_df.reset_index(drop=True)


def load_product_code_rows(
    source: str | Path, sheet_name: str | int = 0
) -> list[dict[str, str | None]]:
    df = _read_excel_with_auto_header(source, sheet_name=sheet_name)
    normalized_map = {normalize_column_name(column): column for column in df.columns}

    code_column = next(
        (
            normalized_map[alias]
            for alias in CODE_COLUMN_ALIASES
            if alias in normalized_map
        ),
        None,
    )
    if code_column is None:
        raise ValueError("Fisierul nu contine o coloana de cod produs recognoscibila")

    item_name_column = next(
        (
            normalized_map[alias]
            for alias in ITEM_NAME_COLUMN_ALIASES
            if alias in normalized_map
        ),
        None,
    )

    seen_codes: set[str] = set()
    rows: list[dict[str, str | None]] = []
    for record in df.to_dict(orient="records"):
        item_code = str(record.get(code_column, "")).strip()
        if not item_code or item_code.lower() == "nan" or item_code in seen_codes:
            continue
        seen_codes.add(item_code)
        item_name = None
        if item_name_column:
            raw_item_name = record.get(item_name_column)
            if raw_item_name is not None:
                cleaned_name = str(raw_item_name).strip()
                item_name = (
                    cleaned_name
                    if cleaned_name and cleaned_name.lower() != "nan"
                    else None
                )
        rows.append({"item_code": item_code, "item_name": item_name})
    return rows


async def sync_focus_products(
    conn: asyncpg.Connection,
    source: str | Path,
) -> int:
    rows = load_product_code_rows(source)
    item_codes = [row["item_code"] for row in rows]
    latest_names: dict[str, str] = {}

    if item_codes:
        sales_rows = await conn.fetch(
            """
            SELECT DISTINCT ON (item_code) item_code, item_name
            FROM sales_transactions
            WHERE item_code = ANY($1::TEXT[])
            ORDER BY item_code, import_month DESC, sale_date DESC
            """,
            item_codes,
        )
        latest_names = {
            str(row["item_code"]): str(row["item_name"])
            for row in sales_rows
            if row["item_name"]
        }

    async with conn.transaction():
        if item_codes:
            await conn.execute(
                "DELETE FROM focus_products WHERE NOT (item_code = ANY($1::TEXT[]))",
                item_codes,
            )
        else:
            await conn.execute("DELETE FROM focus_products")

        await conn.executemany(
            """
            INSERT INTO focus_products (item_code, item_name)
            VALUES ($1, $2)
            ON CONFLICT (item_code) DO UPDATE
            SET item_name = COALESCE(EXCLUDED.item_name, focus_products.item_name)
            """,
            [
                (
                    row["item_code"],
                    row["item_name"] or latest_names.get(str(row["item_code"])),
                )
                for row in rows
            ],
        )

    return len(rows)
