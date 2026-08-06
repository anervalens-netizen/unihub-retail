from __future__ import annotations

import re
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import AuthClaims, require_auth
from db.connection import get_pool
from permissions import require_privileged_access
from privileged_access import TARGET_FINALIZER_GROUPS_ENV, has_configured_group
from rate_limits import REPORT_EXPORT_LIMIT, TARGET_MUTATION_LIMIT, rate_limit
from repositories.target_calculator import TargetCalculatorRepository
from services.target_calculator import TargetCalculatorService

router = APIRouter(prefix="/api/target-calculator", tags=["target-calculator"])
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def can_finalize_targets(claims: AuthClaims) -> bool:
    return has_configured_group(claims.groups, TARGET_FINALIZER_GROUPS_ENV)


def require_target_owner(
    request: Request,
    claims: AuthClaims = Depends(require_auth),
) -> AuthClaims:
    return require_privileged_access(
        request=request,
        claims=claims,
        allowed=can_finalize_targets(claims),
        resource="target_calculator_finalization",
        detail="Doar proprietarul calculatorului poate calcula sau publica targetele finale.",
        fallback_route="/api/target-calculator/scenarios",
    )


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
    override_reason: str | None = Field(default=None, min_length=1, max_length=500)


class TargetFinalRowsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    rows: list[TargetFinalRow] = Field(min_length=1)


class TargetFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class TargetOpenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class TargetContextResponse(TargetOpenModel):
    latest_sales_month: str
    suggested_target_month: str
    suggested_cohort_month: str
    suggested_total_target: Decimal
    default_min_floor: Decimal
    default_previous_month_floor_pct: Decimal
    default_previous_month_cap_pct: Decimal
    default_seasonality_years: int
    active_store_count: int
    regionals: list[str]
    can_finalize: bool


class TargetSourceMonth(TargetOpenModel):
    month: str
    label: str
    role: str


class TargetHistoryValue(TargetOpenModel):
    month: str
    label: str
    role: str
    target: Decimal
    realized: Decimal
    actual_realized: Decimal | None = None
    is_forecast: bool = False
    forecast_factor: Decimal = Decimal("1")
    attainment_pct: Decimal | None = None
    weight: Decimal = Decimal("0")


class TargetSeasonalityYear(TargetOpenModel):
    year_offset: int
    base_month: str
    target_month: str
    base_value: Decimal
    target_value: Decimal
    ratio: Decimal | None = None


class TargetSeasonalityDetails(TargetOpenModel):
    store_factor: Decimal | None = None
    zone_factor: Decimal | None = None
    network_factor: Decimal | None = None
    blended_factor: Decimal | None = None
    used_factor: Decimal | None = None
    last_year_store_factor: Decimal | None = None
    multiyear_store_factor: Decimal | None = None
    weights: dict[str, Decimal] | None = None
    store_years: list[TargetSeasonalityYear] = []
    zone_years: list[TargetSeasonalityYear] = []
    network_years: list[TargetSeasonalityYear] = []
    min: Decimal | None = None
    max: Decimal | None = None


class TargetTrendDetails(TargetOpenModel):
    base_month: str | None = None
    ratio: Decimal | None = None
    weight: Decimal | None = None
    raw_adjustment: Decimal | None = None
    used_adjustment: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None


class TargetCalculationDetails(TargetOpenModel):
    method: str | None = None
    seasonality_years: int | None = None
    current_month: str | None = None
    current_forecast: Decimal | None = None
    raw_estimate: Decimal | None = None
    floor_target: Decimal | None = None
    cap_target: Decimal | None = None
    allocation_reason: str | None = None
    is_floor_limited: bool | None = None
    is_cap_limited: bool | None = None
    flags: list[str] = []
    seasonality: TargetSeasonalityDetails | None = None
    trend: TargetTrendDetails | None = None


class TargetProfitabilityResponse(TargetOpenModel):
    agent_count: int
    base_salary_per_agent: Decimal
    salary_cost_at_90_pct: Decimal
    operating_costs: Decimal | None = None
    accessory_margin_pct: Decimal | None = None
    break_even_gross_sales: Decimal | None = None
    forecast_sales: Decimal | None = None
    anomaly_flags: list[str] = []


class TargetScenarioRowResponse(TargetOpenModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    calculated_weight: Decimal
    normalized_weight: Decimal | None = None
    floor_target: Decimal
    cap_target: Decimal | None = None
    proposed_target: Decimal
    final_target: Decimal | None = None
    is_floor_limited: bool = False
    is_cap_limited: bool = False
    history: list[TargetHistoryValue] = []
    calculation_details: TargetCalculationDetails = TargetCalculationDetails()
    note: str | None = None
    updated_at: str | None = None
    profitability: TargetProfitabilityResponse | None = None


class TargetRegionalSummaryResponse(TargetOpenModel):
    regional: str
    store_count: int
    floor_total: Decimal
    proposed_total: Decimal
    final_total: Decimal
    current_month: str | None = None
    current_forecast_total: Decimal = Decimal("0")
    proposed_growth_vs_current_pct: Decimal | None = None
    final_growth_vs_current_pct: Decimal | None = None
    last_year_base_month: str | None = None
    last_year_target_month: str | None = None
    last_year_base_total: Decimal = Decimal("0")
    last_year_target_total: Decimal = Decimal("0")
    last_year_growth_pct: Decimal | None = None


class TargetSourceSummaryResponse(TargetOpenModel):
    month: str
    label: str
    target: Decimal
    realized: Decimal
    actual_realized: Decimal
    is_forecast: bool
    forecast_factor: Decimal
    attainment_pct: Decimal | None = None


class TargetForecastRunResponse(TargetOpenModel):
    id: int
    model_name: str
    model_mode: str
    variant: str
    generated_at: str
    source_month: str | None = None


class TargetProfitabilitySummaryResponse(TargetOpenModel):
    status: str
    pnl_months: list[str] = []
    pnl_store_count: int
    forecast_store_count: int
    forecast_run: TargetForecastRunResponse | None = None
    assumptions: TargetOpenModel | None = None
    salary_total: Decimal
    operating_costs_total: Decimal | None = None
    break_even_total: Decimal | None = None
    forecast_total: Decimal | None = None
    forecast_coverage: TargetOpenModel | None = None
    forecast_below_break_even_count: int
    target_below_break_even_count: int


class TargetCalculationParams(TargetOpenModel):
    seasonality_years: int | None = None
    profitability: TargetOpenModel | None = None
    profitability_summary: TargetOpenModel | None = None


class TargetScenarioSummaryResponse(TargetOpenModel):
    id: int
    target_month: str
    cohort_month: str
    total_target: Decimal
    min_floor: Decimal
    previous_month_floor_pct: Decimal
    status: str
    revision: int
    calculation_method: str
    source_months: list[TargetSourceMonth] = []
    warnings: list[str] = []
    calculation_params: TargetCalculationParams = TargetCalculationParams()
    store_count: int = 0
    proposed_total: Decimal = Decimal("0")
    final_total: Decimal = Decimal("0")
    pending_final_count: int = 0
    created_at: str
    updated_at: str
    finalized_at: str | None = None


class TargetScenarioResponse(TargetScenarioSummaryResponse):
    remaining_difference: Decimal
    pending_final_count: int
    floor_limited_count: int
    manual_adjustments_count: int
    cap_limited_count: int = 0
    manager_overrides_count: int = 0
    rows: list[TargetScenarioRowResponse]
    regional_summary: list[TargetRegionalSummaryResponse] = []
    source_summary: list[TargetSourceSummaryResponse] = []
    profitability_summary: TargetProfitabilitySummaryResponse | None = None


class TargetStoreHistoryPointResponse(TargetOpenModel):
    month: str
    total_sales: Decimal
    target_value: Decimal
    target_pct: Decimal | None = None
    total_quantity: int
    receipt_count: int
    cartele_qty: int
    avg_receipt: Decimal | None = None
    bon2acc_pct: Decimal | None = None
    focus_pct: Decimal | None = None
    active_agents: int
    working_days: int


class TargetStoreAgentResponse(TargetOpenModel):
    agent: str
    total_sales: Decimal
    sales_share_pct: Decimal
    total_quantity: int
    receipt_count: int
    avg_receipt: Decimal | None = None
    bon2acc_pct: Decimal | None = None
    focus_pct: Decimal | None = None
    active_months_16: int
    sales_16m: Decimal


class TargetStoreDetailResponse(TargetOpenModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    target_month: str
    cohort_month: str
    proposed_target: Decimal
    final_target: Decimal | None = None
    history: list[TargetStoreHistoryPointResponse] = []
    latest: TargetStoreHistoryPointResponse | None = None
    best_month: TargetStoreHistoryPointResponse | None = None
    avg_sales_16m: Decimal
    agents: list[TargetStoreAgentResponse] = []


async def get_target_calculator_service() -> TargetCalculatorService:
    pool = await get_pool()
    return TargetCalculatorService(TargetCalculatorRepository(pool))


@router.get("/context")
async def get_context(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
    claims: AuthClaims = Depends(require_auth),
)-> TargetContextResponse:
    return TargetContextResponse.model_validate({
        **await svc.get_context(),
        "can_finalize": can_finalize_targets(claims),
    })


@router.get("/scenarios")
async def list_scenarios(
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> list[TargetScenarioSummaryResponse]:
    return await svc.list_scenarios()


@router.post("/scenarios/calculate")
async def calculate_scenario(
    body: TargetCalculationRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return await svc.calculate(body.model_dump())


@router.patch("/scenarios/{scenario_id}/rows")
async def update_final_targets(
    scenario_id: int,
    body: TargetFinalRowsRequest,
    claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return await svc.save_final_targets(
        scenario_id,
        [row.model_dump() for row in body.rows],
        body.expected_revision,
        actor=claims.sub,
    )


@router.post("/scenarios/{scenario_id}/finalize")
async def finalize_scenario(
    scenario_id: int,
    body: TargetFinalizeRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return await svc.finalize(scenario_id, body.expected_revision)


@router.get(
    "/scenarios/{scenario_id}/export",
    responses={
        200: {
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
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
)-> TargetStoreDetailResponse:
    return await svc.get_store_detail(scenario_id, site_code)


@router.get("/scenarios/{scenario_id}")
async def get_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return await svc.get_scenario_detail(scenario_id)
