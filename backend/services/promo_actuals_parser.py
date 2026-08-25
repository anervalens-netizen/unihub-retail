from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable

import pandas as pd
from fastapi import HTTPException, status

from services.product_lists import normalize_column_name


PROMO_REPORT_SHEET = "AccesoriPromoLunar"
PROMO_REPORT_SITE_ALIASES = {"sitecode", "site_code", "site"}
PROMO_REPORT_CODE_ALIASES = {
    "cod",
    "item_code",
    "itemcode",
    "cod_produs",
}
PROMO_REPORT_QTY_ALIASES = {
    "promo_luna_curenta",
    "promo_qty",
    "cantitate_promo",
    "promo",
}
PROMO_REPORT_VALUE_ALIASES = {
    "promovaloare_luna_curenta",
    "promo_valoare_luna_curenta",
    "promo_value",
    "valoare_promo",
}


@dataclass(frozen=True, slots=True)
class PromoActualsParseResult:
    report_rows: int
    promo_units: int
    rows: tuple[dict[str, str | int], ...]

    def __iter__(self):
        yield self.report_rows
        yield self.promo_units

    def __eq__(self, other: object) -> bool:
        if isinstance(other, tuple) and len(other) == 2:
            return (self.report_rows, self.promo_units) == other
        if isinstance(other, PromoActualsParseResult):
            return (
                self.report_rows,
                self.promo_units,
                self.rows,
            ) == (
                other.report_rows,
                other.promo_units,
                other.rows,
            )
        return NotImplemented


SpreadsheetReader = Callable[..., pd.DataFrame]


def _column_for(
    columns: dict[str, str],
    aliases: set[str],
) -> str | None:
    return next(
        (columns[key] for key in aliases if key in columns),
        None,
    )


def _resolve_promo_columns(
    dataframe: pd.DataFrame,
) -> tuple[str, str, str, str | None]:
    columns = {
        normalize_column_name(column): str(column)
        for column in dataframe.columns
    }
    site = _column_for(columns, PROMO_REPORT_SITE_ALIASES)
    code = _column_for(columns, PROMO_REPORT_CODE_ALIASES)
    quantity = _column_for(columns, PROMO_REPORT_QTY_ALIASES)
    value = _column_for(columns, PROMO_REPORT_VALUE_ALIASES)
    if not site or not code or not quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Raportul trebuie sa contina coloanele SiteCode, Cod "
                "si Promo Luna Curenta"
            ),
        )
    return site, code, quantity, value


def _promo_quantity(raw_value: object) -> int | None:
    if raw_value is None or str(raw_value).strip() == "":
        return None
    try:
        quantity = Decimal(str(raw_value).strip())
    except (InvalidOperation, ValueError):
        quantity = Decimal("NaN")
    if (
        not quantity.is_finite()
        or quantity != quantity.to_integral_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cantitatile promo trebuie sa fie intregi finite",
        )
    return int(quantity)


def _promo_value(raw_value: object) -> Decimal:
    text = (
        ""
        if raw_value is None or pd.isna(raw_value)
        else str(raw_value).strip()
    )
    try:
        value = Decimal(text or "0")
    except (InvalidOperation, ValueError):
        value = Decimal("NaN")
    if not value.is_finite():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valorile promo trebuie sa fie finite",
        )
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _require_item_identity(site_code: str, item_code: str) -> None:
    invalid = (
        not site_code
        or site_code.casefold() == "nan"
        or not item_code
        or item_code.casefold() == "nan"
    )
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Fiecare cantitate promo nenula necesita SiteCode si Cod"
            ),
        )


def _non_zero_promo_rows(
    net_units: dict[tuple[str, str], int],
    net_values: dict[tuple[str, str], Decimal],
) -> tuple[dict[str, str | int], ...]:
    """Materialize every non-zero net key, including isolated negative returns.

    Mixed reports must preserve the signed net of every (site_code, item_code)
    key so that a regression such as gross 244 + isolated -1 + isolated -1
    records 242 in the material. Consumers that grant promo units (Incentive,
    copurchase) keep filtering value > 0 — the parser only materializes the
    full signed picture; the report-level fail-closed check still rejects
    all-returns reports without a positive net key.
    """
    rows: list[dict[str, str | int]] = []
    for (site_code, item_code), quantity in sorted(net_units.items()):
        if quantity == 0:
            continue
        value = net_values.get((site_code, item_code), Decimal("0"))
        rows.append(
            {
                "site_code": site_code,
                "item_code": item_code,
                "quantity": quantity,
                "value": (
                    f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
                ),
            }
        )
    return tuple(rows)


def validate_promo_actuals_report(
    content: bytes,
    *,
    sheet_name: str = PROMO_REPORT_SHEET,
    reader: SpreadsheetReader,
    reader_limits: Any,
) -> PromoActualsParseResult:
    try:
        dataframe = reader(
            content,
            sheet_name=sheet_name,
            limits=reader_limits,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Raportul trebuie sa contina foaia {sheet_name}",
        ) from exc
    site_column, code_column, quantity_column, value_column = (
        _resolve_promo_columns(dataframe)
    )
    net_units: dict[tuple[str, str], int] = {}
    net_values: dict[tuple[str, str], Decimal] = {}
    for index, raw_quantity in dataframe[quantity_column].items():
        quantity = _promo_quantity(raw_quantity)
        if quantity is None or quantity == 0:
            continue
        site_code = str(dataframe.at[index, site_column]).strip()
        item_code = str(dataframe.at[index, code_column]).strip()
        _require_item_identity(site_code, item_code)
        key = (site_code, item_code)
        net_units[key] = net_units.get(key, 0) + quantity
        if value_column is not None:
            net_values[key] = net_values.get(
                key,
                Decimal("0"),
            ) + _promo_value(dataframe.at[index, value_column])
    rows = _non_zero_promo_rows(net_units, net_values)
    if not any(int(row["quantity"]) > 0 for row in rows):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Raportul nu contine unitati promo nete pozitive",
        )
    return PromoActualsParseResult(
        report_rows=len(rows),
        promo_units=sum(int(row["quantity"]) for row in rows),
        rows=rows,
    )

