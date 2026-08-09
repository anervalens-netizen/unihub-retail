from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class StrictApiModel(BaseModel):
    """Fail-closed base for every public request and response contract."""

    model_config = ConfigDict(extra="forbid")


MonthStr = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
PercentageFloat = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
PercentageInt = Annotated[int, Field(ge=0, le=100)]
