import { generatedGet, generatedPatch, generatedPost } from './generated/client';
import { downloadBlob } from '../lib/download';

export interface TargetCalculatorContext {
  latest_sales_month: string;
  suggested_target_month: string;
  suggested_cohort_month: string;
  suggested_total_target: number;
  default_min_floor: number;
  default_previous_month_floor_pct: number;
  default_previous_month_cap_pct: number;
  default_seasonality_years: number;
  active_store_count: number;
  regionals: string[];
  can_finalize: boolean;
}

export interface TargetSourceMonth {
  month: string;
  label: string;
  role: string;
}

export interface TargetHistoryValue extends TargetSourceMonth {
  target: number;
  realized: number;
  actual_realized?: number;
  is_forecast?: boolean;
  forecast_factor?: number;
  attainment_pct: number | null;
  weight: number;
}

export interface TargetScenarioRow {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  calculated_weight: number;
  normalized_weight: number;
  floor_target: number;
  proposed_target: number;
  final_target: number | null;
  is_floor_limited: boolean;
  history: TargetHistoryValue[];
  calculation_details: TargetCalculationDetails;
  note: string | null;
  updated_at: string;
  profitability: TargetProfitability;
}

export interface TargetProfitability {
  agent_count: number;
  base_salary_per_agent: number;
  salary_cost_at_90_pct: number;
  operating_costs: number | null;
  accessory_margin_pct: number | null;
  break_even_gross_sales: number | null;
  forecast_sales: number | null;
  anomaly_flags: string[];
}

export interface TargetProfitabilitySummary {
  status: 'ready' | 'partial';
  pnl_months: string[];
  pnl_store_count: number;
  forecast_store_count: number;
  forecast_run: {
    id: number;
    model_name: string;
    model_mode: string;
    variant: string;
    generated_at: string;
  } | null;
  assumptions: Record<string, number>;
  salary_total: number;
  operating_costs_total: number | null;
  break_even_total: number | null;
  forecast_total: number | null;
  forecast_below_break_even_count: number;
  target_below_break_even_count: number;
}

export interface TargetSeasonalityYear {
  year_offset: number;
  base_month: string;
  target_month: string;
  base_value: number;
  target_value: number;
  ratio: number | null;
}

export interface TargetCalculationDetails {
  method?: string;
  seasonality_years?: number;
  current_month?: string;
  current_forecast?: number;
  raw_estimate?: number;
  floor_target?: number;
  cap_target?: number;
  allocation_reason?: string;
  is_floor_limited?: boolean;
  is_cap_limited?: boolean;
  flags?: string[];
  seasonality?: {
    store_factor?: number | null;
    zone_factor?: number | null;
    network_factor?: number | null;
    blended_factor?: number | null;
    used_factor?: number | null;
    last_year_store_factor?: number | null;
    multiyear_store_factor?: number | null;
    weights?: Record<string, number>;
    store_years?: TargetSeasonalityYear[];
    zone_years?: TargetSeasonalityYear[];
    network_years?: TargetSeasonalityYear[];
    min?: number;
    max?: number;
  };
  trend?: {
    base_month?: string;
    ratio?: number | null;
    weight?: number;
    raw_adjustment?: number;
    used_adjustment?: number;
    min?: number;
    max?: number;
  };
}

export interface TargetRegionalSummary {
  regional: string;
  store_count: number;
  floor_total: number;
  proposed_total: number;
  final_total: number;
  current_month: string | null;
  current_forecast_total: number;
  proposed_growth_vs_current_pct: number | null;
  final_growth_vs_current_pct: number | null;
  last_year_base_month: string | null;
  last_year_target_month: string | null;
  last_year_base_total: number;
  last_year_target_total: number;
  last_year_growth_pct: number | null;
}

export interface TargetSourceSummary {
  month: string;
  label: string;
  target: number;
  realized: number;
  actual_realized: number;
  is_forecast: boolean;
  forecast_factor: number;
  attainment_pct: number | null;
}

export interface TargetScenarioSummary {
  id: number;
  target_month: string;
  cohort_month: string;
  total_target: number;
  min_floor: number;
  previous_month_floor_pct: number;
  status: 'draft' | 'finalized';
  revision: number;
  calculation_method: string;
  source_months: TargetSourceMonth[];
  warnings: string[];
  calculation_params: Record<string, unknown>;
  store_count: number;
  proposed_total: number;
  final_total: number;
  created_at: string;
  updated_at: string;
  finalized_at: string | null;
}

export interface TargetScenario extends TargetScenarioSummary {
  remaining_difference: number;
  pending_final_count: number;
  floor_limited_count: number;
  manual_adjustments_count: number;
  rows: TargetScenarioRow[];
  regional_summary: TargetRegionalSummary[];
  source_summary: TargetSourceSummary[];
  profitability_summary: TargetProfitabilitySummary;
}

export interface TargetCalculationInput {
  target_month: string;
  total_target: number;
  min_floor: number;
  previous_month_floor_pct: number;
  previous_month_cap_pct?: number;
  seasonality_years?: number;
  expected_revision?: number;
}

export async function fetchTargetCalculatorContext(): Promise<TargetCalculatorContext> {
  return generatedGet('get_context_api_target_calculator_context_get') as unknown as TargetCalculatorContext;
}

export async function fetchTargetScenarios(): Promise<TargetScenarioSummary[]> {
  return generatedGet('list_scenarios_api_target_calculator_scenarios_get') as unknown as TargetScenarioSummary[];
}

export async function fetchTargetScenario(id: number): Promise<TargetScenario> {
  return generatedGet('get_scenario_api_target_calculator_scenarios__scenario_id__get', {
    pathParams: { scenario_id: id },
  }) as unknown as TargetScenario;
}

export async function calculateTargetScenario(input: TargetCalculationInput): Promise<TargetScenario> {
  return generatedPost('calculate_scenario_api_target_calculator_scenarios_calculate_post', input) as unknown as TargetScenario;
}

export async function saveTargetFinalValues(
  id: number,
  expectedRevision: number,
  rows: Array<{ site_code: string; final_target: number | null; note: string | null }>,
): Promise<TargetScenario> {
  return generatedPatch(
    'update_final_targets_api_target_calculator_scenarios__scenario_id__rows_patch',
    { expected_revision: expectedRevision, rows },
    { pathParams: { scenario_id: id } },
  ) as unknown as TargetScenario;
}

export interface TargetStoreHistoryPoint {
  month: string;
  total_sales: number;
  target_value: number;
  target_pct: number | null;
  total_quantity: number;
  receipt_count: number;
  cartele_qty: number;
  avg_receipt: number | null;
  bon2acc_pct: number | null;
  focus_pct: number | null;
  active_agents: number;
  working_days: number;
}

export interface TargetStoreAgent {
  agent: string;
  total_sales: number;
  sales_share_pct: number;
  total_quantity: number;
  receipt_count: number;
  avg_receipt: number | null;
  bon2acc_pct: number | null;
  focus_pct: number | null;
  active_months_16: number;
  sales_16m: number;
}

export interface TargetStoreDetail {
  site_code: string;
  locatie: string;
  firma: string;
  regional: string;
  asm: string;
  target_month: string;
  cohort_month: string;
  proposed_target: number;
  final_target: number | null;
  history: TargetStoreHistoryPoint[];
  latest: TargetStoreHistoryPoint | null;
  best_month: TargetStoreHistoryPoint | null;
  avg_sales_16m: number;
  agents: TargetStoreAgent[];
}

export async function fetchTargetStoreDetail(scenarioId: number, siteCode: string): Promise<TargetStoreDetail> {
  return generatedGet('get_store_detail_api_target_calculator_scenarios__scenario_id__stores__site_code__get', {
    pathParams: { scenario_id: scenarioId, site_code: siteCode },
  }) as unknown as TargetStoreDetail;
}

export async function finalizeTargetScenario(id: number, expectedRevision: number): Promise<TargetScenario> {
  return generatedPost(
    'finalize_scenario_api_target_calculator_scenarios__scenario_id__finalize_post',
    { expected_revision: expectedRevision },
    { pathParams: { scenario_id: id } },
  ) as unknown as TargetScenario;
}

export async function downloadTargetScenario(id: number, filename: string): Promise<void> {
  const data = await generatedGet('export_scenario_api_target_calculator_scenarios__scenario_id__export_get', {
    pathParams: { scenario_id: id },
    responseType: 'blob',
  });
  downloadBlob(data, filename);
}
