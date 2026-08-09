from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ConfigDict, Field
from schemas.common import StrictApiModel, MonthStr

from auth import AuthClaims, require_auth
from composition import build_target_calculator_service
from permissions import require_privileged_access
from privileged_access import TARGET_FINALIZER_GROUPS_ENV, has_configured_group
from rate_limits import REPORT_EXPORT_LIMIT, TARGET_MUTATION_LIMIT, rate_limit
from services.target_calculator import TargetCalculatorService

router = APIRouter(prefix="/api/target-calculator", tags=["target-calculator"])


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


class TargetCalculationRequest(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    target_month: MonthStr
    total_target: Decimal = Field(gt=0)
    min_floor: Decimal = Field(default=Decimal("35000"), ge=0)
    previous_month_floor_pct: Decimal = Field(default=Decimal("0.90"), ge=0, le=2)
    previous_month_cap_pct: Decimal = Field(default=Decimal("1.70"), gt=0, le=3)
    seasonality_years: int = Field(default=3, ge=1, le=3)
    cohort_month: MonthStr | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class TargetFinalRow(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    site_code: str
    final_target: Decimal | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=500)
    override_reason: str | None = Field(default=None, min_length=1, max_length=500)


class TargetFinalRowsRequest(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    rows: list[TargetFinalRow] = Field(min_length=1)


class TargetFinalizeRequest(StrictApiModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)


class TargetApiErrorResponse(StrictApiModel):
    """Documented shape of explicit Target HTTPException responses."""

    detail: str | dict[str, object]


TargetErrorResponses = dict[int | str, dict[str, Any]]


TARGET_BAD_REQUEST_RESPONSES: TargetErrorResponses = {
    400: {"model": TargetApiErrorResponse},
}
TARGET_NOT_FOUND_RESPONSES: TargetErrorResponses = {
    404: {"model": TargetApiErrorResponse},
}
TARGET_CONFLICT_RESPONSES: TargetErrorResponses = {
    409: {"model": TargetApiErrorResponse},
}
TARGET_MUTATION_ERROR_RESPONSES: TargetErrorResponses = {
    **TARGET_BAD_REQUEST_RESPONSES,
    **TARGET_NOT_FOUND_RESPONSES,
    **TARGET_CONFLICT_RESPONSES,
}


class TargetContextResponse(StrictApiModel):
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


class TargetSourceMonth(StrictApiModel):
    month: str
    label: str
    role: str


class TargetHistoryValue(StrictApiModel):
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


class TargetSeasonalityYear(StrictApiModel):
    year_offset: int
    base_month: str
    target_month: str
    base_value: Decimal
    target_value: Decimal
    ratio: Decimal | None = None


class TargetSeasonalityDetails(StrictApiModel):
    store_factor: Decimal | None = None
    zone_factor: Decimal | None = None
    network_factor: Decimal | None = None
    blended_factor: Decimal | None = None
    used_factor: Decimal | None = None
    last_year_store_factor: Decimal | None = None
    multiyear_store_factor: Decimal | None = None
    weights: dict[str, Decimal] | None = None
    store_years: list[TargetSeasonalityYear] = Field(default_factory=list)
    zone_years: list[TargetSeasonalityYear] = Field(default_factory=list)
    network_years: list[TargetSeasonalityYear] = Field(default_factory=list)
    min: Decimal | None = None
    max: Decimal | None = None


class TargetTrendDetails(StrictApiModel):
    base_month: str | None = None
    ratio: Decimal | None = None
    weight: Decimal | None = None
    raw_adjustment: Decimal | None = None
    used_adjustment: Decimal | None = None
    min: Decimal | None = None
    max: Decimal | None = None


class TargetCalculationDetails(StrictApiModel):
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
    flags: list[str] = Field(default_factory=list)
    seasonality: TargetSeasonalityDetails | None = None
    trend: TargetTrendDetails | None = None


class TargetProfitabilityResponse(StrictApiModel):
    agent_count: int
    base_salary_per_agent: Decimal
    salary_cost_at_90_pct: Decimal
    operating_costs: Decimal | None = None
    accessory_margin_pct: Decimal | None = None
    break_even_gross_sales: Decimal | None = None
    forecast_sales: Decimal | None = None
    anomaly_flags: list[str] = Field(default_factory=list)


class TargetScenarioRowResponse(StrictApiModel):
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
    history: list[TargetHistoryValue] = Field(default_factory=list)
    calculation_details: TargetCalculationDetails = Field(
        default_factory=TargetCalculationDetails
    )
    note: str | None = None
    updated_at: str | None = None
    manager_override_target: Decimal | None = None
    manager_override_reason: str | None = None
    manager_override_at: str | None = None
    manager_override_revision: int | None = None
    profitability: TargetProfitabilityResponse | None = None


class TargetRegionalSummaryResponse(StrictApiModel):
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


class TargetSourceSummaryResponse(StrictApiModel):
    month: str
    label: str
    target: Decimal
    realized: Decimal
    actual_realized: Decimal
    is_forecast: bool
    forecast_factor: Decimal
    attainment_pct: Decimal | None = None


class TargetForecastRunResponse(StrictApiModel):
    id: int
    model_name: str
    model_mode: str
    variant: str
    generated_at: str
    source_month: str | None = None


class TargetForecastCoverageResponse(StrictApiModel):
    mode: str
    cutoff: str | None = None
    cutoff_min: str | None = None
    cutoff_max: str | None = None
    expected_store_count: int
    covered_store_count: int
    missing_site_codes: list[str] = Field(default_factory=list)


class TargetProfitabilityAssumptionsResponse(StrictApiModel):
    vat_ruleset_id: str
    vat_ruleset_hash: str | None = None
    vat_rule_id: str
    vat_effective_from: str | None = None
    vat_multiplier: Decimal
    vat_rate: Decimal
    salary_pnl_factor: Decimal
    meal_vouchers_per_agent: Decimal
    sales_commission_rate: Decimal
    salary_assumed_attainment: Decimal
    default_store_agent_count: int
    sun_plaza_agent_count: int
    base_salary_default: Decimal
    base_salary_high: Decimal
    target_rule_set_id: str | None = None
    target_rule_set_hash: str | None = None


class TargetProfitabilitySummaryResponse(StrictApiModel):
    status: str
    pnl_months: list[str] = Field(default_factory=list)
    pnl_store_count: int
    forecast_store_count: int
    forecast_run: TargetForecastRunResponse | None = None
    assumptions: TargetProfitabilityAssumptionsResponse | None = None
    salary_total: Decimal
    operating_costs_total: Decimal | None = None
    break_even_total: Decimal | None = None
    forecast_total: Decimal | None = None
    forecast_coverage: TargetForecastCoverageResponse | None = None
    forecast_below_break_even_count: int
    target_below_break_even_count: int
    input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class TargetCalculationParams(StrictApiModel):
    seasonality_years: int | None = None
    seasonality_min: Decimal | None = None
    seasonality_max: Decimal | None = None
    trend_weight: Decimal | None = None
    trend_adjustment_min: Decimal | None = None
    trend_adjustment_max: Decimal | None = None
    previous_month_cap_pct: Decimal | None = None
    minimum_seasonality_base: Decimal | None = None
    strong_weights: dict[str, Decimal] = Field(default_factory=dict)
    weak_weights: dict[str, Decimal] = Field(default_factory=dict)
    new_store_weights: dict[str, Decimal] = Field(default_factory=dict)
    profitability: TargetProfitabilityAssumptionsResponse | None = None
    profitability_summary: TargetProfitabilitySummaryResponse | None = None


class TargetScenarioSummaryResponse(StrictApiModel):
    id: int
    target_month: str
    cohort_month: str
    total_target: Decimal
    min_floor: Decimal
    previous_month_floor_pct: Decimal
    status: str
    revision: int
    calculation_method: str
    source_months: list[TargetSourceMonth] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    calculation_params: TargetCalculationParams = Field(
        default_factory=TargetCalculationParams
    )
    rule_set_id: str | None = None
    rule_set_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    rule_set_snapshot: dict[str, object] | None = None
    calculation_input_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    profitability_input_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
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
    regional_summary: list[TargetRegionalSummaryResponse] = Field(default_factory=list)
    source_summary: list[TargetSourceSummaryResponse] = Field(default_factory=list)
    profitability_summary: TargetProfitabilitySummaryResponse | None = None


class TargetStoreHistoryPointResponse(StrictApiModel):
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


class TargetStoreAgentResponse(StrictApiModel):
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


class TargetStoreDetailResponse(StrictApiModel):
    site_code: str
    locatie: str
    firma: str
    regional: str
    asm: str
    target_month: str
    cohort_month: str
    proposed_target: Decimal
    final_target: Decimal | None = None
    history: list[TargetStoreHistoryPointResponse] = Field(default_factory=list)
    latest: TargetStoreHistoryPointResponse | None = None
    best_month: TargetStoreHistoryPointResponse | None = None
    avg_sales_16m: Decimal
    agents: list[TargetStoreAgentResponse] = Field(default_factory=list)


get_target_calculator_service = build_target_calculator_service


@router.get("/context", responses=TARGET_NOT_FOUND_RESPONSES)
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
    return [TargetScenarioSummaryResponse.model_validate(item) for item in await svc.list_scenarios()]


@router.post("/scenarios/calculate", responses={
    **TARGET_BAD_REQUEST_RESPONSES,
    **TARGET_CONFLICT_RESPONSES,
})
async def calculate_scenario(
    body: TargetCalculationRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return TargetScenarioResponse.model_validate(await svc.calculate(body.model_dump()))


@router.patch("/scenarios/{scenario_id}/rows", responses=TARGET_MUTATION_ERROR_RESPONSES)
async def update_final_targets(
    scenario_id: int,
    body: TargetFinalRowsRequest,
    claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return TargetScenarioResponse.model_validate(
        await svc.save_final_targets(
            scenario_id,
            [row.model_dump() for row in body.rows],
            body.expected_revision,
            actor=claims.sub,
        )
    )


@router.post("/scenarios/{scenario_id}/finalize", responses=TARGET_MUTATION_ERROR_RESPONSES)
async def finalize_scenario(
    scenario_id: int,
    body: TargetFinalizeRequest,
    _claims: AuthClaims = Depends(require_target_owner),
    _rate_limit: None = Depends(rate_limit(TARGET_MUTATION_LIMIT)),
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return TargetScenarioResponse.model_validate(
        await svc.finalize(scenario_id, body.expected_revision)
    )


@router.get(
    "/scenarios/{scenario_id}/export",
    responses={
        **TARGET_NOT_FOUND_RESPONSES,
        **TARGET_CONFLICT_RESPONSES,
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


@router.get("/scenarios/{scenario_id}/stores/{site_code}", responses=TARGET_NOT_FOUND_RESPONSES)
async def get_store_detail(
    scenario_id: int,
    site_code: str,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetStoreDetailResponse:
    return TargetStoreDetailResponse.model_validate(
        await svc.get_store_detail(scenario_id, site_code)
    )


@router.get("/scenarios/{scenario_id}", responses={
    **TARGET_NOT_FOUND_RESPONSES,
    **TARGET_CONFLICT_RESPONSES,
})
async def get_scenario(
    scenario_id: int,
    svc: TargetCalculatorService = Depends(get_target_calculator_service),
)-> TargetScenarioResponse:
    return TargetScenarioResponse.model_validate(await svc.get_scenario_detail(scenario_id))
