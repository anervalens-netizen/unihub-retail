from __future__ import annotations

from decimal import Decimal
import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


class StrictApiModel(BaseModel):
    """Fail-closed base for every public request and response contract."""

    model_config = ConfigDict(extra="forbid")


MonthStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
BoundedText32 = Annotated[str, StringConstraints(min_length=1, max_length=32)]
BoundedText120 = Annotated[str, StringConstraints(min_length=1, max_length=120)]
BoundedCode64 = Annotated[str, StringConstraints(min_length=1, max_length=64)]
BoundedListItem100 = Annotated[str, StringConstraints(min_length=1, max_length=100)]
Year2018To2100 = Annotated[int, Field(ge=2018, le=2100)]
MonthNumber = Annotated[int, Field(ge=1, le=12)]
Limit100 = Annotated[int, Field(ge=1, le=100)]
Limit500 = Annotated[int, Field(ge=1, le=500)]
Limit2000 = Annotated[int, Field(ge=1, le=2000)]
Offset100000 = Annotated[int, Field(ge=0, le=100_000)]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
PercentageFloat = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
PercentageInt = Annotated[int, Field(ge=0, le=100)]


_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_month_window(value: str) -> str:
    months = value.split(",")
    if not months or any(not _MONTH_RE.fullmatch(month) for month in months):
        raise ValueError("months must be comma-separated YYYY-MM values")
    if len(months) != len(set(months)):
        raise ValueError("months must contain unique values")
    return value


MonthWindowStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=120),
    AfterValidator(_validate_month_window),
]
