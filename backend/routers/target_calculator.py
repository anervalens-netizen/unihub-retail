from __future__ import annotations

import re
from decimal import Decimal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from db.connection import get_pool
from repositories.target_calculator import TargetCalculatorRepository
from services.target_calculator import TargetCalculatorService

router = APIRouter(prefix="/api/target-calculator", tags=["target-calculator"])
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class TargetCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_month: str
    total_target: Decimal = Field(gt=0)
    min_floor: Decimal = Field(default=Decimal("35000"), ge=0)
    previous_month_floor_pct: Decimal = Field(default=Decimal("0.90"), ge=0, le=2)
    cohort_month: str | None = None

    @field_validator("target_month", "cohort_month")
    @classmethod
    def valid_month(cls, value: str | None) -> str | None:
        if value is not None and not MONTH_PATTERN.match(value):
            raise ValueError("Luna trebuie sa fie in format YYYY-MM")
        return value


class TargetFinalRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    final_target: Decimal = Field(ge=0)
    note: str | None = Field(default=None, max_length=500)


class TargetFinalRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[TargetFinalRow] = Field(min_length=1)


async def get_target_calculator_service() -> TargetCalculatorService:
    pool = await get_pool()
    return TargetCalculatorService(TargetCalculatorRepository(pool))


@router.get("/context")
async def get_context(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.get_context()


@router.get("/scenarios")
async def list_scenarios(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.list_scenarios()


@router.post("/scenarios/calculate")
async def calculate_scenario(
    body: TargetCalculationRequest,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.calculate(body.model_dump())


@router.patch("/scenarios/{scenario_id}/rows")
async def update_final_targets(
    scenario_id: int,
    body: TargetFinalRowsRequest,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.save_final_targets(
        scenario_id,
        [row.model_dump() for row in body.rows],
    )


@router.post("/scenarios/{scenario_id}/finalize")
async def finalize_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.finalize(scenario_id)


@router.get("/scenarios/{scenario_id}/export")
async def export_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    content, filename = await svc.export_excel(scenario_id)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.get_scenario_detail(scenario_id)
