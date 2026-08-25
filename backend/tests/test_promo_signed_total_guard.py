from __future__ import annotations

import pandas as pd
import pytest
from fastapi import HTTPException

from services.promo_actuals_parser import validate_promo_actuals_report


def _reader(*_args, **_kwargs) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "SiteCode": ["S1", "S2"],
            "Cod": ["I1", "I2"],
            "Promo Luna Curenta": [1, -2],
            "PromoValoare Luna Curenta": [10.0, -20.0],
        }
    )


def _limits():
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


def test_parser_rejects_mixed_report_with_negative_signed_total() -> None:
    """Reject before publication when signed promo_units would violate API type."""
    with pytest.raises(HTTPException) as exc:
        validate_promo_actuals_report(
            b"data",
            reader=_reader,
            reader_limits=_limits(),
        )

    assert exc.value.status_code == 400
    assert "total promo net negativ" in str(exc.value.detail).casefold()
