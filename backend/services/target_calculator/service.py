"""Stable orchestration facade for Target Calculator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from repositories.target_calculator import (
    TargetCalculatorRepository,
    TargetScenarioVersionConflict,
)
from services.forecast import get_forecast_factor
from services.target_calculator.allocation import allocate_with_bounds, money
from services.target_calculator.context import build_target_context
from services.target_calculator.editing import validate_unique_final_rows
from services.target_calculator.export import build_target_excel
from services.target_calculator.finalization import finalization_error
from services.target_calculator.profitability import (
    ProfitabilityConstants,
    attach_profitability,
    fallback_profitability_assumptions,
    forecast_coverage,
    forecast_coverage_error,
    frozen_profitability,
    populate_profitability,
    profitability_assumptions,
    profitability_input_payload,
    saved_profitability_assumptions,
    saved_target_rule_set,
)
from services.target_calculator.proposal import ProposalContext, calculate_proposal
from services.target_calculator.rules import canonical_input_hash
from services.target_calculator.scenarios import is_editable_scenario
from services.target_calculator.seasonality import shift_month
from services.target_calculator.serialization import (
    build_scenario_detail,
    build_store_detail,
    regional_summary,
    serialize_header,
    serialize_row,
    serialize_store_agent,
    serialize_store_history,
    source_summary,
)
from services.target_rule_registry import TargetRuleSet


ForecastFactorLoader = Callable[[Any, str], Awaitable[Any]]
Allocator = Callable[[list[dict[str, Any]], Decimal], tuple[list[dict[str, Any]], list[str]]]

DEFAULT_MIN_FLOOR = Decimal("35000")
DEFAULT_PREVIOUS_MONTH_FLOOR_PCT = Decimal("0.90")
DEFAULT_PREVIOUS_MONTH_CAP_PCT = Decimal("1.70")
DEFAULT_SEASONALITY_YEARS = 3
MAX_SEASONALITY_YEARS = 3
DEFAULT_TREND_WEIGHT = Decimal("0.10")
DEFAULT_TREND_ADJUSTMENT_MIN = Decimal("0.95")
DEFAULT_TREND_ADJUSTMENT_MAX = Decimal("1.10")
DEFAULT_SEASONALITY_MIN = Decimal("0.70")
DEFAULT_SEASONALITY_MAX = Decimal("1.70")
MIN_SEASONALITY_BASE = Decimal("10000")
CALCULATION_METHOD = "seasonal_blended_multiyear_v2_ruleset"

PROFITABILITY_CONSTANTS = ProfitabilityConstants(
    salary_pnl_factor=Decimal("1.6955"),
    meal_vouchers_per_agent=Decimal("480"),
    sales_commission_rate=Decimal("0.03"),
    salary_assumed_attainment=Decimal("0.90"),
    default_store_agent_count=2,
    sun_plaza_agent_count=3,
    base_salary_default=Decimal("2400"),
    base_salary_high=Decimal("2600"),
    base_salary_high_site_codes=frozenset({
        "AFICOTRO", "AUCHMIL2", "AUCHMILI", "AUCHTRIC", "CCTCIT", "CJIULMALL",
        "CJPPOL", "CLUJCFPOL", "CORALEX", "COTROCENI", "CRFFEER", "CTAUCH",
        "CTCITYPRK", "CTCORA", "CTCRFTOM", "CTVIVO", "MC-MEGAMALL", "MCRFBAL",
        "MEGAMALL", "PRKLK", "PROM", "PROMEN", "SUNPLZ", "TMACUH", "TMSHOPCITY",
        "UNIRII",
    }),
)
STRONG_SEASONALITY_WEIGHTS = {
    "store": Decimal("0.50"), "zone": Decimal("0.30"), "network": Decimal("0.20"),
}
WEAK_SEASONALITY_WEIGHTS = {
    "store": Decimal("0.30"), "zone": Decimal("0.40"), "network": Decimal("0.30"),
}
NEW_STORE_SEASONALITY_WEIGHTS = {
    "store": Decimal("0"), "zone": Decimal("0.60"), "network": Decimal("0.40"),
}


class TargetCalculatorService:
    """Coordinates repository work and explicitly injected calculation ports."""

    def __init__(
        self,
        repo: TargetCalculatorRepository,
        *,
        forecast_factor_loader: ForecastFactorLoader = get_forecast_factor,
        allocator: Allocator = allocate_with_bounds,
    ):
        self.repo = repo
        self.forecast_factor_loader = forecast_factor_loader
        self.allocator = allocator

    async def get_context(self) -> dict[str, Any]:
        latest_month = await self.repo.get_latest_sales_month()
        if not latest_month:
            raise HTTPException(status_code=404, detail="Nu exista date de vanzari pentru calculator.")
        suggested_month = shift_month(latest_month, 1)
        target_total = await self.repo.get_target_total(suggested_month)
        if target_total == 0:
            target_total = await self.repo.get_target_total(latest_month)
        cohort = await self.repo.get_active_cohort(latest_month, suggested_month)
        return build_target_context(
            latest_month=latest_month,
            suggested_month=suggested_month,
            target_total=target_total,
            cohort=[dict(row) for row in cohort],
            defaults={
                "default_min_floor": float(DEFAULT_MIN_FLOOR),
                "default_previous_month_floor_pct": float(DEFAULT_PREVIOUS_MONTH_FLOOR_PCT),
                "default_previous_month_cap_pct": float(DEFAULT_PREVIOUS_MONTH_CAP_PCT),
                "default_seasonality_years": DEFAULT_SEASONALITY_YEARS,
            },
        )

    async def calculate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await calculate_proposal(
            ProposalContext(
                repo=self.repo,
                get_forecast_factor=self.forecast_factor_loader,
                allocate_with_bounds=self.allocator,
                get_scenario_detail=self.get_scenario_detail,
                calculation_method=CALCULATION_METHOD,
                default_min_floor=DEFAULT_MIN_FLOOR,
                default_floor_pct=DEFAULT_PREVIOUS_MONTH_FLOOR_PCT,
                default_cap_pct=DEFAULT_PREVIOUS_MONTH_CAP_PCT,
                default_seasonality_years=DEFAULT_SEASONALITY_YEARS,
                max_seasonality_years=MAX_SEASONALITY_YEARS,
                default_trend_weight=DEFAULT_TREND_WEIGHT,
                default_trend_min=DEFAULT_TREND_ADJUSTMENT_MIN,
                default_trend_max=DEFAULT_TREND_ADJUSTMENT_MAX,
                default_seasonality_min=DEFAULT_SEASONALITY_MIN,
                default_seasonality_max=DEFAULT_SEASONALITY_MAX,
                minimum_seasonality_base=MIN_SEASONALITY_BASE,
                strong_seasonality_weights=STRONG_SEASONALITY_WEIGHTS,
                weak_seasonality_weights=WEAK_SEASONALITY_WEIGHTS,
                new_store_seasonality_weights=NEW_STORE_SEASONALITY_WEIGHTS,
                profitability_constants=PROFITABILITY_CONSTANTS,
            ),
            payload,
        )

    async def list_scenarios(self) -> list[dict[str, Any]]:
        serialized = [serialize_header(dict(row)) for row in await self.repo.list_scenarios()]
        for row in serialized:
            calculation_params = row.get("calculation_params")
            if row.get("rule_set_snapshot") is None and isinstance(
                calculation_params, dict
            ) and isinstance(
                calculation_params.get("profitability"), dict
            ):
                row["calculation_params"] = dict(calculation_params)
                row["calculation_params"]["profitability"] = (
                    self._saved_profitability_assumptions(row)
                )
            if row.get("rule_set_snapshot") is None:
                for key in (
                    "rule_set_id", "rule_set_hash", "rule_set_snapshot",
                    "calculation_input_sha256", "profitability_input_sha256",
                ):
                    row.pop(key, None)
        return serialized

    async def get_scenario_detail(self, scenario_id: int) -> dict[str, Any]:
        scenario = await self.repo.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
        header = serialize_header(dict(scenario))
        rows = [serialize_row(dict(row)) for row in await self.repo.get_scenario_rows(scenario_id)]
        profitability_summary = await self._attach_profitability(header, rows)
        return build_scenario_detail(header, rows, profitability_summary)

    # Compatibility methods retain the established test/service surface while
    # the implementations live in their ownership modules.
    @staticmethod
    def _profitability_assumptions(target_month: str) -> dict[str, Any]:
        return profitability_assumptions(target_month, PROFITABILITY_CONSTANTS)

    @staticmethod
    def _fallback_profitability_assumptions() -> dict[str, Any]:
        return fallback_profitability_assumptions(PROFITABILITY_CONSTANTS)

    @staticmethod
    def _saved_profitability_assumptions(scenario: dict[str, Any]) -> dict[str, Any]:
        return saved_profitability_assumptions(scenario, PROFITABILITY_CONSTANTS)

    @staticmethod
    def _saved_target_rule_set(scenario: dict[str, Any]) -> TargetRuleSet | None:
        return saved_target_rule_set(scenario)

    @staticmethod
    def _canonical_input_hash(payload: Any) -> str:
        return canonical_input_hash(payload)

    @staticmethod
    def _profitability_input_payload(inputs: dict[str, Any]) -> dict[str, Any]:
        return profitability_input_payload(inputs)

    @staticmethod
    def _forecast_coverage(
        rows: list[dict[str, Any]], inputs: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Decimal]]:
        return forecast_coverage(rows, inputs)

    @staticmethod
    def _forecast_coverage_error(coverage: dict[str, Any]) -> HTTPException:
        return forecast_coverage_error(coverage)

    def _populate_profitability(
        self, scenario: dict[str, Any], rows: list[dict[str, Any]], inputs: dict[str, Any]
    ) -> dict[str, Any]:
        return populate_profitability(scenario, rows, inputs, PROFITABILITY_CONSTANTS)

    def _frozen_profitability(
        self, scenario: dict[str, Any], rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return frozen_profitability(scenario, rows)

    async def _attach_profitability(
        self, scenario: dict[str, Any], rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return await attach_profitability(self.repo, scenario, rows, PROFITABILITY_CONSTANTS)

    async def save_final_targets(
        self,
        scenario_id: int,
        rows: list[dict[str, Any]],
        expected_revision: int,
        *,
        actor: str | None = None,
    ) -> dict[str, Any]:
        try:
            validate_unique_final_rows(rows)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if actor is not None:
            current = await self.get_scenario_detail(scenario_id)
            proposed_by_site = {row["site_code"]: row["proposed_target"] for row in current["rows"]}
            for row in rows:
                proposed = proposed_by_site.get(row["site_code"])
                final_target = row.get("final_target")
                if proposed is not None and final_target is not None and money(final_target) != money(proposed):
                    reason = str(row.get("override_reason") or row.get("note") or "").strip()
                    if not reason:
                        raise HTTPException(status_code=400, detail="Override-ul managerial necesita un motiv explicit.")
        try:
            updated = await self.repo.update_final_targets(scenario_id, rows, expected_revision, actor=actor)
        except TargetScenarioVersionConflict:
            raise HTTPException(status_code=409, detail="Scenariul a fost modificat de alt utilizator. Reincarca datele inainte de salvare.") from None
        if updated != len(rows):
            scenario = await self.repo.get_scenario(scenario_id)
            if not scenario:
                raise HTTPException(status_code=404, detail="Scenariul de target nu exista.")
            if not is_editable_scenario(scenario):
                raise HTTPException(status_code=409, detail="Un scenariu finalizat nu mai poate fi editat.")
            raise HTTPException(status_code=400, detail="Una sau mai multe locatii nu apartin scenariului.")
        return await self.get_scenario_detail(scenario_id)

    async def finalize(self, scenario_id: int, expected_revision: int) -> dict[str, Any]:
        scenario = await self.get_scenario_detail(scenario_id)
        final_error = finalization_error(scenario, CALCULATION_METHOD)
        messages = {
            "formula_veche": (409, "Scenariul a fost calculat cu o formula veche. Genereaza o propunere noua inainte de finalizare."),
            "targete_incomplete": (400, "Toate locatiile trebuie sa aiba target final completat inainte de finalizare."),
            "total_nealiniat": (400, "Totalul targetelor finale trebuie sa fie egal cu bugetul scenariului inainte de finalizare."),
        }
        if final_error in messages:
            status, detail = messages[final_error]
            raise HTTPException(status_code=status, detail=detail)
        try:
            finalized = await self.repo.finalize_scenario(scenario_id, expected_revision)
        except TargetScenarioVersionConflict:
            raise HTTPException(status_code=409, detail="Scenariul a fost modificat de alt utilizator. Reincarca datele inainte de finalizare.") from None
        if not finalized:
            raise HTTPException(status_code=409, detail="Scenariul nu poate fi finalizat.")
        return await self.get_scenario_detail(scenario_id)

    async def export_excel(self, scenario_id: int):
        return await build_target_excel(scenario_id, self.get_scenario_detail)

    async def get_store_detail(self, scenario_id: int, site_code: str) -> dict[str, Any]:
        data = await self.repo.get_store_detail(scenario_id, site_code)
        if not data:
            raise HTTPException(status_code=404, detail="Locatia nu exista in documentul de target.")
        return build_store_detail(data)

    def _serialize_header(self, row: dict[str, Any]) -> dict[str, Any]:
        return serialize_header(row)

    def _serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return serialize_row(row)

    def _regional_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return regional_summary(rows)

    def _source_summary(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return source_summary(rows)

    def _serialize_store_history(self, row: dict[str, Any]) -> dict[str, Any]:
        return serialize_store_history(row)

    def _serialize_store_agent(self, row: dict[str, Any]) -> dict[str, Any]:
        return serialize_store_agent(row)
