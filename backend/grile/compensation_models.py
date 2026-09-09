"""Manager-confirmed provisional V1 inputs; never salary actuals."""
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

Amount = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=12, decimal_places=2)]
Quantity = Annotated[int, Field(ge=0, le=100000)]

class CompensationValues(BaseModel):
    model_config = ConfigDict(extra='forbid')
    salary_base: Amount | None = None
    vouchers: Amount | None = None
    sim_quantity: Quantity | None = None
    epay_under_50: Quantity | None = None
    epay_over_50: Quantity | None = None
    incentive: Amount | None = None
    adjustment: Annotated[Decimal, Field(ge=-1000000, le=1000000, max_digits=12, decimal_places=2)] | None = None

class CompensationInput(CompensationValues):
    expected_revision: int = Field(ge=0)

class CompensationEntry(CompensationValues):
    month: str
    agent_code: str
    revision: int
