from __future__ import annotations

import os
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import AuthClaims, require_auth
from db.connection import get_pool
from rate_limits import REPORT_EXPORT_LIMIT, TARGET_MUTATION_LIMIT, rate_limit
from repositories.target_calculator import TargetCalculatorRepository
from services.target_calculator import TargetCalculatorService

router = APIRouter(prefix="/api/target-calculator", tags=["target-calculator"])
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DEFAULT_FINALIZER_EMAILS = "aner.valens@gmail.com"


def can_finalize_targets(claims: AuthClaims) -> bool:
    allowed_emails = {
        email.strip().casefold()
        for email in os.getenv("TARGET_CALCULATOR_FINALIZER_EMAILS", DEFAULT_FINALIZER_EMAILS).split(",")
        if email.strip()
    }
    return claims.email.strip().casefold() in allowed_emails


def require_target_owner(claims: AuthClaims = Depends(require_auth)) -> AuthClaims:
    if not can_finalize_targets(claims):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doar proprietarul calculatorului poate calcula sau publica targetele finale.",
        )
    return claims


class TargetCalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_month: str
    total_target: Decimal = Field(gt=0)
    min_floor: Decimal = Field(default=Decimal("35000"), ge=0)
    previous_month_floor_pct: Decimal = Field(default=Decimal("0.90"), ge=0, le=2)
    previous_month_cap_pct: Decimal = Field(default=Decimal("1.70"), gt=0, le=3)
    seasonality_years: int = Field(default=3, ge=1, le=3)
    cohort_month: str | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("target_month", "cohort_month")
    @classmethod
    def valid_month(cls, value: str | None) -> str | None:
        if value is not None and not MONTH_PATTERN.match(value):
            raise ValueError("Luna trebuie sa fie in format YYYY-MM")
        return value


class TargetFinalRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    final_target: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)


class TargetFinalRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    rows: list[TargetFinalRow] = Field(min_length=1)


class TargetFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


async def get_target_calculator_service() -> TargetCalculatorService:
    pool = await get_pool()
    return TargetCalculatorService(TargetCalculatorRepository(pool))


@router.get("/context")
async def get_context(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
    claims: AuthClaims = Depends(require_auth),
):
    return {
        **await svc.get_context(),
        "can_finalize": can_finalize_targets(claims),
    }


@router.get("/scenarios")
async def list_scenarios(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.list_scenarios()


@router.post("/scenarios/calculate")
async def calculate_scenario(
    body: TargetCalculationRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.calculate(body.model_dump())


@router.patch("/scenarios/{scenario_id}/rows")
async def update_final_targets(
    scenario_id: int,
    body: TargetFinalRowsRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.save_final_targets(
        scenario_id,
        [row.model_dump() for row in body.rows],
        body.expected_revision,
    )


@router.post("/scenarios/{scenario_id}/finalize")
async def finalize_scenario(
    scenario_id: int,
    body: TargetFinalizeRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.finalize(scenario_id, body.expected_revision)


@router.get("/scenarios/{scenario_id}/export")
async def export_scenario(
    scenario_id: int,
    _rate_limit: None = Depends(rate_limit(REPORT_EXPORT_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    content, filename = await svc.export_excel(scenario_id)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/scenarios/{scenario_id}/stores/{site_code}")
async def get_store_detail(
    scenario_id: int,
    site_code: str,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.get_store_detail(scenario_id, site_code)


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
):
    return await svc.get_scenario_detail(scenario_id)
