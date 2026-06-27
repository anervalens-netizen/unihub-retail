import { client } from './client';
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
  floor_target: number;
  proposed_target: number;
  final_target: number | null;
  is_floor_limited: boolean;
  history: TargetHistoryValue[];
  calculation_details: TargetCalculationDetails;
  note: string | null;
  updated_at: string;
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
  const { data } = await client.get<TargetCalculatorContext>('/api/target-calculator/context');
  return data;
}

export async function fetchTargetScenarios(): Promise<TargetScenarioSummary[]> {
  const { data } = await client.get<TargetScenarioSummary[]>('/api/target-calculator/scenarios');
  return data;
}

export async function fetchTargetScenario(id: number): Promise<TargetScenario> {
  const { data } = await client.get<TargetScenario>(`/api/target-calculator/scenarios/${id}`);
  return data;
}

export async function calculateTargetScenario(input: TargetCalculationInput): Promise<TargetScenario> {
  const { data } = await client.post<TargetScenario>('/api/target-calculator/scenarios/calculate', input);
  return data;
}

export async function saveTargetFinalValues(
  id: number,
  expectedRevision: number,
  rows: Array<{ site_code: string; final_target: number | null; note: string | null }>,
): Promise<TargetScenario> {
  const { data } = await client.patch<TargetScenario>(
    `/api/target-calculator/scenarios/${id}/rows`,
    { expected_revision: expectedRevision, rows },
  );
  return data;
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
  const { data } = await client.get<TargetStoreDetail>(
    `/api/target-calculator/scenarios/${scenarioId}/stores/${encodeURIComponent(siteCode)}`,
  );
  return data;
}

export async function finalizeTargetScenario(id: number, expectedRevision: number): Promise<TargetScenario> {
  const { data } = await client.post<TargetScenario>(
    `/api/target-calculator/scenarios/${id}/finalize`,
    { expected_revision: expectedRevision },
  );
  return data;
}

export async function downloadTargetScenario(id: number, filename: string): Promise<void> {
  const { data } = await client.get<Blob>(`/api/target-calculator/scenarios/${id}/export`, { responseType: 'blob' });
  downloadBlob(data, filename);
}
