"""Monthly manager choice, separate from legacy Grile imports."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["automatic", "manual"]
    manual_target: Decimal | None = Field(default=None, gt=0, le=1000000, max_digits=12, decimal_places=2)
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_choice(self):
        if (self.mode == "manual") != (self.manual_target is not None):
            raise ValueError("Manual mode requires a positive target; automatic mode requires null")
        return self


class AgentTargetEntry(BaseModel):
    month: str
    agent_code: str
    mode: Literal["automatic", "manual"] = "automatic"
    manual_target: Decimal | None = None
    revision: int = 0


class AgentTargetState(AgentTargetEntry):
    automatic_target: Decimal | None = None
